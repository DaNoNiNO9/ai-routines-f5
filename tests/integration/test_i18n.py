"""Locale selection and template translation hooks."""

from __future__ import annotations

import io
import zipfile

from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from pypdf import PdfReader
from sqlalchemy import select

from app.engine import messages
from app.engine.types import Note
from app.models import User
from tests.integration.test_onboarding import _signup
from tests.integration.test_plan_pages import _generate

DEFICIT = Note(code="target.deficit", level="info", params={"pct": 20})


def test_default_locale_is_spanish(client: FlaskClient) -> None:
    html = client.get("/").get_data(as_text=True)
    assert '<html lang="es"' in html


def test_lang_query_parameter_switches_and_persists(client: FlaskClient) -> None:
    assert '<html lang="en"' in client.get("/?lang=en").get_data(as_text=True)
    assert '<html lang="en"' in client.get("/").get_data(as_text=True)


def test_unknown_lang_is_ignored(client: FlaskClient) -> None:
    assert '<html lang="es"' in client.get("/?lang=fr").get_data(as_text=True)


def test_accept_language_header_is_honoured(client: FlaskClient) -> None:
    html = client.get("/", headers={"Accept-Language": "en-US,en;q=0.9"}).get_data(as_text=True)
    assert '<html lang="en"' in html


def test_unsupported_accept_language_falls_back_to_default(client: FlaskClient) -> None:
    html = client.get("/", headers={"Accept-Language": "de-DE,de;q=0.9"}).get_data(as_text=True)
    assert '<html lang="es"' in html


def test_landing_page_reads_in_english(client: FlaskClient) -> None:
    html = client.get("/?lang=en").get_data(as_text=True)
    assert "Your plan, calculated." in html
    assert "Tu plan, calculado." not in html
    assert "Sign in" in html
    assert "Skip to content" in html


def test_account_language_beats_the_browser_header(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    user = seeded.session.scalar(select(User))
    assert user is not None
    user.locale = "en"
    seeded.session.commit()

    html = client.get("/panel", headers={"Accept-Language": "es-ES,es;q=0.9"}).get_data(
        as_text=True
    )
    assert '<html lang="en"' in html
    assert "Start the questionnaire" in html


def test_engine_notes_render_in_the_language_of_the_request(app: Flask) -> None:
    with app.test_request_context("/?lang=en"):
        assert messages.render(DEFICIT) == "You eat 20 % less than you burn."
    with app.test_request_context("/"):
        assert messages.render(DEFICIT) == "Comes un 20 % menos de lo que gastas."


def test_engine_notes_stay_in_spanish_outside_the_application() -> None:
    """Los scripts y los tests del motor no tienen app a la que preguntar."""
    assert messages.render(DEFICIT) == "Comes un 20 % menos de lo que gastas."


def test_stored_plan_explanations_are_rendered_again_in_english(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    """El plan se generó en castellano: sus avisos se vuelven a pintar traducidos."""
    _generate(client)
    spanish = client.get("/nutricion").get_data(as_text=True)
    english = client.get("/nutricion?lang=en").get_data(as_text=True)

    assert "Metabolismo basal por Katch-McArdle" in spanish
    assert "Basal metabolic rate by Katch-McArdle" in english
    assert "Metabolismo basal por Katch-McArdle" not in english
    assert "Your nutrition plan" in english
    assert "Worth knowing" in english


def test_routine_pages_are_translated_too(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _generate(client)
    html = client.get("/entrenamiento?lang=en").get_data(as_text=True)
    assert "Weekly volume" in html
    assert "How it is put together" in html
    assert "How to progress" in html  # aviso del motor, no plantilla


def test_the_pdf_is_exported_in_english(client: FlaskClient, seeded: SQLAlchemy) -> None:
    """El documento que alguien se lleva al médico, entero en su idioma."""
    _generate(client)
    payload = client.get("/cuenta/plan.pdf?lang=en").get_data()
    reader = PdfReader(io.BytesIO(payload))
    texto = "\n".join(page.extract_text() for page in reader.pages)

    assert "NUTRITION AND TRAINING PLAN" in texto
    assert "Daily target" in texto
    assert "How this was worked out" in texto
    assert "less than you burn" in texto  # aviso del motor
    assert "Forja is a guidance tool" in texto  # aviso legal de todas las páginas
    assert "Objetivo diario" not in texto
    assert "Cómo se ha calculado" not in texto


def test_the_archive_readme_is_translated(client: FlaskClient, seeded: SQLAlchemy) -> None:
    """El LEEME se traduce; los nombres de columna se quedan en castellano a propósito."""
    _generate(client)
    payload = client.get("/cuenta/datos.zip?lang=en").get_data()
    with zipfile.ZipFile(io.BytesIO(payload)) as archivo:
        leeme = archivo.read("LEEME.txt").decode("utf-8")
        cabecera = archivo.read("planes.csv").decode("utf-8-sig").splitlines()[0]

    assert leeme.startswith("Forja data export")
    assert "Every version of the nutrition plan." in leeme
    assert cabecera.startswith("version,estado,desde")
