"""Auditoría de rendimiento (Fase 13): el número de consultas no crece con los datos.

Medir milisegundos en un portátil no dice mucho; contar consultas sí. Si una
página lanza una consulta por fila, se ve enseguida al meterle más filas.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event, select

from app.engine.enums import SetType, WorkoutStatus
from app.models import Exercise, SetLog, User, WeightLog, WorkoutSession
from tests.integration.test_auth import _register
from tests.integration.test_onboarding import _fill_all

CEILINGS = {
    "/panel": 20,
    "/nutricion": 15,
    "/entrenamiento": 15,
    "/entrenamiento/dia/1": 20,
    "/diario": 15,
    "/revision": 15,
    "/entreno/historial": 15,
    "/entreno/progreso": 10,
    "/cuenta": 10,
}


@pytest.fixture
def counting(app: Flask) -> Iterator[list[str]]:
    """Cada consulta que sale hacia la base de datos durante el test."""
    from app.extensions import db

    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    engine = db.engine
    event.listen(engine, "before_cursor_execute", record)
    yield statements
    event.remove(engine, "before_cursor_execute", record)


def _sessions_with_sets(database: SQLAlchemy, user: User, how_many: int, day_offset: int) -> None:
    """Sesiones completadas con diez series cada una, sin pasar por la web."""
    exercises = database.session.scalars(select(Exercise).limit(5)).all()
    now = datetime.now(tz=UTC)
    for number in range(how_many):
        started = now - timedelta(days=day_offset + number, hours=2)
        session = WorkoutSession(
            user=user,
            started_at=started,
            finished_at=started + timedelta(minutes=55),
            status=WorkoutStatus.COMPLETED,
        )
        database.session.add(session)
        database.session.flush()
        for position, exercise in enumerate(exercises):
            for index in range(1, 3):
                database.session.add(
                    SetLog(
                        workout_session_id=session.id,
                        exercise_id=exercise.id,
                        set_index=index,
                        set_type=SetType.WORKING,
                        reps=8 + index,
                        weight_kg=40.0 + position,
                        rir=2,
                        completed_at=started + timedelta(minutes=5 * position),
                    )
                )
    database.session.commit()


def _weights(database: SQLAlchemy, user: User, first: int, last: int) -> None:
    """Pesajes de días distintos: uno por día tiene su restricción única."""
    for number in range(first, last):
        database.session.add(
            WeightLog(user=user, logged_on=user.today() - timedelta(days=number), weight_kg=64.0)
        )
    database.session.commit()


def _counts(client: FlaskClient, statements: list[str]) -> dict[str, int]:
    counted: dict[str, int] = {}
    for path in CEILINGS:
        statements.clear()
        response = client.get(path)
        assert response.status_code == 200, path
        counted[path] = len(statements)
    return counted


def test_no_page_asks_one_query_per_row(
    app: Flask, seeded: SQLAlchemy, counting: list[str]
) -> None:
    client = app.test_client()
    assert _register(client, email="carga@example.com").status_code == 302
    _fill_all(client)
    assert client.post("/cuestionario/revisar").status_code == 302
    user = seeded.session.scalar(select(User))
    assert user is not None

    _weights(seeded, user, 1, 11)
    _sessions_with_sets(seeded, user, 3, day_offset=1)
    few = _counts(client, counting)

    _weights(seeded, user, 11, 71)
    _sessions_with_sets(seeded, user, 25, day_offset=20)
    many = _counts(client, counting)

    grown = {path: (few[path], many[path]) for path in CEILINGS if many[path] > few[path] + 1}
    assert grown == {}, f"consultas que crecen con los datos: {grown}"
    over = {path: many[path] for path, ceiling in CEILINGS.items() if many[path] > ceiling}
    assert over == {}, f"páginas por encima de su techo de consultas: {over}"
