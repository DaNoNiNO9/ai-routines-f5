"""What the exercise sheet shows: animation frames, video, steps and the person's history.

Media live as static files, not in the database: the two photos of each
exercise (free-exercise-db, public domain) and, for some, a video from wger
(CC-BY-SA 4.0) converted by ``scripts/build_videos.py``. The video's credit
comes from ``static/video/exercises/CREDITS.json``, which that script writes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from flask import current_app
from flask_babel import get_locale

from app.models import Exercise, Profile, User
from app.services import dashboard, workouts

VIDEO_DIR = Path("video") / "exercises"


@dataclass(frozen=True)
class Video:
    """A converted exercise video and who made it."""

    src: str
    poster: str
    author: str
    license: str
    license_url: str
    source: str


@dataclass(frozen=True)
class History:
    """The person's record with one exercise."""

    sessions: int
    best: workouts.ProgressPoint | None
    recent: list[workouts.ProgressPoint]


@lru_cache(maxsize=4)
def _credits(static_folder: str) -> dict[str, dict[str, Any]]:
    path = Path(static_folder) / VIDEO_DIR / "CREDITS.json"
    if not path.exists():
        return {}
    data: dict[str, dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return data


def video_for(exercise: Exercise) -> Video | None:
    """The exercise's video, or ``None`` when wger has none for it."""
    static_folder = str(current_app.static_folder)
    credit = _credits(static_folder).get(exercise.slug)
    if credit is None or not (Path(static_folder) / VIDEO_DIR / f"{exercise.slug}.mp4").exists():
        return None
    return Video(
        src=(VIDEO_DIR / f"{exercise.slug}.mp4").as_posix(),
        poster=(VIDEO_DIR / f"{exercise.slug}.jpg").as_posix(),
        author=str(credit["author"]),
        license=str(credit["license"]),
        license_url=str(credit["license_url"]),
        source=str(credit["source"]),
    )


def steps(exercise: Exercise) -> tuple[list[str], bool]:
    """The how-to as a list of steps, and whether it fell back to English.

    Spanish readers get the short steps written for the app; English readers,
    the original instructions. A Spanish reader only sees English when an
    exercise has no Spanish steps yet, and the sheet says so.
    """
    english = str(get_locale() or "es").startswith("en")
    text = exercise.instructions_en if english else exercise.instructions_es
    fell_back = False
    if not text:
        text = exercise.instructions_en if not english else exercise.instructions_es
        fell_back = bool(text) and not english
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines, fell_back


def history(user: User, exercise: Exercise, recent: int = 5) -> History:
    """Sessions done, best set by estimated max, and the latest ones (newest first)."""
    points = workouts.exercise_progress(user, exercise)
    best = max(points, key=lambda point: (point.est_1rm, point.top_weight), default=None)
    return History(sessions=len(points), best=best, recent=list(reversed(points))[:recent])


def sheet(user: User, exercise: Exercise, profile: Profile | None) -> dict[str, Any]:
    """Everything the exercise sheet template needs."""
    lines, fell_back = steps(exercise)
    record = history(user, exercise)
    start_kg = None
    if record.sessions == 0 and profile is not None:
        start_kg = workouts.first_load(exercise, profile)
    return {
        "exercise": exercise,
        "frames": dashboard.image_frames(exercise),
        "video": video_for(exercise),
        "steps": lines,
        "steps_in_english": fell_back,
        "history": record,
        "start_kg": start_kg,
    }
