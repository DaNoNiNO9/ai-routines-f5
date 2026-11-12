"""Flask CLI commands.

    flask seed equipment   Load or update the equipment catalogue.
    flask seed exercises   Load or update the exercise catalogue (needs equipment).
    flask seed all         Every loader, in dependency order.
    flask privacy reapply-erasures   After restoring a backup, erase again what was erased.
    flask privacy purge-erasures     Forget erasures older than every backup.

Loaders are idempotent; errors abort with a clear message and roll back.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import click
from flask import Flask, current_app
from flask.cli import AppGroup
from sqlalchemy.orm import Session

from app.extensions import db
from app.seeds.loaders import SeedError, SeedResult, seed_equipment, seed_exercises

logger = logging.getLogger(__name__)

seed_cli = AppGroup("seed", help="Load reference data (idempotent).")


def _run(name: str, loader: Callable[[Session], SeedResult]) -> None:
    try:
        result = loader(db.session)
        db.session.commit()
    except SeedError as exc:
        db.session.rollback()
        logger.exception("Seed %s failed", name)
        raise click.ClickException(str(exc)) from exc
    click.echo(f"{name}: {result.created} created, {result.updated} updated")


@seed_cli.command("equipment")
def seed_equipment_command() -> None:
    """Load or update the equipment catalogue."""
    _run("equipment", seed_equipment)


@seed_cli.command("exercises")
def seed_exercises_command() -> None:
    """Load or update the exercise catalogue (run `seed equipment` first)."""
    _run("exercises", seed_exercises)


@seed_cli.command("all")
def seed_all_command() -> None:
    """Run every loader in dependency order."""
    _run("equipment", seed_equipment)
    _run("exercises", seed_exercises)


privacy_cli = AppGroup("privacy", help="RGPD: erasures and backups.")


@privacy_cli.command("reapply-erasures")
def reapply_erasures_command() -> None:
    """Run right after restoring a backup: deletes again what people erased."""
    from app.services.privacy import reapply_erasures

    result = reapply_erasures(current_app.config["ERASURE_LOG_DAYS"])
    click.echo(
        f"accounts deleted again: {result.accounts}, health data deleted again: "
        f"{result.health}, old records purged: {result.purged}"
    )


@privacy_cli.command("purge-erasures")
def purge_erasures_command() -> None:
    """Daily: forget erasures older than every backup that could be restored."""
    from app.services.privacy import purge_erasure_log

    purged = purge_erasure_log(current_app.config["ERASURE_LOG_DAYS"])
    click.echo(f"old records purged: {purged}")


def register_cli(app: Flask) -> None:
    """Attach the command groups to the application."""
    app.cli.add_command(seed_cli)
    app.cli.add_command(privacy_cli)
