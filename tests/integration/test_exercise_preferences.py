"""Cambiar un ejercicio eligiendo, por grupo muscular, con la ficha delante.

Antes la app elegía el recambio («No me gusta: cámbialo») y en la sesión había un
desplegable de nombres. Ahora se ve todo lo que se puede hacer, agrupado por
músculo, se abre la ficha (vídeo y pasos) y se decide: solo hoy o en la rutina.
"""

from __future__ import annotations

import re

from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.models import Exercise, Profile, RoutineDay, RoutineExercise, User, WorkoutSession
from app.services import swaps
from tests.integration.test_auth import _register
from tests.integration.test_onboarding import _fill_all


def _with_routine(client: FlaskClient, email: str = "gustos@example.com") -> None:
    assert _register(client, email=email).status_code == 302
    _fill_all(client)
    assert client.post("/cuestionario/revisar").status_code == 302


def _first_item(database: SQLAlchemy, email: str = "gustos@example.com") -> RoutineExercise:
    user = database.session.scalar(select(User).where(User.email == email))
    assert user is not None
    day = next(
        d for d in database.session.scalars(select(RoutineDay)) if d.routine.user_id == user.id
    )
    return day.exercises[0]


def _options(page: str) -> list[int]:
    return [int(x) for x in re.findall(r'name="exercise_id" value="(\d+)"', page)]


