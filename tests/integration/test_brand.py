"""The app is called Alza everywhere, in both languages, with its mark and icons.

Also the English counterpart of ``test_coherence``: an English screen must not
fall back to Spanish interface text. Names generated and stored in the
database ("Torso / pierna · 4 días", "Desayuno") are data, not interface, and
are left out by the word list below.
"""

from __future__ import annotations

import io
import re
import zipfile

from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from pypdf import PdfReader

from tests.integration.test_coherence import LEFTOVERS, _pages

OLD_NAME = re.compile(r"forja", re.I)
# Spanish words that never appear in stored names, only in interface text.
SPANISH_WORDS = re.compile(
    r"\b(?:de|del|la|el|los|las|con|por|para|semana|tu|tus|sin|más|menos|hoy|serie|series)\b"
)


def test_the_header_carries_the_mark_and_the_name(client: FlaskClient) -> None:
    html = client.get("/").get_data(as_text=True)
    assert 'class="brand-mark"' in html
    assert '<span class="brand-name">Alza</span>' in html
    assert "<title>Alza" in html


def test_every_page_declares_the_icons(client: FlaskClient) -> None:
    html = client.get("/").get_data(as_text=True)
    for asset in ("img/favicon.svg", "img/favicon.ico", "img/apple-touch-icon.png"):
        assert asset in html
        assert client.get(f"/static/{asset}").status_code == 200


def test_favicon_ico_is_served_at_the_root(client: FlaskClient) -> None:
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    assert response.data[:4] == b"\x00\x00\x01\x00"  # ICO magic number


def test_no_screen_says_forja(lived_in: FlaskClient, seeded: SQLAlchemy) -> None:
    for language in ("es", "en"):
        lived_in.get(f"/panel?lang={language}")
        for path, text in _pages(lived_in, seeded).items():
            assert not OLD_NAME.search(text), (language, path)


def test_exports_say_alza(lived_in: FlaskClient) -> None:
    pdf = lived_in.get("/cuenta/plan.pdf")
    assert 'filename="alza-plan-' in pdf.headers["Content-Disposition"]
    reader = PdfReader(io.BytesIO(pdf.data))
    text = "".join(page.extract_text() for page in reader.pages)
    assert "ALZA" in text
    assert not OLD_NAME.search(text)
    assert reader.metadata is not None
    assert reader.metadata.author == "Alza"

    archive = lived_in.get("/cuenta/datos.zip")
    assert 'filename="alza-datos-' in archive.headers["Content-Disposition"]
    with zipfile.ZipFile(io.BytesIO(archive.data)) as bundle:
        leeme = next(name for name in bundle.namelist() if name.upper().startswith("LEEME"))
        assert bundle.read(leeme).decode("utf-8-sig").startswith("Exportación de datos de Alza")


def test_english_screens_are_in_english(lived_in: FlaskClient, seeded: SQLAlchemy) -> None:
    lived_in.get("/panel?lang=en")
    for path, text in _pages(lived_in, seeded).items():
        prose = text.replace("None yet", "")  # English for «Ninguna todavía», not Python's None
        assert not LEFTOVERS.search(prose), (path, LEFTOVERS.findall(prose))
        assert not SPANISH_WORDS.search(text), (path, SPANISH_WORDS.findall(text))
