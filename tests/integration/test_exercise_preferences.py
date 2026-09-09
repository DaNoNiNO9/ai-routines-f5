"""Apartar un ejercicio desde la rutina, que es donde se ve lo que se está apartando.

Antes esto se pedía en el cuestionario, escribiendo de memoria nombres exactos de
un catálogo de 190 ejercicios. Ahora se decide con la ficha delante.
"""

from __future__ import annotations

import re

from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.models import Profile, RoutineDay, User
from tests.integration.test_auth import _register
from tests.integration.test_onboarding import _fill_all


def _with_routine(client: FlaskClient, email: str = "gustos@example.com") -> None:
    assert _register(client, email=email).status_code == 302
    _fill_all(client)
    assert client.post("/cuestionario/revisar").status_code == 302


def _day_exercises(client: FlaskClient, index: int = 1) -> list[str]:
    page = client.get(f"/entrenamiento/dia/{index}").get_data(as_text=True)
    return re.findall(r'<h2 class="card-title">([^<]+)</h2>', page)


def _first_item_id(client: FlaskClient, index: int = 1) -> int:
    page = client.get(f"/entrenamiento/dia/{index}").get_data(as_text=True)
    return int(re.findall(r'name="routine_exercise_id" value="(\d+)"', page)[0])


def test_disliking_an_exercise_swaps_it_and_remembers(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    before = _day_exercises(client)
    item_id = _first_item_id(client)

    response = client.post(
        "/entrenamiento/dia/1/cambiar", data={"routine_exercise_id": item_id}, follow_redirects=True
    )
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "No volverá a aparecer" in page

    after = _day_exercises(client)
    assert after[0] != before[0]
    assert len(after) == len(before)  # se cambia, no se pierde el hueco

    profile = seeded.session.scalar(select(Profile))
    assert profile is not None
    assert len(profile.disliked_exercises) == 1

    # Y aparece en la rutina, con su botón para deshacerlo.
    routine_page = client.get("/entrenamiento").get_data(as_text=True)
    assert "Ejercicios apartados" in routine_page
    assert before[0] in routine_page


def test_an_exercise_set_aside_can_come_back(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    client.post(
        "/entrenamiento/dia/1/cambiar", data={"routine_exercise_id": _first_item_id(client)}
    )
    profile = seeded.session.scalar(select(Profile))
    assert profile is not None
    slug = profile.disliked_exercises[0]

    response = client.post("/entrenamiento/permitir", data={"slug": slug}, follow_redirects=True)
    assert "Vuelve a estar disponible" in response.get_data(as_text=True)
    seeded.session.expire_all()
    assert seeded.session.scalar(select(Profile)).disliked_exercises == []
    assert "Ejercicios apartados" not in client.get("/entrenamiento").get_data(as_text=True)


def test_a_set_aside_exercise_does_not_come_back_in_the_next_routine(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    """La siguiente versión del cuestionario tampoco lo programa."""
    _with_routine(client)
    client.post(
        "/entrenamiento/dia/1/cambiar", data={"routine_exercise_id": _first_item_id(client)}
    )
    profile = seeded.session.scalar(select(Profile))
    assert profile is not None
    apartado = profile.disliked_exercises[0]

    _fill_all(client)
    assert client.post("/cuestionario/revisar").status_code == 302

    seeded.session.expire_all()
    nuevo = seeded.session.scalar(select(Profile).order_by(Profile.version.desc()))
    assert nuevo is not None
    assert apartado in nuevo.disliked_exercises  # el cuestionario no lo olvida
    programados = {
        item.exercise.slug
        for day in seeded.session.scalars(select(RoutineDay)).all()
        for item in day.exercises
    }
    assert apartado not in programados


def test_another_account_cannot_touch_your_routine(app: Flask, seeded: SQLAlchemy) -> None:
    owner = app.test_client()
    _with_routine(owner, "duena2@example.com")
    item_id = _first_item_id(owner)

    intruder = app.test_client()
    _with_routine(intruder, "intrusa2@example.com")
    response = intruder.post("/entrenamiento/dia/1/cambiar", data={"routine_exercise_id": item_id})
    assert response.status_code == 404

    seeded.session.expire_all()
    duena = seeded.session.scalar(select(User).where(User.email == "duena2@example.com"))
    assert duena is not None
    assert duena.profiles[-1].disliked_exercises == []


def test_without_an_alternative_nothing_changes(client: FlaskClient, seeded: SQLAlchemy) -> None:
    """Si no hay recambio posible, se dice y la rutina se queda como estaba."""
    _with_routine(client)
    item_id = _first_item_id(client)
    profile = seeded.session.scalar(select(Profile))
    assert profile is not None
    # Todas las alternativas ya apartadas: no queda ninguna a la que cambiar.
    from app.services import dashboard

    equipment = frozenset(item.code for item in profile.user.equipment)
    day = seeded.session.scalar(select(RoutineDay))
    assert day is not None
    item = next(row for row in day.exercises if row.id == item_id)
    profile.disliked_exercises = [
        row.slug for row in dashboard.usable_alternatives(item, profile, equipment)
    ]
    seeded.session.commit()

    before = _day_exercises(client)
    response = client.post(
        "/entrenamiento/dia/1/cambiar", data={"routine_exercise_id": item_id}, follow_redirects=True
    )
    assert "No hay otro ejercicio" in response.get_data(as_text=True)
    assert _day_exercises(client) == before
