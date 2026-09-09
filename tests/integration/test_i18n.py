"""Locale selection and template translation hooks."""

from __future__ import annotations

from flask.testing import FlaskClient


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
