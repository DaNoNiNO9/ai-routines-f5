"""Bring a Hevy workout history into Alza.

Hevy exports every set as one CSV row (Profile > Settings > Export & Import
Data > Export Workouts). The import has three steps:

1. ``parse_csv`` reads the file, whatever the unit (kg or lb) and date style,
   and groups the rows into workouts.
2. ``suggest_matches`` pairs each Hevy exercise with one of ours: first a list
   of the usual Hevy names, then a word-overlap guess. The person checks and
   corrects the pairs before anything is written.
3. ``import_history`` stores each workout as a finished session with its sets.
   A workout already imported (same start minute) is skipped, so importing the
   same file twice changes nothing.

Cardio rows (time or distance, no reps) and exercises left unpaired are
skipped and counted. The uploaded file waits in ``instance/imports`` only
between the preview and the confirmation, and is deleted afterwards or after
an hour (it is health data).
"""

from __future__ import annotations

import csv
import io
import logging
import math
import re
import secrets
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import current_app
from sqlalchemy import select

from app.engine.enums import SetType, WorkoutStatus
from app.extensions import db
from app.models import Exercise, SetLog, User, WorkoutSession

logger = logging.getLogger(__name__)

LB_TO_KG = 0.45359237
# Los mismos límites que la base de datos (SetLog): fuera de ellos la serie se omite.
MAX_WEIGHT_KG = 1000
MAX_REPS = 200
MAX_BYTES = 8 * 1024 * 1024
PENDING_SECONDS = 3600
MIN_GUESS_SCORE = 0.5

DATE_FORMATS = (
    "%d %b %Y, %H:%M",  # 14 Nov 2026, 18:30 (la exportación actual)
    "%d %b %Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%b %d, %Y, %I:%M %p",
)

