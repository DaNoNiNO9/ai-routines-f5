"""On-demand help: every «?» opens its own explanation, in both languages."""

from __future__ import annotations

import re

from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy

from tests.integration.test_workout_flow import _with_routine

PAGES = {
    "/panel": {"constancia", "revision"},
    "/nutricion": {"macros"},
    "/diario": {"comida"},
    "/revision": {"revision"},
}


def _pairs(html: str) -> tuple[set[str], set[str]]:
    triggers = set(re.findall(r'data-help="ayuda-([\w-]+)"', html))
    dialogs = set(re.findall(r'<dialog id="ayuda-([\w-]+)"', html))
    return triggers, dialogs


def test_every_help_button_has_its_dialog(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    for path, expected in PAGES.items():
        html = client.get(path).get_data(as_text=True)
        triggers, dialogs = _pairs(html)
        assert expected <= triggers, (path, triggers)
        assert triggers == dialogs, path
        # Sin JavaScript también se abre: el enlace apunta al id del diálogo.
        for key in triggers:
            assert f'href="#ayuda-{key}"' in html


def test_the_session_explains_how_to_log_a_set(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    response = client.post("/entreno/empezar/1")
    html = client.get(response.headers["Location"]).get_data(as_text=True)
    triggers, dialogs = _pairs(html)
    assert "series" in triggers
    assert triggers == dialogs
    assert "cuántas más podrías haber hecho con buena técnica" in html


def test_help_reads_in_english(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _with_routine(client)
    html = client.get("/nutricion?lang=en").get_data(as_text=True)
    assert "What macronutrients are" in html
    assert "Got it" in html
