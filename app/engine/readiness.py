"""How you arrive at today's session, from what the plate and the bar already know.

Four signals, each worth points: how you slept (asked in one tap when the
session starts), how much of yesterday's target you ate (only if it was logged),
how hard the last session felt, and how many weeks in a row you have been eating
below what you burn. Few points: a normal day. Some: an easy day (load a bit
lower, one more rep in reserve). Many: an easier one. Missing data adds nothing,
so a person who logs little is never pushed into an easy day by default.

The adjustment only touches the first set's suggestion; after that, every set
adjusts itself from how the previous one went (``loads.next_set_load``).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.engine.types import Note


class Sleep(StrEnum):
    """One-tap answer at the start of the session."""

    GOOD = "good"
    OK = "ok"
    BAD = "bad"


class DayKind(StrEnum):
    """What kind of session today should be."""

    NORMAL = "normal"
    EASY = "easy"
    EASIER = "easier"


UNDERFED_HARD = 0.70  # menos del 70 % de lo previsto ayer
UNDERFED_SOFT = 0.85
HARD_SESSION = 5  # fatiga percibida de 1 a 5
LONG_DEFICIT_WEEKS = 8
EASY_FROM = 2
EASIER_FROM = 4
LOAD_FACTOR = {DayKind.NORMAL: 1.0, DayKind.EASY: 0.95, DayKind.EASIER: 0.90}
EXTRA_RIR = {DayKind.NORMAL: 0, DayKind.EASY: 1, DayKind.EASIER: 1}


@dataclass(frozen=True)
class Readiness:
    """Today's verdict and why."""

    kind: DayKind
    load_factor: float
    extra_rir: int
    reasons: tuple[Note, ...]
    points: int

    @property
    def is_easy(self) -> bool:
        """An easy or easier day."""
        return self.kind is not DayKind.NORMAL


def assess(
    sleep: Sleep | None,
    intake_ratio: float | None,
    last_fatigue: int | None,
    deficit_weeks: int,
) -> Readiness:
    """Combine the signals into today's kind of session."""
    points = 0
    reasons: list[Note] = []
    if sleep is Sleep.BAD:
        points += 2
        reasons.append(Note("readiness.sleep_bad"))
    elif sleep is Sleep.OK:
        points += 1
        reasons.append(Note("readiness.sleep_ok"))
    if intake_ratio is not None and intake_ratio < UNDERFED_SOFT:
        points += 2 if intake_ratio < UNDERFED_HARD else 1
        reasons.append(Note("readiness.underfed", params={"pct": round(intake_ratio * 100)}))
    if last_fatigue is not None and last_fatigue >= HARD_SESSION:
        points += 1
        reasons.append(Note("readiness.hard_last_session"))
    if deficit_weeks >= LONG_DEFICIT_WEEKS:
        points += 1
        reasons.append(Note("readiness.long_deficit", params={"weeks": deficit_weeks}))
    if points >= EASIER_FROM:
        kind = DayKind.EASIER
    elif points >= EASY_FROM:
        kind = DayKind.EASY
    else:
        kind = DayKind.NORMAL
    return Readiness(
        kind=kind,
        load_factor=LOAD_FACTOR[kind],
        extra_rir=EXTRA_RIR[kind],
        reasons=tuple(reasons),
        points=points,
    )
