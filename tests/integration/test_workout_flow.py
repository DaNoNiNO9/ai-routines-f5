"""A whole session logged through HTTP: start, sets, substitution, close, history."""

from __future__ import annotations

from typing import Any

from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.engine.enums import WorkoutStatus
from app.models import Routine, RoutineExercise, SetLog, User, WorkoutSession
from tests.integration.test_onboarding import _fill_all, _register, _signup


def _with_routine(client: FlaskClient) -> None:
    _signup(client)
    _fill_all(client)
    assert client.post("/cuestionario/revisar").status_code == 302


def _routine(database: SQLAlchemy) -> Routine:
    routine = database.session.scalar(select(Routine))
    assert routine is not None
    return routine


def _log(client: FlaskClient, session_id: int, item: RoutineExercise, **data: Any) -> Any:
    payload = {
        "routine_exercise_id": item.id,
        "set_index": 1,
        "weight_kg": "60",
        "reps": "8",
        "rir": "2",
        "set_type": "working",
    }
    payload.update(data)
    return client.post(f"/entreno/{session_id}/serie", data=payload)


def test_a_session_is_started_from_the_day_page(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    day_page = client.get("/entrenamiento/dia/1").get_data(as_text=True)
    assert "Empezar esta sesión" in day_page

    started = client.post("/entreno/empezar/1")
    assert started.status_code == 302
    session = seeded.session.scalar(select(WorkoutSession))
    assert session is not None
    assert session.status is WorkoutStatus.IN_PROGRESS
    assert session.routine_day.day_index == 1
    assert session.mesocycle_week == 1
    assert started.headers["Location"].endswith(f"/entreno/{session.id}")

    # Starting again continues the same session instead of opening a second one.
    again = client.post("/entreno/empezar/2", follow_redirects=True)
    assert "Ya tienes una sesión en marcha" in again.get_data(as_text=True)
    assert len(seeded.session.scalars(select(WorkoutSession)).all()) == 1
    assert client.post("/entreno/empezar/9").status_code == 404


def test_logging_sets_shows_the_rest_timer_and_persists(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    client.post("/entreno/empezar/1")
    session = seeded.session.scalar(select(WorkoutSession))
    routine = _routine(seeded)
    item = routine.days[0].exercises[0]

    page = client.get(f"/entreno/{session.id}").get_data(as_text=True)
    assert item.exercise.name_es in page
    assert f'value="{item.id}"' in page
    assert f"0/{item.sets}" in page

    logged = _log(client, session.id, item, weight_kg="62.5", reps="9")
    assert logged.status_code == 302
    location = logged.headers["Location"]
    assert f"descanso={item.rest_seconds}" in location
    assert location.endswith(f"#ex-{item.id}")

    row = seeded.session.scalar(select(SetLog))
    assert row is not None
    assert (row.reps, row.weight_kg, row.rir) == (9, 62.5, 2)

    after = client.get(location.split("#")[0]).get_data(as_text=True)
    assert "restTimer" in after
    assert "Descanso" in after
    assert "62.5 kg × 9" in after  # noqa: RUF001 - the page really shows a multiplication sign
    assert f"1/{item.sets}" in after

    # Logging the same index again corrects it instead of duplicating.
    _log(client, session.id, item, set_index=1, weight_kg="65", reps="7")
    seeded.session.expire_all()
    rows = seeded.session.scalars(select(SetLog)).all()
    assert len(rows) == 1
    assert rows[0].weight_kg == 65


def test_a_set_can_be_deleted_and_bad_input_is_refused(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    client.post("/entreno/empezar/1")
    session = seeded.session.scalar(select(WorkoutSession))
    item = _routine(seeded).days[0].exercises[0]

    _log(client, session.id, item)
    row = seeded.session.scalar(select(SetLog))
    deleted = client.post(f"/entreno/{session.id}/serie/{row.id}/borrar")
    assert deleted.status_code == 302
    assert seeded.session.scalars(select(SetLog)).all() == []

    heavy = _log(client, session.id, item, weight_kg="2000", follow_redirects=False)
    assert heavy.status_code == 302  # back to the page with the error flashed
    assert "El número debe estar entre" in client.get(f"/entreno/{session.id}").get_data(
        as_text=True
    )
    assert seeded.session.scalars(select(SetLog)).all() == []

    other_day_item = _routine(seeded).days[1].exercises[0]
    assert _log(client, session.id, other_day_item).status_code == 404


def test_an_exercise_can_be_swapped_before_logging(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    client.post("/entreno/empezar/1")
    session = seeded.session.scalar(select(WorkoutSession))
    routine = _routine(seeded)
    item = next(
        candidate for candidate in routine.days[0].exercises if candidate.exercise.alternatives
    )
    page = client.get(f"/entreno/{session.id}").get_data(as_text=True)
    assert "Cambiar por una alternativa" in page

    from app.services import dashboard, onboarding

    user = seeded.session.scalar(select(User))
    profile = onboarding.current_profile(user)
    equipment = frozenset(code.code for code in user.equipment)
    options = dashboard.usable_alternatives(item, profile, equipment)
    assert options

    swapped = client.post(
        f"/entreno/{session.id}/sustituir",
        data={"routine_exercise_id": item.id, "exercise_id": options[0].id},
        follow_redirects=True,
    )
    text = swapped.get_data(as_text=True)
    assert "Ejercicio sustituido" in text
    assert options[0].name_es in text
    assert "sustituido</span>" in text

    _log(client, session.id, item)
    seeded.session.expire_all()
    assert seeded.session.scalar(select(SetLog)).exercise_id == options[0].id

    blocked = client.post(
        f"/entreno/{session.id}/sustituir",
        data={"routine_exercise_id": item.id, "exercise_id": ""},
        follow_redirects=True,
    )
    assert "no se puede sustituir" in blocked.get_data(as_text=True)


def test_finishing_the_session_shows_totals_and_records(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    client.post("/entreno/empezar/1")
    session = seeded.session.scalar(select(WorkoutSession))
    item = _routine(seeded).days[0].exercises[0]
    for index in (1, 2):
        _log(client, session.id, item, set_index=index, weight_kg="60", reps="8")

    finished = client.post(
        f"/entreno/{session.id}/terminar", data={"perceived_fatigue": "4", "notes": "Buen día"}
    )
    assert finished.status_code == 302
    assert finished.headers["Location"].endswith(f"/entreno/{session.id}/resumen")
    seeded.session.expire_all()
    session = seeded.session.scalar(select(WorkoutSession))
    assert session.status is WorkoutStatus.COMPLETED
    assert session.perceived_fatigue == 4
    assert session.notes == "Buen día"

    summary = client.get(f"/entreno/{session.id}/resumen").get_data(as_text=True)
    assert "2" in summary
    assert "960" in summary  # 2 x 8 x 60 kg
    assert "PR" in summary
    assert "Buen día" in summary
    assert "4 · Cansado" in summary

    # A closed session sends you to the summary, not back to the live page.
    assert client.get(f"/entreno/{session.id}").headers["Location"].endswith("/resumen")

    history = client.get("/entreno/historial").get_data(as_text=True)
    assert session.routine_day.name in history
    assert "PR ×1" in history  # noqa: RUF001 - as rendered

    progress = client.get("/entreno/progreso").get_data(as_text=True)
    assert item.exercise.name_es in progress
    assert "Con dos sesiones registradas" in progress  # only one point so far
    assert client.get(f"/entreno/progreso?ejercicio={item.exercise.slug}").status_code == 200


def test_a_session_without_sets_is_not_counted(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    client.post("/entreno/empezar/1")
    session = seeded.session.scalar(select(WorkoutSession))
    closed = client.post(f"/entreno/{session.id}/terminar", data={}, follow_redirects=True)
    assert "no cuenta como completada" in closed.get_data(as_text=True)
    seeded.session.expire_all()
    assert seeded.session.scalar(select(WorkoutSession)).status is WorkoutStatus.ABANDONED
    assert "Sin series registradas" in client.get(f"/entreno/{session.id}/resumen").get_data(
        as_text=True
    )


def test_a_session_can_be_abandoned(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    client.post("/entreno/empezar/1")
    session = seeded.session.scalar(select(WorkoutSession))
    left = client.post(f"/entreno/{session.id}/abandonar", follow_redirects=True)
    assert "Sesión abandonada" in left.get_data(as_text=True)
    seeded.session.expire_all()
    assert seeded.session.scalar(select(WorkoutSession)).status is WorkoutStatus.ABANDONED


def test_sessions_are_private_to_their_owner(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    client.post("/entreno/empezar/1")
    session = seeded.session.scalar(select(WorkoutSession))
    client.post("/salir", follow_redirects=True)

    # A stranger with their own plan still cannot reach someone else's session.
    assert _register(client, email="otra@example.com").status_code == 302
    _fill_all(client)
    client.post("/cuestionario/revisar")
    for path in (
        f"/entreno/{session.id}",
        f"/entreno/{session.id}/resumen",
    ):
        assert client.get(path).status_code == 404, path
    assert client.post(f"/entreno/{session.id}/terminar", data={}).status_code == 404
    assert client.post(f"/entreno/{session.id}/abandonar").status_code == 404
    seeded.session.expire_all()
    assert seeded.session.scalar(select(WorkoutSession)).status is WorkoutStatus.IN_PROGRESS


def test_the_empty_history_and_progress_pages_explain_themselves(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    assert "Todavía no hay sesiones" in client.get("/entreno/historial").get_data(as_text=True)
    assert "Aún no hay series" in client.get("/entreno/progreso").get_data(as_text=True)


def test_starting_a_session_without_a_routine_is_refused(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _signup(client)
    assert client.post("/entreno/empezar/1").headers["Location"].endswith("/cuestionario")
