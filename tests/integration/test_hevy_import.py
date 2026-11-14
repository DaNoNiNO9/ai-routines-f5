"""Hevy import: read the export, pair the exercises, store the history once."""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, select

from app.engine.enums import SetType, WorkoutStatus
from app.models import SetLog, WorkoutSession
from app.services import hevy
from tests.integration.test_auth import PASSWORD
from tests.integration.test_workout_flow import _with_routine

HEADER = (
    '"title","start_time","end_time","description","exercise_title","superset_id",'
    '"exercise_notes","set_index","set_type","weight_kg","reps","distance_km",'
    '"duration_seconds","rpe"'
)
PUSH = '"Push A","10 Nov 2026, 18:30","10 Nov 2026, 19:35","",'
LEGS = '"Legs","12 Nov 2026, 07:00","12 Nov 2026, 08:10","",'
ROWS = [
    PUSH + '"Bench Press (Barbell)","","",0,"warmup",40,10,,,',
    PUSH + '"Bench Press (Barbell)","","",1,"normal",80,8,,,8',
    PUSH + '"Bench Press (Barbell)","","",2,"normal",80,7,,,9',
    PUSH + '"Lateral Raise (Dumbbell)","","",0,"normal",10,15,,,',
    PUSH + '"Treadmill","","",0,"normal",,,2.5,900,',
    PUSH + '"Mystery Machine Thing","","",0,"normal",30,12,,,',
    LEGS + '"Squat (Barbell)","","",0,"normal",100,5,,,',
    LEGS + '"Squat (Barbell)","","",1,"failure",100,5,,,10',
]
CSV = ("﻿" + HEADER + "\n" + "\n".join(ROWS) + "\n").encode("utf-8")


def test_the_export_is_read_into_workouts() -> None:
    history = hevy.parse_csv(CSV, "Europe/Madrid")
    assert [w.title for w in history.workouts] == ["Push A", "Legs"]
    push = history.workouts[0]
    assert push.started_at.hour == 17  # 18:30 en Madrid es 17:30 UTC en noviembre
    assert history.skipped_cardio == 1  # la cinta: tiempo y distancia, sin repeticiones
    bench = [s for s in push.sets if s.exercise == "Bench Press (Barbell)"]
    assert [s.set_index for s in bench] == [1, 2, 3]
    assert bench[0].set_type is SetType.WARMUP
    assert (bench[1].weight_kg, bench[1].reps, bench[1].rir) == (80, 8, 2)  # RPE 8 = 2 en reserva
    assert history.exercises["Squat (Barbell)"] == 2


def test_pounds_become_kilos() -> None:
    data = CSV.decode("utf-8").replace('"weight_kg"', '"weight_lbs"').encode("utf-8")
    history = hevy.parse_csv(data)
    assert history.unit == "lb"
    squat = history.workouts[1].sets[0]
    assert squat.weight_kg == pytest.approx(45.36, abs=0.01)


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"a,b,c\n1,2,3\n", "not_hevy"),
        (b"\xff\xfe\x00garbage", "not_csv"),
        ((HEADER + "\n").encode(), "empty"),
    ],
)
def test_files_that_are_not_an_export_are_refused(data: bytes, reason: str) -> None:
    with pytest.raises(hevy.HevyImportError) as error:
        hevy.parse_csv(data)
    assert error.value.reason == reason


def test_usual_names_are_paired_and_strangers_are_not(seeded: SQLAlchemy) -> None:
    matches = hevy.suggest_matches(
        ["Bench Press (Barbell)", "Lateral Raise (Dumbbell)", "Mystery Machine Thing", "Leg Press"]
    )
    assert matches["Bench Press (Barbell)"].exercise.name_en == "Barbell Bench Press - Medium Grip"
    assert matches["Bench Press (Barbell)"].sure
    assert matches["Lateral Raise (Dumbbell)"].exercise.name_en == "Side Lateral Raise"
    assert matches["Mystery Machine Thing"].exercise is None
    assert matches["Leg Press"].exercise.name_en == "Leg Press"


def test_every_alias_points_to_a_real_exercise(seeded: SQLAlchemy) -> None:
    from app.models import Exercise

    names = set(seeded.session.scalars(select(Exercise.name_en)))
    missing = sorted(set(hevy.ALIASES.values()) - names)
    assert missing == []


