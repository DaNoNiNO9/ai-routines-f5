"""Flask CLI commands.

    flask seed equipment   Load or update the equipment catalogue.
    flask seed all         Every loader, in dependency order.

Loaders are idempotent; errors abort with a clear message and roll back.
"""

from __future__ import annotations

import logging

import click
from flask import Flask
from flask.cli import AppGroup

from app.extensions import db
from app.seeds.loaders import SeedError, seed_equipment

logger = logging.getLogger(__name__)

seed_cli = AppGroup("seed", help="Load reference data (idempotent).")


def _run_equipment() -> None:
    try:
        result = seed_equipment(db.session)
        db.session.commit()
    except SeedError as exc:
        db.session.rollback()
        logger.exception("Equipment seed failed")
        raise click.ClickException(str(exc)) from exc
    click.echo(f"equipment: {result.created} created, {result.updated} updated")


@seed_cli.command("equipment")
def seed_equipment_command() -> None:
    """Load or update the equipment catalogue."""
    _run_equipment()


@seed_cli.command("all")
def seed_all_command() -> None:
    """Run every loader in dependency order."""
    _run_equipment()


def register_cli(app: Flask) -> None:
    """Attach the command groups to the application."""
    app.cli.add_command(seed_cli)
