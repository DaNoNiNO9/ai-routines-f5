"""The PDF opens and says what it must; the archive carries every record."""

from __future__ import annotations

import io
import zipfile
from datetime import date, timedelta

from flask_sqlalchemy import SQLAlchemy
from pypdf import PdfReader
from sqlalchemy import select

from app.engine.equipment_presets import preset_for
from app.models import Equipment, User
from app.services import exports, plans, tracking, workouts
from tests.factories import make_profile, make_user

TODAY = date(2026, 9, 9)


def _pdf_text(payload: bytes) -> str:
    reader = PdfReader(io.BytesIO(payload))
    return "\n".join(page.extract_text() for page in reader.pages)


def _generate(seeded: SQLAlchemy, **overrides: object):
    user = make_user(seeded.session)
    user.equipment = seeded.session.scalars(
        select(Equipment).where(Equipment.code.in_(preset_for("full_gym")))
    ).all()
    profile = make_profile(seeded.session, user, **overrides)
    result = plans.generate_for_profile(user, profile, TODAY)
    seeded.session.commit()
    return user, profile, result


def test_the_pdf_opens_and_carries_the_plan(seeded: SQLAlchemy) -> None:
    user, profile, result = _generate(seeded)
    payload = exports.plan_pdf(user, result.plan, result.routine, profile, TODAY)

    assert payload.startswith(b"%PDF-")
    reader = PdfReader(io.BytesIO(payload))
    assert len(reader.pages) >= 2
    assert reader.metadata.title is not None
    assert user.display_name in reader.metadata.title

    text = _pdf_text(payload)
    assert user.display_name in text
    assert "Objetivo diario" in text
    assert str(result.plan.calorie_target) in text
    assert "Reparto por comidas" in text
    assert "Cómo se ha calculado" in text
    assert "Rutina" in text
    assert result.routine.days[0].exercises[0].exercise.name_es in text
    # The disclaimer is on every page, not only on the first one.
    for page in reader.pages:
        assert "herramienta orientativa" in page.extract_text()


def test_the_pdf_explains_a_blocked_plan(seeded: SQLAlchemy) -> None:
    user, profile, result = _generate(seeded, is_pregnant_or_breastfeeding=True)
    assert result.plan is None
    payload = exports.plan_pdf(
        user, None, None, profile, TODAY, blocked_reasons=["Embarazo o lactancia."]
    )
    text = _pdf_text(payload)
    assert "No hay plan de nutrición" in text
    assert "Embarazo o lactancia." in text
    assert "herramienta orientativa" in text


def test_the_archive_has_one_sheet_per_kind_of_record(seeded: SQLAlchemy) -> None:
    user, _profile, result = _generate(seeded)
    tracking.upsert_weight(user, TODAY, 64.0, notes="mañana")
    tracking.upsert_intake(user, TODAY, 2000, protein_g=150, adherence_pct=90)
    tracking.upsert_activity(user, TODAY - timedelta(days=1), 9000)
    tracking.upsert_measurement(user, TODAY, waist_cm=78.0)
    session = workouts.start_session(user, result.routine, result.routine.days[0], TODAY)
    item = result.routine.days[0].exercises[0]
    workouts.log_set(session, item, 1, 8, 60.0, 2)
    workouts.finish(session, 3, "buena")
    seeded.session.commit()

    archive = exports.data_archive(user)
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        assert zipped.testzip() is None
        nombres = set(zipped.namelist())
        assert nombres == {
            "LEEME.txt",
            "cuenta.csv",
            "cuestionarios.csv",
            "pesajes.csv",
            "ingestas.csv",
            "actividad.csv",
            "perimetros.csv",
            "planes.csv",
            "ajustes.csv",
            "rutinas.csv",
            "sesiones.csv",
            "series.csv",
        }
        pesajes = zipped.read("pesajes.csv").decode("utf-8-sig")
        assert pesajes.startswith("dia,peso_kg,nota")
        assert "64.0,mañana" in pesajes
        assert zipped.read("pesajes.csv").startswith(b"\xef\xbb\xbf")  # BOM para Excel

        cuenta = zipped.read("cuenta.csv").decode("utf-8-sig")
        assert user.email in cuenta
        series = zipped.read("series.csv").decode("utf-8-sig")
        assert item.exercise.name_es in series
        rutinas = zipped.read("rutinas.csv").decode("utf-8-sig")
        assert len(rutinas.strip().splitlines()) == 1 + sum(
            len(day.exercises) for day in result.routine.days
        )
        planes = zipped.read("planes.csv").decode("utf-8-sig")
        assert str(result.plan.calorie_target) in planes
        assert "pesajes.csv" in zipped.read("LEEME.txt").decode("utf-8")


def test_the_archive_only_carries_its_owner(seeded: SQLAlchemy) -> None:
    user, _profile, _result = _generate(seeded)
    tracking.upsert_weight(user, TODAY, 64.0)
    stranger = make_user(seeded.session, email="otra@example.com", display_name="Otra")
    tracking.upsert_weight(stranger, TODAY, 99.9)
    seeded.session.commit()

    with zipfile.ZipFile(io.BytesIO(exports.data_archive(user))) as zipped:
        contenido = zipped.read("pesajes.csv").decode("utf-8-sig")
    assert "64.0" in contenido
    assert "99.9" not in contenido


def test_the_archive_of_an_empty_account_still_opens(database: SQLAlchemy) -> None:
    user = make_user(database.session)
    database.session.commit()
    with zipfile.ZipFile(io.BytesIO(exports.data_archive(user))) as zipped:
        assert zipped.testzip() is None
        assert zipped.read("pesajes.csv").decode("utf-8-sig").strip() == "dia,peso_kg,nota"


def test_the_file_name_is_safe(database: SQLAlchemy) -> None:
    user = make_user(database.session, display_name="Ana / Ríos")
    assert exports.export_filename(user, TODAY, "pdf") == "forja-plan-ana-rios-2026-09-09.pdf"
    nameless = make_user(database.session, email="x@y.com", display_name="///")
    assert exports.export_filename(nameless, TODAY, "zip") == "forja-datos-usuario-2026-09-09.zip"
    assert isinstance(database.session.scalar(select(User)), User)


def test_the_pdf_writes_labels_in_spanish_not_enum_values(seeded: SQLAlchemy) -> None:
    """A plan someone takes to a dietitian cannot say "fat_loss" or "katch_mcardle"."""
    user, profile, result = _generate(seeded)
    text = _pdf_text(exports.plan_pdf(user, result.plan, result.routine, profile, TODAY))
    assert "Perder grasa".lower() in text.lower()
    assert "Katch-McArdle" in text
    assert "fat_loss" not in text
    assert "katch_mcardle" not in text
    assert "navy" not in text.lower() or "Navy" in text  # la fórmula sí se nombra