# Nombres habituales de Hevy → nombre inglés de nuestro catálogo.
ALIASES: dict[str, str] = {
    "bench press (barbell)": "Barbell Bench Press - Medium Grip",
    "bench press (dumbbell)": "Dumbbell Bench Press",
    "bench press (smith machine)": "Smith Machine Bench Press",
    "bench press - close grip (barbell)": "Close-Grip Barbell Bench Press",
    "close grip bench press (barbell)": "Close-Grip Barbell Bench Press",
    "incline bench press (barbell)": "Barbell Incline Bench Press - Medium Grip",
    "incline bench press (dumbbell)": "Incline Dumbbell Press",
    "incline bench press (smith machine)": "Smith Machine Incline Bench Press",
    "chest press (machine)": "Machine Bench Press",
    "incline chest press (machine)": "Leverage Incline Chest Press",
    "chest fly (dumbbell)": "Dumbbell Flyes",
    "incline chest fly (dumbbell)": "Incline Dumbbell Flyes",
    "butterfly (pec deck)": "Butterfly",
    "cable fly crossovers": "Cable Crossover",
    "low cable fly crossovers": "Low Cable Crossover",
    "push up": "Pushups",
    "chest dip": "Dips - Chest Version",
    "triceps dip": "Dips - Triceps Version",
    "bench dip": "Bench Dips",
    "squat (barbell)": "Barbell Squat",
    "front squat": "Front Barbell Squat",
    "front squat (barbell)": "Front Barbell Squat",
    "goblet squat": "Goblet Squat",
    "squat (smith machine)": "Smith Machine Squat",
    "squat (dumbbell)": "Dumbbell Squat",
    "squat (bodyweight)": "Bodyweight Squat",
    "hack squat": "Hack Squat",
    "hack squat (machine)": "Hack Squat",
    "leg press (machine)": "Leg Press",
    "leg press": "Leg Press",
    "leg extension (machine)": "Leg Extensions",
    "lying leg curl (machine)": "Lying Leg Curls",
    "seated leg curl (machine)": "Seated Leg Curl",
    "romanian deadlift (barbell)": "Romanian Deadlift",
    "romanian deadlift (dumbbell)": "Stiff-Legged Dumbbell Deadlift",
    "deadlift (barbell)": "Barbell Deadlift",
    "deadlift (trap bar)": "Trap Bar Deadlift",
    "sumo deadlift": "Sumo Deadlift",
    "hip thrust (barbell)": "Barbell Hip Thrust",
    "glute bridge": "Butt Lift (Bridge)",
    "lunge (dumbbell)": "Dumbbell Lunges",
    "lunge (barbell)": "Barbell Lunge",
    "walking lunge": "Bodyweight Walking Lunge",
    "bulgarian split squat": "Split Squat with Dumbbells",
    "step up": "Dumbbell Step Ups",
    "standing calf raise": "Standing Calf Raises",
    "standing calf raise (machine)": "Standing Calf Raises",
    "standing calf raise (barbell)": "Standing Barbell Calf Raise",
    "standing calf raise (dumbbell)": "Standing Dumbbell Calf Raise",
    "standing calf raise (smith machine)": "Smith Machine Calf Raise",
    "seated calf raise": "Seated Calf Raise",
    "calf press (machine)": "Calf Press On The Leg Press Machine",
    "hip abduction (machine)": "Thigh Abductor",
    "hip adduction (machine)": "Thigh Adductor",
    "lat pulldown (cable)": "Wide-Grip Lat Pulldown",
    "lat pulldown - close grip (cable)": "Close-Grip Front Lat Pulldown",
    "lat pulldown (machine)": "Wide-Grip Lat Pulldown",
    "single arm lat pulldown": "One Arm Lat Pulldown",
    "reverse grip lat pulldown (cable)": "Underhand Cable Pulldowns",
    "pull up": "Pullups",
    "chin up": "Chin-Up",
    "pull up (weighted)": "Weighted Pull Ups",
    "pull up (assisted)": "Band Assisted Pull-Up",
    "pull up (band)": "Band Assisted Pull-Up",
    "seated cable row - v grip (cable)": "Seated Cable Rows",
    "seated cable row - bar grip": "Seated Cable Rows",
    "seated row (machine)": "Leverage Iso Row",
    "bent over row (barbell)": "Bent Over Barbell Row",
    "bent over row (dumbbell)": "Bent Over Two-Dumbbell Row",
    "dumbbell row": "One-Arm Dumbbell Row",
    "t bar row": "T-Bar Row with Handle",
    "inverted row": "Inverted Row",
    "face pull": "Face Pull",
    "face pull (cable)": "Face Pull",
    "straight arm lat pulldown (cable)": "Straight-Arm Pulldown",
    "pullover (dumbbell)": "Straight-Arm Dumbbell Pullover",
    "shrug (barbell)": "Barbell Shrug",
    "shrug (dumbbell)": "Dumbbell Shrug",
    "overhead press (barbell)": "Standing Military Press",
    "seated overhead press (barbell)": "Seated Barbell Military Press",
    "shoulder press (dumbbell)": "Dumbbell Shoulder Press",
    "seated shoulder press (dumbbell)": "Dumbbell Shoulder Press",
    "overhead press (dumbbell)": "Standing Dumbbell Press",
    "seated shoulder press (machine)": "Machine Shoulder (Military) Press",
    "shoulder press (machine plates)": "Machine Shoulder (Military) Press",
    "overhead press (smith machine)": "Smith Machine Overhead Shoulder Press",
    "arnold press (dumbbell)": "Arnold Dumbbell Press",
    "lateral raise (dumbbell)": "Side Lateral Raise",
    "lateral raise (cable)": "Standing Low-Pulley Deltoid Raise",
    "front raise (dumbbell)": "Front Dumbbell Raise",
    "rear delt reverse fly (dumbbell)": "Reverse Flyes",
    "rear delt reverse fly (machine)": "Reverse Machine Flyes",
    "rear delt reverse fly (cable)": "Cable Rear Delt Fly",
    "upright row (barbell)": "Upright Barbell Row",
    "push press": "Push Press",
    "bicep curl (barbell)": "Barbell Curl",
    "bicep curl (dumbbell)": "Dumbbell Bicep Curl",
    "bicep curl (cable)": "Standing Biceps Cable Curl",
    "bicep curl (machine)": "Machine Bicep Curl",
    "preacher curl (machine)": "Machine Bicep Curl",
    "ez bar biceps curl": "EZ-Bar Curl",
    "hammer curl (dumbbell)": "Hammer Curls",
    "hammer curl (cable)": "Cable Hammer Curls - Rope Attachment",
    "rope cable curl": "Cable Hammer Curls - Rope Attachment",
    "concentration curl": "Concentration Curls",
    "seated incline curl (dumbbell)": "Incline Dumbbell Curl",
    "reverse curl (barbell)": "Reverse Barbell Curl",
    "zottman curl (dumbbell)": "Zottman Curl",
    "triceps pushdown": "Triceps Pushdown",
    "triceps rope pushdown": "Triceps Pushdown - Rope Attachment",
    "overhead triceps extension (cable)": "Cable Rope Overhead Triceps Extension",
    "triceps extension (dumbbell)": "Standing Dumbbell Triceps Extension",
    "single arm triceps extension (dumbbell)": "Dumbbell One-Arm Triceps Extension",
    "skullcrusher (barbell)": "Lying Triceps Press",
    "skullcrusher (dumbbell)": "Lying Dumbbell Tricep Extension",
    "triceps kickback (dumbbell)": "Tricep Dumbbell Kickback",
    "crunch": "Crunches",
    "cable crunch": "Cable Crunch",
    "hanging leg raise": "Hanging Leg Raise",
    "lying leg raise": "Flat Bench Lying Leg Raise",
    "plank": "Plank",
    "side plank": "Side Bridge",
    "russian twist (weighted)": "Russian Twist",
    "russian twist (bodyweight)": "Russian Twist",
    "ab wheel": "Ab Roller",
    "reverse crunch": "Reverse Crunch",
    "dead bug": "Dead Bug",
    "mountain climber": "Mountain Climbers",
    "back extension (hyperextension)": "Hyperextensions (Back Extensions)",
    "good morning (barbell)": "Good Morning",
    "farmers walk": "Farmer's Walk",
    "kettlebell swing": "One-Arm Kettlebell Swings",
    "box jump": "Front Box Jump",
    "jump squat": "Freehand Jump Squat",
    "cable pull through": "Pull Through",
    "pallof press": "Pallof Press",
    "glute kickback (machine)": "Glute Kickback",
    "cable glute kickback": "One-Legged Cable Kickback",
    "wrist curl (dumbbell)": "Seated Dumbbell Palms-Up Wrist Curl",
}

