"""Split selection and day templates.

Split by available days (§3.7): 2 = full body; 3 = full body for beginners
and intermediates, push/pull/legs for advanced; 4 = upper/lower; 5 =
upper/lower + push/pull/legs (Arnold split for very experienced lifters);
6 = push/pull/legs twice. Each day is a list of slots: a movement pattern, a
role (main, secondary, accessory, isolation) and an optional target muscle.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.engine.enums import MovementPattern as P
from app.engine.enums import MuscleGroup as M
from app.engine.enums import SplitType, TrainingExperience

MAIN = "main"
SECONDARY = "secondary"
ACCESSORY = "accessory"
ISOLATION = "isolation"

ADVANCED = {TrainingExperience.YEARS_2_TO_5, TrainingExperience.OVER_5_YEARS}


@dataclass(frozen=True)
class Slot:
    """A place in a training day to be filled by one exercise."""

    pattern: P
    role: str
    target: M | None = None
    unilateral: bool = False


@dataclass(frozen=True)
class DayTemplate:
    """Name, focus and slots of one training day."""

    name: str
    focus: tuple[M, ...]
    slots: tuple[Slot, ...]


def select_split(days: int, experience: TrainingExperience) -> SplitType:
    """Pick the split family for the available days and experience."""
    if days <= 2:
        return SplitType.FULL_BODY
    if days == 3:
        return SplitType.PUSH_PULL_LEGS if experience in ADVANCED else SplitType.FULL_BODY
    if days == 4:
        return SplitType.UPPER_LOWER
    if days == 5:
        if experience is TrainingExperience.OVER_5_YEARS:
            return SplitType.ARNOLD
        return SplitType.UPPER_LOWER_PPL
    return SplitType.PPL_TWICE


FULL_A = DayTemplate(
    "Cuerpo completo A",
    (M.QUADS, M.CHEST, M.BACK),
    (
        Slot(P.KNEE_DOMINANT, MAIN, M.QUADS),
        Slot(P.HORIZONTAL_PUSH, MAIN, M.CHEST),
        Slot(P.HORIZONTAL_PULL, SECONDARY, M.BACK),
        Slot(P.HIP_DOMINANT, SECONDARY, M.HAMSTRINGS),
        Slot(P.VERTICAL_PUSH, ACCESSORY, M.SHOULDERS),
        Slot(P.CORE, ISOLATION, M.ABS),
    ),
)
FULL_B = DayTemplate(
    "Cuerpo completo B",
    (M.HAMSTRINGS, M.SHOULDERS, M.BACK),
    (
        Slot(P.HIP_DOMINANT, MAIN, M.HAMSTRINGS),
        Slot(P.VERTICAL_PUSH, MAIN, M.SHOULDERS),
        Slot(P.VERTICAL_PULL, SECONDARY, M.BACK),
        Slot(P.KNEE_DOMINANT, SECONDARY, M.QUADS, unilateral=True),
        Slot(P.HORIZONTAL_PUSH, ACCESSORY, M.CHEST),
        Slot(P.ISOLATION, ISOLATION, M.BICEPS),
    ),
)
FULL_C = DayTemplate(
    "Cuerpo completo C",
    (M.QUADS, M.CHEST, M.GLUTES),
    (
        Slot(P.KNEE_DOMINANT, MAIN, M.QUADS),
        Slot(P.HORIZONTAL_PUSH, MAIN, M.CHEST),
        Slot(P.HORIZONTAL_PULL, SECONDARY, M.BACK),
        Slot(P.HIP_DOMINANT, SECONDARY, M.GLUTES),
        Slot(P.ISOLATION, ISOLATION, M.TRICEPS),
        Slot(P.CORE, ISOLATION, M.ABS),
    ),
)
UPPER_A = DayTemplate(
    "Torso A",
    (M.CHEST, M.BACK, M.SHOULDERS),
    (
        Slot(P.HORIZONTAL_PUSH, MAIN, M.CHEST),
        Slot(P.HORIZONTAL_PULL, MAIN, M.BACK),
        Slot(P.VERTICAL_PUSH, SECONDARY, M.SHOULDERS),
        Slot(P.VERTICAL_PULL, SECONDARY, M.BACK),
        Slot(P.ISOLATION, ISOLATION, M.BICEPS),
        Slot(P.ISOLATION, ISOLATION, M.TRICEPS),
    ),
)
LOWER_A = DayTemplate(
    "Pierna A",
    (M.QUADS, M.HAMSTRINGS, M.GLUTES),
    (
        Slot(P.KNEE_DOMINANT, MAIN, M.QUADS),
        Slot(P.HIP_DOMINANT, SECONDARY, M.HAMSTRINGS),
        Slot(P.KNEE_DOMINANT, ACCESSORY, M.GLUTES, unilateral=True),
        Slot(P.ISOLATION, ISOLATION, M.HAMSTRINGS),
        Slot(P.ISOLATION, ISOLATION, M.CALVES),
        Slot(P.CORE, ISOLATION, M.ABS),
    ),
)
UPPER_B = DayTemplate(
    "Torso B",
    (M.SHOULDERS, M.BACK, M.CHEST),
    (
        Slot(P.VERTICAL_PUSH, MAIN, M.SHOULDERS),
        Slot(P.VERTICAL_PULL, MAIN, M.BACK),
        Slot(P.HORIZONTAL_PUSH, SECONDARY, M.CHEST),
        Slot(P.HORIZONTAL_PULL, SECONDARY, M.BACK),
        Slot(P.ISOLATION, ISOLATION, M.SHOULDERS),
        Slot(P.ISOLATION, ISOLATION, M.BICEPS),
        Slot(P.ISOLATION, ISOLATION, M.TRICEPS),
    ),
)
LOWER_B = DayTemplate(
    "Pierna B",
    (M.HAMSTRINGS, M.QUADS, M.GLUTES),
    (
        Slot(P.HIP_DOMINANT, MAIN, M.HAMSTRINGS),
        Slot(P.KNEE_DOMINANT, SECONDARY, M.QUADS),
        Slot(P.HIP_DOMINANT, ACCESSORY, M.GLUTES),
        Slot(P.ISOLATION, ISOLATION, M.QUADS),
        Slot(P.ISOLATION, ISOLATION, M.CALVES),
        Slot(P.CORE, ISOLATION, M.ABS),
    ),
)
PUSH_A = DayTemplate(
    "Empuje A",
    (M.CHEST, M.SHOULDERS, M.TRICEPS),
    (
        Slot(P.HORIZONTAL_PUSH, MAIN, M.CHEST),
        Slot(P.VERTICAL_PUSH, SECONDARY, M.SHOULDERS),
        Slot(P.HORIZONTAL_PUSH, ACCESSORY, M.CHEST),
        Slot(P.ISOLATION, ISOLATION, M.SHOULDERS),
        Slot(P.ISOLATION, ISOLATION, M.TRICEPS),
        Slot(P.ISOLATION, ISOLATION, M.CHEST),
    ),
)
PULL_A = DayTemplate(
    "Tirón A",
    (M.BACK, M.BICEPS, M.SHOULDERS),
    (
        Slot(P.VERTICAL_PULL, MAIN, M.BACK),
        Slot(P.HORIZONTAL_PULL, SECONDARY, M.BACK),
        Slot(P.HORIZONTAL_PULL, ACCESSORY, M.SHOULDERS),
        Slot(P.ISOLATION, ISOLATION, M.BICEPS),
        Slot(P.ISOLATION, ISOLATION, M.BICEPS),
        Slot(P.CORE, ISOLATION, M.ABS),
    ),
)
LEGS_A = DayTemplate(
    "Pierna A",
    (M.QUADS, M.HAMSTRINGS, M.GLUTES),
    (
        Slot(P.KNEE_DOMINANT, MAIN, M.QUADS),
        Slot(P.HIP_DOMINANT, SECONDARY, M.HAMSTRINGS),
        Slot(P.KNEE_DOMINANT, ACCESSORY, M.GLUTES, unilateral=True),
        Slot(P.ISOLATION, ISOLATION, M.HAMSTRINGS),
        Slot(P.ISOLATION, ISOLATION, M.CALVES),
        Slot(P.CORE, ISOLATION, M.ABS),
    ),
)
PUSH_B = DayTemplate(
    "Empuje B",
    (M.SHOULDERS, M.CHEST, M.TRICEPS),
    (
        Slot(P.VERTICAL_PUSH, MAIN, M.SHOULDERS),
        Slot(P.HORIZONTAL_PUSH, SECONDARY, M.CHEST),
        Slot(P.HORIZONTAL_PUSH, ACCESSORY, M.TRICEPS),
        Slot(P.ISOLATION, ISOLATION, M.SHOULDERS),
        Slot(P.ISOLATION, ISOLATION, M.TRICEPS),
        Slot(P.ISOLATION, ISOLATION, M.CHEST),
    ),
)
PULL_B = DayTemplate(
    "Tirón B",
    (M.BACK, M.BICEPS, M.TRAPS),
    (
        Slot(P.HORIZONTAL_PULL, MAIN, M.BACK),
        Slot(P.VERTICAL_PULL, SECONDARY, M.BACK),
        Slot(P.HORIZONTAL_PULL, ACCESSORY, M.BACK, unilateral=True),
        Slot(P.ISOLATION, ISOLATION, M.SHOULDERS),
        Slot(P.ISOLATION, ISOLATION, M.BICEPS),
        Slot(P.ISOLATION, ISOLATION, M.TRAPS),
    ),
)
LEGS_B = DayTemplate(
    "Pierna B",
    (M.HAMSTRINGS, M.GLUTES, M.QUADS),
    (
        Slot(P.HIP_DOMINANT, MAIN, M.HAMSTRINGS),
        Slot(P.KNEE_DOMINANT, SECONDARY, M.QUADS),
        Slot(P.HIP_DOMINANT, ACCESSORY, M.GLUTES),
        Slot(P.ISOLATION, ISOLATION, M.QUADS),
        Slot(P.ISOLATION, ISOLATION, M.CALVES),
        Slot(P.ISOLATION, ISOLATION, M.ADDUCTORS),
    ),
)
CHEST_BACK_A = DayTemplate(
    "Pecho y espalda A",
    (M.CHEST, M.BACK),
    (
        Slot(P.HORIZONTAL_PUSH, MAIN, M.CHEST),
        Slot(P.HORIZONTAL_PULL, MAIN, M.BACK),
        Slot(P.HORIZONTAL_PUSH, SECONDARY, M.CHEST),
        Slot(P.VERTICAL_PULL, SECONDARY, M.BACK),
        Slot(P.ISOLATION, ISOLATION, M.CHEST),
        Slot(P.HORIZONTAL_PULL, ACCESSORY, M.SHOULDERS),
    ),
)
SHOULDERS_ARMS = DayTemplate(
    "Hombros y brazos",
    (M.SHOULDERS, M.BICEPS, M.TRICEPS),
    (
        Slot(P.VERTICAL_PUSH, MAIN, M.SHOULDERS),
        Slot(P.ISOLATION, ISOLATION, M.SHOULDERS),
        Slot(P.ISOLATION, ISOLATION, M.BICEPS),
        Slot(P.ISOLATION, ISOLATION, M.TRICEPS),
        Slot(P.ISOLATION, ISOLATION, M.BICEPS),
        Slot(P.ISOLATION, ISOLATION, M.TRICEPS),
    ),
)
CHEST_BACK_B = DayTemplate(
    "Pecho y espalda B",
    (M.BACK, M.CHEST),
    (
        Slot(P.VERTICAL_PULL, MAIN, M.BACK),
        Slot(P.HORIZONTAL_PUSH, MAIN, M.CHEST),
        Slot(P.HORIZONTAL_PULL, SECONDARY, M.BACK, unilateral=True),
        Slot(P.HORIZONTAL_PUSH, SECONDARY, M.CHEST),
        Slot(P.ISOLATION, ISOLATION, M.CHEST),
        Slot(P.CORE, ISOLATION, M.ABS),
    ),
)

TEMPLATES: dict[SplitType, tuple[DayTemplate, ...]] = {
    SplitType.FULL_BODY: (FULL_A, FULL_B, FULL_C),
    SplitType.UPPER_LOWER: (UPPER_A, LOWER_A, UPPER_B, LOWER_B),
    SplitType.PUSH_PULL_LEGS: (PUSH_A, PULL_A, LEGS_A),
    SplitType.UPPER_LOWER_PPL: (UPPER_A, LOWER_A, PUSH_A, PULL_A, LEGS_A),
    SplitType.ARNOLD: (CHEST_BACK_A, SHOULDERS_ARMS, LEGS_A, CHEST_BACK_B, LEGS_B),
    SplitType.PPL_TWICE: (PUSH_A, PULL_A, LEGS_A, PUSH_B, PULL_B, LEGS_B),
}


def day_templates(split: SplitType, days: int) -> tuple[DayTemplate, ...]:
    """The day templates for ``split``, trimmed or cycled to ``days`` entries."""
    base = TEMPLATES[split]
    if days <= len(base):
        return base[:days]
    return tuple(base[index % len(base)] for index in range(days))
