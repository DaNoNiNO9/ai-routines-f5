"""Request ids and structured log output."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pytest
from flask.testing import FlaskClient

from app.logging_config import resolve_level
from tests.conftest import AppFactory


def test_generated_request_id_is_returned(client: FlaskClient) -> None:
    request_id = client.get("/health").headers["X-Request-ID"]
    assert re.fullmatch(r"[0-9a-f]{12}", request_id)


def test_incoming_request_id_is_preserved_and_truncated(client: FlaskClient) -> None:
    long_id = "x" * 100
    response = client.get("/health", headers={"X-Request-ID": long_id})
    assert response.headers["X-Request-ID"] == "x" * 64


def test_resolve_level_accepts_names_case_insensitively() -> None:
    assert resolve_level("info") == logging.INFO
    assert resolve_level("WARNING") == logging.WARNING


def test_resolve_level_rejects_unknown_names() -> None:
    with pytest.raises(ValueError, match="Unknown LOG_LEVEL 'loud'"):
        resolve_level("loud")


def test_invalid_log_level_in_config_fails_fast(make_app: AppFactory) -> None:
    with pytest.raises(ValueError, match="Unknown LOG_LEVEL"):
        make_app(LOG_LEVEL="verbose")


def test_json_log_file_has_one_object_per_line_with_request_fields(
    make_app: AppFactory, tmp_path: Path
) -> None:
    app = make_app(LOG_TO_FILE=True)
    app.test_client().get("/health?x=1", headers={"X-Request-ID": "log-test-1"})

    lines = (tmp_path / "logs" / "alza.log").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    request_records = [r for r in records if r["name"] == "app.request"]
    assert request_records, records
    record = request_records[-1]
    assert record["message"] == "GET /health?x=1 -> 200"
    assert record["request_id"] == "log-test-1"
    assert record["method"] == "GET"
    assert record["path"] == "/health"
    assert record["level"] == "INFO"
    assert "timestamp" in record


def test_records_outside_requests_use_dashes(make_app: AppFactory, tmp_path: Path) -> None:
    make_app(LOG_TO_FILE=True)
    lines = (tmp_path / "logs" / "alza.log").read_text(encoding="utf-8").splitlines()
    created = [json.loads(line) for line in lines if "Application created" in line]
    assert created
    assert created[-1]["request_id"] == "-"
    assert created[-1]["path"] == "-"
