"""No screen shows what only the code should see.

A sweep over every page of an account that has used everything: plan,
routine, diary, a finished session and an open one. What a person reads must
never contain an ISO date, an internal code, a Python ``None`` or, in
Spanish, a decimal point. Each rule exists because the app once did it.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select

from app.models import WorkoutSession
from tests.integration.test_onboarding import _post_step, _signup

PAGES = (
    "/panel",
    "/nutricion",
    "/entrenamiento",
    "/entrenamiento/dia/1",
    "/entrenamiento/dia/2",
    "/diario",
    "/diario/perimetros",
    "/revision",
    "/entreno/historial",
    "/entreno/progreso",
    "/cuenta",
    "/cuestionario/revisar",
)

ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
INTERNAL_CODE = re.compile(r"\b[a-z]+(?:_[a-z0-9]+)+\b")
DECIMAL_POINT = re.compile(r"\b\d+\.\d{1,2}\b")
LEFTOVERS = re.compile(r"\bNone\b|\bnan\b|\bUndefined\b|\{\{|\}\}|%\(\w+\)s")


class _VisibleText(HTMLParser):
    """Text a person sees: no scripts, styles or attributes."""

    SKIP = frozenset({"script", "style", "template"})

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in self.SKIP:
            self._skipping += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skipping:
            self._skipping -= 1

    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self.parts.append(data)


def _visible(html: str) -> str:
    # The footer carries the version ("v0.1.0"), which is allowed its dots.
    html = re.sub(r'<footer class="site-footer">.*?</footer>', "", html, flags=re.S)
    parser = _VisibleText()
    parser.feed(html)
    return " ".join(" ".join(parser.parts).split())


def _pages(client: FlaskClient, seeded: SQLAlchemy) -> dict[str, str]:
    open_session = seeded.session.scalars(
        select(WorkoutSession).order_by(WorkoutSession.id.desc())
    ).first()
    finished = seeded.session.scalars(select(WorkoutSession).order_by(WorkoutSession.id)).first()
    assert open_session is not None
    assert finished is not None
    paths = (*PAGES, f"/entreno/{open_session.id}", f"/entreno/{finished.id}/resumen")
    pages = {}
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, path
        pages[path] = _visible(response.get_data(as_text=True))
    return pages


def test_no_screen_shows_an_iso_date_a_code_or_a_leftover(
    lived_in: FlaskClient, seeded: SQLAlchemy
) -> None:
    for path, text in _pages(lived_in, seeded).items():
        assert not ISO_DATE.search(text), (path, ISO_DATE.findall(text))
        assert not INTERNAL_CODE.search(text), (path, INTERNAL_CODE.findall(text))
        assert not LEFTOVERS.search(text), (path, LEFTOVERS.findall(text))


def test_spanish_screens_use_a_decimal_comma(lived_in: FlaskClient, seeded: SQLAlchemy) -> None:
    for path, text in _pages(lived_in, seeded).items():
        assert not DECIMAL_POINT.search(text), (path, DECIMAL_POINT.findall(text))


# Words a person should never have to look up. Formula names (Katch-McArdle,
# Mifflin-St Jeor) stay: they only appear where the plan explains its sources.
JARGON = re.compile(
    r"\b(?:RIR|HIIT|LISS|TDEE|BMR|mesociclos?|descargas?|isquiosurales|metabolismo basal|Navy|"
    r"tracción|aislamiento|series efectivas|recomposición|superávit|suelo calórico|"
    r"progresión doble|perímetros?)\b",
    re.IGNORECASE,
)


def test_spanish_screens_speak_plainly(lived_in: FlaskClient, seeded: SQLAlchemy) -> None:
    for path, text in _pages(lived_in, seeded).items():
        assert not JARGON.search(text), (path, JARGON.findall(text))


def test_the_landing_and_the_questionnaire_speak_plainly(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    del seeded
    texts = {path: client.get(path) for path in ("/", "/registro", "/entrar")}
    _signup(client)
    for number in range(1, 8):
        texts[f"/paso/{number}"] = client.get(f"/cuestionario/paso/{number}")
        _post_step(client, number)
    for path, response in texts.items():
        assert response.status_code == 200, path
        text = _visible(response.get_data(as_text=True))
        assert not JARGON.search(text), (path, JARGON.findall(text))