def test_every_day_offers_to_change_each_exercise(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    item = _first_item(seeded)
    page = client.get("/entrenamiento/dia/1").get_data(as_text=True)
    assert f"/entrenamiento/cambiar/{item.id}" in page
    assert "Cambiar ejercicio" in page
    assert "No me gusta: cámbialo" not in page
    assert f"/entrenamiento/cambiar/{item.id}" in client.get("/entrenamiento").get_data(
        as_text=True
    )


def test_the_choice_is_grouped_by_muscle_and_starts_with_its_own(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    item = _first_item(seeded)
    page = client.get(f"/entrenamiento/cambiar/{item.id}").get_data(as_text=True)
    assert "Cambiar ejercicio" in page
    assert 'aria-current="true"' in page  # el grupo del ejercicio, elegido de entrada
    assert "Ver cómo se hace" in page  # cada opción abre su ficha
    ids = _options(page)
    assert ids
    assert item.exercise_id not in ids
    own = item.exercise.primary_muscle
    for exercise_id in ids:
        assert seeded.session.get(Exercise, exercise_id).primary_muscle == own
    everything = _options(
        client.get(f"/entrenamiento/cambiar/{item.id}?musculo=todos").get_data(as_text=True)
    )
    assert len(everything) > len(ids)
    partial = client.get(f"/entrenamiento/cambiar/{item.id}?parcial=1").get_data(as_text=True)
    assert "<html" not in partial  # la versión para la ventana va sin la página


def test_only_what_you_can_do_is_offered(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    item = _first_item(seeded)
    profile = seeded.session.scalar(select(Profile))
    equipment = frozenset(row.code for row in profile.user.equipment)
    pool = swaps.usable_pool(item, profile, equipment)
    in_day = {other.exercise_id for other in item.day.exercises}
    assert pool
    assert not ({row.id for row in pool} & in_day)


def test_choosing_in_the_routine_keeps_it_from_now_on(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    item = _first_item(seeded)
    old = item.exercise.display_name
    choice = _options(client.get(f"/entrenamiento/cambiar/{item.id}").get_data(as_text=True))[0]
    response = client.post(
        f"/entrenamiento/cambiar/{item.id}",
        data={"exercise_id": choice, "destino": "rutina", "volver": "/entrenamiento/dia/1"},
        follow_redirects=True,
    )
    assert f"sustituye a {old}" in response.get_data(as_text=True)
    seeded.session.expire_all()
    assert seeded.session.get(RoutineExercise, item.id).exercise_id == choice
    assert seeded.session.scalar(select(Profile)).disliked_exercises == []


def test_setting_the_old_one_aside_is_optional_and_reversible(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    item = _first_item(seeded)
    slug = item.exercise.slug
    choice = _options(client.get(f"/entrenamiento/cambiar/{item.id}").get_data(as_text=True))[0]
    client.post(
        f"/entrenamiento/cambiar/{item.id}",
        data={"exercise_id": choice, "destino": "rutina", "apartar": "1"},
    )
    seeded.session.expire_all()
    assert seeded.session.scalar(select(Profile)).disliked_exercises == [slug]
    assert "Ejercicios apartados" in client.get("/entrenamiento").get_data(as_text=True)

    response = client.post("/entrenamiento/permitir", data={"slug": slug}, follow_redirects=True)
    assert "Vuelve a estar disponible" in response.get_data(as_text=True)
    seeded.session.expire_all()
    assert seeded.session.scalar(select(Profile)).disliked_exercises == []


def test_a_set_aside_exercise_does_not_come_back_in_the_next_routine(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    item = _first_item(seeded)
    apartado = item.exercise.slug
    choice = _options(client.get(f"/entrenamiento/cambiar/{item.id}").get_data(as_text=True))[0]
    client.post(
        f"/entrenamiento/cambiar/{item.id}",
        data={"exercise_id": choice, "destino": "rutina", "apartar": "1"},
    )
    _fill_all(client)
    assert client.post("/cuestionario/revisar").status_code == 302
    seeded.session.expire_all()
    nuevo = seeded.session.scalar(select(Profile).order_by(Profile.version.desc()))
    assert apartado in nuevo.disliked_exercises
    programados = {
        row.exercise.slug
        for day in seeded.session.scalars(select(RoutineDay)).all()
        if day.routine.status.value == "active"
        for row in day.exercises
    }
    assert apartado not in programados


def test_only_today_changes_the_session_and_not_the_routine(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    started = client.post("/entreno/empezar/1")
    session_id = int(started.headers["Location"].rstrip("/").split("/")[-1])
    item = _first_item(seeded)
    session_page = client.get(f"/entreno/{session_id}").get_data(as_text=True)
    assert f"/entrenamiento/cambiar/{item.id}?sesion={session_id}" in session_page.replace(
        "&amp;", "&"
    )
    page = client.get(f"/entrenamiento/cambiar/{item.id}?sesion={session_id}").get_data(
        as_text=True
    )
    assert "Solo hoy" in page
    assert "En mi rutina" in page
    choice = _options(page)[0]
    response = client.post(
        f"/entrenamiento/cambiar/{item.id}",
        data={"exercise_id": choice, "destino": "sesion", "sesion_id": session_id},
    )
    assert response.headers["Location"].endswith(f"/entreno/{session_id}#ex-{item.id}")
    seeded.session.expire_all()
    session = seeded.session.get(WorkoutSession, session_id)
    assert session.substitutions == {str(item.id): choice}
    assert seeded.session.get(RoutineExercise, item.id).exercise_id != choice


def test_an_exercise_you_cannot_do_is_refused(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    item = _first_item(seeded)
    profile = seeded.session.scalar(select(Profile))
    equipment = frozenset(row.code for row in profile.user.equipment)
    usable = {row.id for row in swaps.usable_pool(item, profile, equipment)}
    forbidden = next(
        row.id
        for row in seeded.session.scalars(select(Exercise))
        if row.id not in usable and row.id != item.exercise_id
    )
    response = client.post(
        f"/entrenamiento/cambiar/{item.id}",
        data={"exercise_id": forbidden, "destino": "rutina"},
        follow_redirects=True,
    )
    assert "no encaja con tu material" in response.get_data(as_text=True)
    seeded.session.expire_all()
    assert seeded.session.get(RoutineExercise, item.id).exercise_id == item.exercise_id


def test_another_account_cannot_touch_your_routine(app: Flask, seeded: SQLAlchemy) -> None:
    owner = app.test_client()
    _with_routine(owner, "duena2@example.com")
    item = _first_item(seeded, "duena2@example.com")
    original = item.exercise_id

    intruder = app.test_client()
    _with_routine(intruder, "intrusa2@example.com")
    assert intruder.get(f"/entrenamiento/cambiar/{item.id}").status_code == 404
    response = intruder.post(
        f"/entrenamiento/cambiar/{item.id}", data={"exercise_id": 1, "destino": "rutina"}
    )
    assert response.status_code == 404
    seeded.session.expire_all()
    assert seeded.session.get(RoutineExercise, item.id).exercise_id == original
