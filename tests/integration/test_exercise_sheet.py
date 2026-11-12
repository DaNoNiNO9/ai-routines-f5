"""The exercise sheet: how it is done (video or animation, steps) and your record."""

from __future__ import annotations

import json
from pathlib import Path

from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.models import Exercise, WorkoutSession
from tests.integration.test_workout_flow import _log, _routine, _with_routine

VIDEO_DIR = Path(__file__).resolve().parents[2] / "app" / "static" / "video" / "exercises"


def test_the_sheet_needs_a_session(client: FlaskClient, seeded: SQLAlchemy) -> None:
    response = client.get("/entrenamiento/ejercicio/leg-press")
    assert response.status_code == 302
    assert "/entrar" in response.headers["Location"]


def test_an_exercise_with_video_shows_it_with_its_credit(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    html = client.get("/entrenamiento/ejercicio/leg-press?parcial=1").get_data(as_text=True)
    assert '<video class="sheet-video" src="/static/video/exercises/leg-press.mp4"' in html
    assert "muted loop playsinline" in html
    assert "CC-BY-SA 4.0" in html
    assert "wger" in html
    assert "<!doctype" not in html.lower()  # partial: only the sheet


def test_an_exercise_without_video_animates_its_two_photos(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    html = client.get("/entrenamiento/ejercicio/ab-roller?parcial=1").get_data(as_text=True)
    assert "<video" not in html
    assert 'class="sheet-anim is-animated"' in html
    assert "img/exercises/ab-roller/0.jpg" in html
    assert "img/exercises/ab-roller/1.jpg" in html


def test_steps_are_in_spanish_and_in_english_for_english_readers(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    spanish = client.get("/entrenamiento/ejercicio/leg-press?parcial=1").get_data(as_text=True)
    assert '<ol class="sheet-steps">' in spanish
    assert "Siéntate en la prensa" in spanish
    assert "en inglés" not in spanish
    english = client.get("/entrenamiento/ejercicio/leg-press?parcial=1&lang=en").get_data(
        as_text=True
    )
    assert "Siéntate en la prensa" not in english
    assert "leg press machine" in english.lower()


def test_every_exercise_has_spanish_steps(seeded: SQLAlchemy) -> None:
    exercises = seeded.session.scalars(select(Exercise)).all()
    assert exercises
    missing = [item.slug for item in exercises if not item.instructions_es]
    assert missing == []
    assert all(2 <= len(item.instructions_es.splitlines()) <= 5 for item in exercises)


def test_the_sheet_shows_your_record(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    item = _routine(seeded).days[0].exercises[0]
    client.post("/entreno/empezar/1")
    session = seeded.session.scalar(select(WorkoutSession))
    assert session is not None
    _log(client, session.id, item, set_index=1, weight_kg="62.5", reps="9", rir="2")
    client.post(f"/entreno/{session.id}/terminar", data={"perceived_fatigue": "3"})
    html = client.get(f"/entrenamiento/ejercicio/{item.exercise.slug}").get_data(as_text=True)
    assert "62,5 kg × 9" in html  # noqa: RUF001 - la ficha muestra el signo de multiplicar
    assert "máximo estimado" in html
    assert "Todavía no lo has hecho" not in html


def test_a_new_exercise_suggests_where_to_start(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    html = client.get("/entrenamiento/ejercicio/leg-press").get_data(as_text=True)
    assert "Todavía no lo has hecho. Para empezar, unos" in html


def test_unknown_exercises_are_not_found(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    assert client.get("/entrenamiento/ejercicio/no-existe").status_code == 404


def test_day_session_and_routine_open_the_sheet(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    day = client.get("/entrenamiento/dia/1").get_data(as_text=True)
    assert "data-sheet" in day
    assert "Buscar vídeo" not in day
    assert 'id="sheet-template"' in day
    assert "data-sheet" in client.get("/entrenamiento").get_data(as_text=True)
    client.post("/entreno/empezar/1")
    session = seeded.session.scalar(select(WorkoutSession))
    assert session is not None
    assert "data-sheet" in client.get(f"/entreno/{session.id}").get_data(as_text=True)


def test_every_credited_video_exists_and_is_light(app: Flask) -> None:
    credits = json.loads((VIDEO_DIR / "CREDITS.json").read_text(encoding="utf-8"))
    assert len(credits) >= 30
    for slug, credit in credits.items():
        video = VIDEO_DIR / f"{slug}.mp4"
        assert video.exists(), slug
        assert (VIDEO_DIR / f"{slug}.jpg").exists(), slug
        assert video.stat().st_size < 2_500_000, slug  # pensado para datos móviles
        assert credit["license"].startswith("CC"), slug
        assert credit["author"], slug