def _upload(client: FlaskClient, data: bytes = CSV) -> str:
    response = client.post(
        "/cuenta/importar/hevy",
        data={"archivo": (io.BytesIO(data), "workouts.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _confirm_as_suggested(client: FlaskClient, page: str) -> object:
    token = re.search(r'name="token" value="([^"]+)"', page).group(1)
    pairs = dict(re.findall(r'name="(par-\d+)" list="ejercicios-alza"\s*value="([^"]*)"', page))
    return client.post("/cuenta/importar/hevy/confirmar", data={"token": token, **pairs})


def test_preview_then_import_writes_finished_sessions(
    client: FlaskClient, seeded: SQLAlchemy, app: Flask
) -> None:
    _with_routine(client)
    page = _upload(client)
    assert "Revisa antes de importar" in page
    assert "2 entrenos" in page
    assert "Mystery Machine Thing" in page
    assert "Sin pareja: no se importa" in page
    # Nada escrito todavía: solo la vista previa.
    assert seeded.session.scalar(select(func.count()).select_from(WorkoutSession)) == 0

    response = _confirm_as_suggested(client, page)
    assert response.status_code == 302
    sessions = seeded.session.scalars(
        select(WorkoutSession).order_by(WorkoutSession.started_at)
    ).all()
    assert len(sessions) == 2
    assert all(s.status is WorkoutStatus.COMPLETED for s in sessions)
    assert sessions[0].notes == "Hevy · Push A"
    sets = seeded.session.scalar(select(func.count()).select_from(SetLog))
    assert sets == 6  # 3 press + 1 elevación + 2 sentadillas; ni la cinta ni lo desconocido
    # El fichero no se queda en el servidor.
    assert not list(Path(app.config["IMPORTS_DIR"]).glob("*.csv"))
    history = client.get("/entreno/historial").get_data(as_text=True)
    assert "Importados 2 entrenos con 6 series" in history
    assert "Hevy · Push A" in history


def test_importing_the_same_file_twice_adds_nothing(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _with_routine(client)
    _confirm_as_suggested(client, _upload(client))
    _confirm_as_suggested(client, _upload(client))
    assert seeded.session.scalar(select(func.count()).select_from(WorkoutSession)) == 2
    assert seeded.session.scalar(select(func.count()).select_from(SetLog)) == 6


def test_an_emptied_pair_is_left_out(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    page = _upload(client)
    token = re.search(r'name="token" value="([^"]+)"', page).group(1)
    client.post("/cuenta/importar/hevy/confirmar", data={"token": token, "par-0": ""})
    # Solo queda par-0 (el press, el más repetido) y se ha vaciado: nada que importar.
    assert seeded.session.scalar(select(func.count()).select_from(SetLog)) == 0


def test_imported_weights_feed_the_next_session(client: FlaskClient, seeded: SQLAlchemy) -> None:
    from app.models import Exercise, User
    from app.services.workouts import last_performance

    _with_routine(client)
    _confirm_as_suggested(client, _upload(client))
    started = client.post("/entreno/empezar/1")
    session_id = int(started.headers["Location"].rstrip("/").split("/")[-1])
    user = seeded.session.scalar(select(User))
    bench = seeded.session.scalar(
        select(Exercise).where(Exercise.name_en == "Barbell Bench Press - Medium Grip")
    )
    previous = last_performance(user, bench, seeded.session.get(WorkoutSession, session_id))
    assert previous is not None
    assert list(previous.sets) == [(8, 80.0), (7, 80.0)]  # sin el calentamiento


def test_a_wrong_file_is_explained(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    response = client.post(
        "/cuenta/importar/hevy",
        data={"archivo": (io.BytesIO(b"a,b\n1,2\n"), "otro.csv")},
        content_type="multipart/form-data",
    )
    assert "No parece una exportación de entrenos de Hevy" in response.get_data(as_text=True)


def test_an_expired_preview_imports_nothing(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    response = client.post(
        "/cuenta/importar/hevy/confirmar", data={"token": "no-existe-este-token", "par-0": "x"}
    )
    assert response.headers["Location"].endswith("/cuenta/importar/hevy")
    assert seeded.session.scalar(select(func.count()).select_from(WorkoutSession)) == 0


def test_cancelling_or_withdrawing_consent_deletes_the_held_file(
    client: FlaskClient, seeded: SQLAlchemy, app: Flask
) -> None:
    _with_routine(client)
    folder = Path(app.config["IMPORTS_DIR"])
    _upload(client)
    assert list(folder.glob("*.csv"))
    client.post("/cuenta/importar/hevy/cancelar")
    assert not list(folder.glob("*.csv"))
    _upload(client)
    client.post("/cuenta/consentimiento/retirar", data={"current_password": PASSWORD})
    assert not list(folder.glob("*.csv"))


def test_one_person_cannot_use_another_persons_upload(
    client: FlaskClient, seeded: SQLAlchemy, app: Flask
) -> None:
    with app.test_request_context():
        token = hevy.keep_pending(999, CSV)
    _with_routine(client)
    response = client.post("/cuenta/importar/hevy/confirmar", data={"token": token})
    assert response.headers["Location"].endswith("/cuenta/importar/hevy")
    assert seeded.session.scalar(select(func.count()).select_from(WorkoutSession)) == 0