_STOPWORDS = frozenset(
    {"with", "the", "on", "a", "to", "of", "version", "position", "medium", "grip"}
)
_SYNONYMS = {
    "db": "dumbbell",
    "dumbbells": "dumbbell",
    "curls": "curl",
    "rows": "row",
    "flyes": "fly",
    "flys": "fly",
    "pushups": "pushup",
    "pullups": "pullup",
    "raises": "raise",
    "extensions": "extension",
    "lunges": "lunge",
    "squats": "squat",
    "crunches": "crunch",
    "dips": "dip",
    "machine": "machine",
    "lever": "machine",
    "leverage": "machine",
    "triceps": "tricep",
    "biceps": "bicep",
}


class HevyImportError(Exception):
    """The file is not a Hevy workout export Alza can read."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class HevySet:
    """One strength set as Hevy logged it."""

    exercise: str
    set_index: int
    set_type: SetType
    weight_kg: float
    reps: int
    rir: int | None


@dataclass
class HevyWorkout:
    """One Hevy workout with its sets."""

    title: str
    started_at: datetime
    finished_at: datetime | None
    sets: list[HevySet] = field(default_factory=list)


@dataclass
class ParsedHistory:
    """Everything read from the file, before anything is stored."""

    workouts: list[HevyWorkout]
    exercises: Counter[str]
    skipped_cardio: int
    unit: str
    skipped_invalid: int = 0


@dataclass(frozen=True)
class Match:
    """The exercise of ours a Hevy name was paired with."""

    exercise: Exercise | None
    sure: bool  # de la lista de nombres conocidos (no una suposición)


@dataclass(frozen=True)
class ImportResult:
    """What the import wrote and what it left out."""

    workouts: int
    sets: int
    duplicates: int
    skipped_sets: int


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c)).strip()


def _number(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        number = float(value.strip().replace(",", "."))
    except ValueError:
        return None
    return number if math.isfinite(number) else None  # «nan» e «inf» también son float


def _moment(value: str, zone: ZoneInfo) -> datetime | None:
    text = value.strip()
    for pattern in DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, pattern)  # noqa: DTZ007 - hora local de quien entrena
        except ValueError:
            continue
        return parsed.replace(tzinfo=zone).astimezone(UTC)
    return None


def parse_csv(data: bytes, timezone: str = "Europe/Madrid") -> ParsedHistory:
    """Read a Hevy workout export. Raises ``HevyImportError`` when it is not one."""
    if len(data) > MAX_BYTES:
        raise HevyImportError("too_big")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HevyImportError("not_csv") from exc
    reader = csv.DictReader(io.StringIO(text))
    headers = {(h or "").strip().lower() for h in reader.fieldnames or []}
    if not {"title", "start_time", "exercise_title", "reps"} <= headers:
        raise HevyImportError("not_hevy")
    unit = "lb" if "weight_lbs" in headers and "weight_kg" not in headers else "kg"
    zone = ZoneInfo(timezone)

    workouts: dict[tuple[str, str], HevyWorkout] = {}
    exercises: Counter[str] = Counter()
    cardio = 0
    skipped = 0
    for raw in reader:
        row = {(k or "").strip().lower(): (v or "") for k, v in raw.items()}
        started = _moment(row.get("start_time", ""), zone)
        name = row.get("exercise_title", "").strip()
        if started is None or not name:
            continue
        key = (row.get("title", ""), row.get("start_time", ""))
        workout = workouts.get(key)
        if workout is None:
            finished = _moment(row.get("end_time", ""), zone)
            workout = HevyWorkout(
                title=row.get("title", "").strip()[:120] or "Hevy",
                started_at=started,
                # Un fin anterior al inicio no tiene sentido (y la base lo rechaza).
                finished_at=finished if finished and finished >= started else None,
            )
            workouts[key] = workout
        reps = _number(row.get("reps"))
        if not reps or reps < 1:
            cardio += 1  # tiempo o distancia: no es una serie de fuerza
            continue
        weight = _number(row.get("weight_kg" if unit == "kg" else "weight_lbs")) or 0.0
        if unit == "lb":
            weight *= LB_TO_KG
        if weight < 0 or weight > MAX_WEIGHT_KG or reps > MAX_REPS:
            skipped += 1  # imposible: mejor omitirla que inventar un valor
            continue
        rpe = _number(row.get("rpe"))
        index = _number(row.get("set_index"))
        workout.sets.append(
            HevySet(
                exercise=name,
                set_index=int(index) + 1
                if index is not None and index >= 0
                else len(workout.sets) + 1,
                set_type=SetType.WARMUP
                if row.get("set_type", "").strip().lower() == "warmup"
                else SetType.WORKING,
                weight_kg=round(max(weight, 0.0), 2),
                reps=int(reps),
                rir=max(0, min(10, round(10 - rpe))) if rpe else None,
            )
        )
        exercises[name] += 1
    if not workouts:
        raise HevyImportError("empty")
    ordered = sorted(workouts.values(), key=lambda w: w.started_at)
    return ParsedHistory(
        workouts=ordered,
        exercises=exercises,
        skipped_cardio=cardio,
        unit=unit,
        skipped_invalid=skipped,
    )


def _tokens(name: str) -> set[str]:
    words = re.findall(r"[a-z]+", _plain(name).replace("-", " "))
    return {_SYNONYMS.get(w, w) for w in words if w not in _STOPWORDS}


def suggest_matches(names: list[str]) -> dict[str, Match]:
    """Pair each Hevy exercise name with one of ours, or with nothing."""
    catalogue = db.session.scalars(select(Exercise).where(Exercise.is_active.is_(True))).all()
    by_english = {_plain(e.name_en): e for e in catalogue}
    by_spanish = {_plain(e.name_es): e for e in catalogue}
    tokens = {e.id: _tokens(e.name_en) | _tokens(e.name_es) for e in catalogue}
    matches: dict[str, Match] = {}
    for name in names:
        key = _plain(name)
        alias = ALIASES.get(key)
        known = by_english.get(_plain(alias)) if alias else None
        known = known or by_english.get(key) or by_spanish.get(key)
        if known is not None:
            matches[name] = Match(known, sure=True)
            continue
        wanted = _tokens(name)
        best, best_score = None, 0.0
        for exercise in catalogue:
            theirs = tokens[exercise.id]
            if not wanted or not theirs:
                continue
            score = len(wanted & theirs) / len(wanted | theirs)
            if score > best_score:
                best, best_score = exercise, score
        matches[name] = Match(best if best_score >= MIN_GUESS_SCORE else None, sure=False)
    return matches


def import_history(
    user: User, history: ParsedHistory, pairs: dict[str, Exercise | None]
) -> ImportResult:
    """Store the workouts as finished sessions; already imported ones are skipped."""
    existing = set(
        db.session.scalars(
            select(WorkoutSession.started_at).where(WorkoutSession.user_id == user.id)
        )
    )
    existing_minutes = {moment.replace(second=0, microsecond=0) for moment in existing}
    workouts = sets = duplicates = skipped = 0
    for workout in history.workouts:
        if workout.started_at.replace(second=0, microsecond=0) in existing_minutes:
            duplicates += 1
            continue
        kept = [s for s in workout.sets if pairs.get(s.exercise) is not None]
        skipped += len(workout.sets) - len(kept)
        if not kept:
            continue
        session = WorkoutSession(
            user=user,
            started_at=workout.started_at,
            finished_at=workout.finished_at or workout.started_at,
            status=WorkoutStatus.COMPLETED,
            notes=f"Hevy · {workout.title}",
        )
        db.session.add(session)
        seen: set[tuple[int, int]] = set()
        for item in kept:
            exercise = pairs[item.exercise]
            assert exercise is not None
            index = item.set_index
            while (exercise.id, index) in seen:  # el mismo ejercicio dos veces en un entreno
                index += 1
            seen.add((exercise.id, index))
            session.sets.append(
                SetLog(
                    exercise_id=exercise.id,
                    set_index=index,
                    set_type=item.set_type,
                    reps=item.reps,
                    weight_kg=item.weight_kg,
                    rir=item.rir,
                    completed_at=workout.finished_at or workout.started_at,
                )
            )
            sets += 1
        workouts += 1
    db.session.commit()
    logger.info(
        "Hevy import for user %s: %s workouts, %s sets, %s duplicates",
        user.id,
        workouts,
        sets,
        duplicates,
    )
    return ImportResult(workouts=workouts, sets=sets, duplicates=duplicates, skipped_sets=skipped)


# --- El fichero espera entre la vista previa y la confirmación ---------------


def _pending_dir() -> Path:
    folder = Path(
        current_app.config.get("IMPORTS_DIR") or Path(current_app.instance_path) / "imports"
    )
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def purge_pending(user_id: int | None = None) -> None:
    """Delete files older than an hour, and all of one person's when given."""
    limit = time.time() - PENDING_SECONDS
    for path in _pending_dir().glob("*.csv"):
        owner = path.name.split("-", 1)[0]
        if path.stat().st_mtime < limit or (user_id is not None and owner == str(user_id)):
            path.unlink(missing_ok=True)


def keep_pending(user_id: int, data: bytes) -> str:
    """Hold the upload until it is confirmed; returns its token."""
    purge_pending(user_id)
    token = secrets.token_urlsafe(16)
    (_pending_dir() / f"{user_id}-{token}.csv").write_bytes(data)
    return token


def read_pending(user_id: int, token: str) -> bytes | None:
    """The upload held for this person, if it is still there."""
    if not re.fullmatch(r"[\w-]{10,40}", token or ""):
        return None
    path = _pending_dir() / f"{user_id}-{token}.csv"
    return path.read_bytes() if path.exists() else None
