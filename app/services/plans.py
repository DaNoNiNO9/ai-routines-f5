"""Bridge between the questionnaire (``Profile``) and the engine, and back to the database.

The engine stays pure: this module builds its inputs from a profile, runs it,
and stores the results as versioned ``Plan`` / ``Routine`` rows plus the full
engine output in ``details`` so any plan can be reproduced or audited later.
Nothing here commits; the caller owns the transaction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.engine import messages
from app.engine.enums import (
    ActivityIntensity,
    AdjustmentReason,
    Aggressiveness,
    BodyFatMethod,
    Goal,
    JobActivity,
    MuscleGroup,
    PlanStatus,
    Sex,
    TrainingExperience,
    TrainingLocation,
    TrainingTime,
)
from app.engine.nutrition import build_nutrition_plan
from app.engine.routines.cardio import steps_target as default_steps_target
from app.engine.routines.catalog import exercise_from_dict
from app.engine.routines.generator import build_routine
from app.engine.routines.types import ExerciseInfo, InjuryInput, RoutineInputs, RoutinePlan
from app.engine.types import Note, NutritionInputs, NutritionPlan, _jsonable
from app.extensions import db
from app.labels import SPLIT_TYPE
from app.models import (
    Exercise,
    Meal,
    Plan,
    PlanAdjustment,
    Profile,
    Routine,
    RoutineDay,
    RoutineExercise,
    User,
)
from app.models.base import utcnow

logger = logging.getLogger(__name__)

DAY_NOTES_MAX = 300
EXERCISE_NOTES_MAX = 200


@dataclass(frozen=True)
class GenerationResult:
    """What a generation run produced (rows are flushed, not committed)."""

    profile: Profile
    nutrition: NutritionPlan
    plan: Plan | None
    routine_plan: RoutinePlan | None
    routine: Routine | None

    @property
    def is_blocked(self) -> bool:
        """Whether safety stopped the nutrition plan (then there is no routine either)."""
        return self.plan is None


def nutrition_inputs(profile: Profile, today: date) -> NutritionInputs:
    """Engine inputs for a profile version (``InputError`` if a value is impossible)."""
    return NutritionInputs(
        sex=Sex(profile.sex),
        age=profile.age_on(today),
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
        goal=Goal(profile.goal),
        training_days_per_week=profile.training_days_per_week,
        session_minutes=profile.session_minutes,
        training_experience=TrainingExperience(profile.training_experience),
        job_activity=JobActivity(profile.job_activity),
        sleep_hours=profile.sleep_hours,
        stress_level=profile.stress_level,
        meals_per_day=profile.meals_per_day,
        neck_cm=profile.neck_cm,
        waist_cm=profile.waist_cm,
        hip_cm=profile.hip_cm,
        body_fat_pct=profile.body_fat_pct,
        body_fat_method=BodyFatMethod(profile.body_fat_method),
        daily_steps=profile.daily_steps,
        other_activity_sessions_per_week=profile.other_activity_sessions_per_week,
        other_activity_minutes=profile.other_activity_minutes,
        other_activity_intensity=(
            ActivityIntensity(profile.other_activity_intensity)
            if profile.other_activity_intensity
            else None
        ),
        aggressiveness=Aggressiveness(profile.aggressiveness),
        target_weight_kg=profile.target_weight_kg,
        target_date=profile.target_date,
        today=today,
        training_time=TrainingTime(profile.training_time),
        wants_carb_cycling=profile.wants_carb_cycling,
        is_pregnant_or_breastfeeding=profile.is_pregnant_or_breastfeeding,
        has_eating_disorder_history=profile.has_eating_disorder_history,
    )


def uncovered_deficit_kcal(nutrition: NutritionPlan) -> float:
    """Daily deficit the diet could not deliver because the calorie floor stopped it.

    Only the floor counts: the maximum-loss cap is a safety limit, so cardio
    must never be added to get around it.
    """
    target = nutrition.target
    if target is None or target.mode != "deficit":
        return 0.0
    if not any(note.code == "target.raised_to_floor" for note in target.notes):
        return 0.0
    wanted = target.fraction * target.maintenance_kcal
    achieved = -target.daily_balance_kcal
    return max(0.0, round(wanted - achieved, 1))


def routine_inputs(
    profile: Profile, equipment_codes: frozenset[str], nutrition: NutritionPlan | None
) -> RoutineInputs:
    """Routine-generator inputs for a profile and the equipment the user owns."""
    return RoutineInputs(
        sex=Sex(profile.sex),
        goal=Goal(profile.goal),
        training_experience=TrainingExperience(profile.training_experience),
        training_days_per_week=profile.training_days_per_week,
        session_minutes=profile.session_minutes,
        training_location=TrainingLocation(profile.training_location),
        equipment=equipment_codes,
        weight_kg=profile.weight_kg,
        injuries=tuple(InjuryInput(injury.area, injury.severity) for injury in profile.injuries),
        priority_muscles=tuple(MuscleGroup(m) for m in profile.priority_muscles[:2]),
        disliked_exercises=frozenset(profile.disliked_exercises),
        preferred_exercises=frozenset(profile.preferred_exercises),
        daily_steps=profile.daily_steps,
        extra_deficit_kcal_per_day=uncovered_deficit_kcal(nutrition) if nutrition else 0.0,
    )


def exercise_info(row: Exercise, slug_by_id: dict[int, str]) -> ExerciseInfo:
    """``ExerciseInfo`` for a catalogue row (alternatives resolved through ``slug_by_id``)."""
    return exercise_from_dict(
        {
            "slug": row.slug,
            "name_es": row.name_es,
            "primary_muscle": row.primary_muscle.value,
            "secondary_muscles": list(row.secondary_muscles),
            "movement_pattern": row.movement_pattern.value,
            "mechanic": row.mechanic.value,
            "force": row.force.value,
            "technical_level": row.technical_level.value,
            "equipment": sorted(row.equipment_codes),
            "contraindications": list(row.contraindications),
            "is_unilateral": row.is_unilateral,
            "is_bodyweight": row.is_bodyweight,
            "alternatives": [
                {"slug": slug_by_id[alt.alternative_id]}
                for alt in row.alternatives
                if alt.alternative_id in slug_by_id
            ],
        }
    )


def load_catalogue() -> tuple[list[ExerciseInfo], dict[str, Exercise]]:
    """Active exercises as the generator sees them, plus the rows by slug."""
    rows = (
        db.session.scalars(
            select(Exercise)
            .where(Exercise.is_active.is_(True))
            .options(selectinload(Exercise.equipment), selectinload(Exercise.alternatives))
            .order_by(Exercise.id)
        )
        .unique()
        .all()
    )
    slug_by_id = {row.id: row.slug for row in rows}
    return [exercise_info(row, slug_by_id) for row in rows], {row.slug: row for row in rows}


def active_plan(user: User) -> Plan | None:
    """The plan in force for ``user`` (at most one)."""
    return db.session.scalar(
        select(Plan)
        .where(Plan.user_id == user.id, Plan.status == PlanStatus.ACTIVE)
        .order_by(Plan.version.desc())
    )


def active_routine(user: User) -> Routine | None:
    """The routine in force for ``user`` (at most one).

    Trae ya los días con sus ejercicios: casi todo el que pide la rutina los
    pinta, y sin esto son treinta consultas para dibujar una semana.
    """
    return db.session.scalar(
        select(Routine)
        .where(Routine.user_id == user.id, Routine.status == PlanStatus.ACTIVE)
        .options(
            selectinload(Routine.days)
            .selectinload(RoutineDay.exercises)
            .selectinload(RoutineExercise.exercise)
        )
        .order_by(Routine.version.desc())
    )


def _next_version(model: type[Plan] | type[Routine], user: User) -> int:
    current = db.session.scalar(select(func.max(model.version)).where(model.user_id == user.id))
    return (current or 0) + 1


def messages_for(notes: tuple[Note, ...]) -> list[dict[str, str]]:
    """Rendered text (with level) for engine notes, in the active language."""
    return [{"level": note.level, "text": messages.render(note)} for note in notes]


def _stored_notes(notes: tuple[Note, ...]) -> list[dict[str, Any]]:
    """The notes themselves, so they can be rendered again in another language."""
    return [
        {"code": note.code, "level": note.level, "params": _jsonable(note.params)} for note in notes
    ]


def _join_notes(notes: tuple[Note, ...], limit: int) -> str | None:
    if not notes:
        return None
    text = " ".join(messages.render(note) for note in notes)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def persist_plan(
    user: User,
    profile: Profile,
    inputs: NutritionInputs,
    nutrition: NutritionPlan,
    today: date,
    *,
    reason: AdjustmentReason | None = None,
    explanation: str | None = None,
    data: dict[str, Any] | None = None,
    steps_target: int | None = None,
    observed_weekly_change_kg: float | None = None,
    observed_tdee_kcal: float | None = None,
    steps_delta: int | None = None,
) -> Plan:
    """Store a finished nutrition plan as the new active version (previous one superseded).

    Without ``reason`` the audit row says ``initial`` (first plan) or
    ``profile_change``; the review passes the engine's reason and decision.
    """
    if (
        nutrition.is_blocked
        or nutrition.bmr is None
        or nutrition.expenditure is None
        or nutrition.target is None
        or nutrition.macros is None
        or nutrition.hydration is None
    ):
        raise ValueError("only a complete nutrition plan can be persisted")
    previous = active_plan(user)
    details = nutrition.to_dict()
    details["messages"] = messages_for(nutrition.all_notes())
    details["all_notes"] = _stored_notes(nutrition.all_notes())
    if steps_target is not None:
        details["steps_target"] = steps_target
    elif previous is not None and isinstance(previous.details.get("steps_target"), int):
        details["steps_target"] = previous.details["steps_target"]
    plan = Plan(
        user=user,
        profile=profile,
        version=_next_version(Plan, user),
        status=PlanStatus.ACTIVE,
        goal=profile.goal,
        starts_on=today,
        calorie_target=nutrition.macros.calories,
        protein_g=nutrition.macros.protein_g,
        carbs_g=nutrition.macros.carbs_g,
        fat_g=nutrition.macros.fat_g,
        fiber_g=nutrition.macros.fiber_g,
        water_ml=nutrition.hydration.base_ml,
        bmr_kcal=nutrition.bmr.selected_kcal,
        tdee_kcal=nutrition.expenditure.maintenance_kcal,
        bmr_method=nutrition.bmr.method,
        confidence=nutrition.confidence,
        inputs_snapshot=_jsonable(inputs),
        details=details,
    )
    for slot in nutrition.meals:
        plan.meals.append(
            Meal(
                position=slot.position,
                name=slot.name,
                timing=slot.timing,
                calories=slot.calories,
                protein_g=slot.protein_g,
                carbs_g=slot.carbs_g,
                fat_g=slot.fat_g,
            )
        )
    if previous is not None:
        previous.status = PlanStatus.SUPERSEDED
        previous.superseded_at = utcnow()
        previous.ends_on = today
    db.session.add(plan)
    db.session.flush()

    target = nutrition.target
    default_explanation = messages.render(
        Note(f"target.{target.mode}", params={"pct": round(target.fraction * 100, 1)})
    )
    db.session.add(
        PlanAdjustment(
            user=user,
            plan=plan,
            previous_plan=previous,
            reason=reason
            or (AdjustmentReason.INITIAL if previous is None else AdjustmentReason.PROFILE_CHANGE),
            expected_weekly_change_kg=target.expected_weekly_change_kg,
            observed_weekly_change_kg=observed_weekly_change_kg,
            observed_tdee_kcal=observed_tdee_kcal,
            calorie_delta=(
                None if previous is None else plan.calorie_target - previous.calorie_target
            ),
            steps_delta=steps_delta,
            explanation=explanation or f"{plan.calorie_target} kcal. {default_explanation}",
            data=data or {"mode": target.mode, "fraction": target.fraction},
        )
    )
    logger.info("Plan v%s stored for user %s (%s kcal)", plan.version, user.id, plan.calorie_target)
    return plan


def persist_routine(
    user: User,
    profile: Profile,
    inputs: RoutineInputs,
    routine_plan: RoutinePlan,
    today: date,
    by_slug: dict[str, Exercise],
) -> Routine:
    """Store a generated routine as the new active version (previous one superseded)."""
    if routine_plan.is_blocked or routine_plan.split_type is None:
        raise ValueError("only a complete routine can be persisted")
    previous = active_routine(user)
    details = routine_plan.to_dict()
    details["messages"] = messages_for(routine_plan.all_notes())
    details["all_notes"] = _stored_notes(routine_plan.all_notes())
    routine = Routine(
        user=user,
        profile=profile,
        version=_next_version(Routine, user),
        name=f"{SPLIT_TYPE[routine_plan.split_type]} · {routine_plan.days_per_week} días",
        split_type=routine_plan.split_type,
        days_per_week=routine_plan.days_per_week,
        mesocycle_weeks=routine_plan.mesocycle_weeks,
        deload_every_weeks=routine_plan.deload_every_weeks,
        status=PlanStatus.ACTIVE,
        starts_on=today,
        inputs_snapshot=_jsonable(inputs),
        details=details,
    )
    for day in routine_plan.days:
        day_row = RoutineDay(
            day_index=day.index,
            name=day.name,
            focus=[muscle.value for muscle in day.focus],
            estimated_minutes=day.estimated_minutes,
            notes=_join_notes(day.notes, DAY_NOTES_MAX),
        )
        for position, exercise in enumerate(day.exercises, start=1):
            day_row.exercises.append(
                RoutineExercise(
                    exercise=by_slug[exercise.slug],
                    position=position,
                    sets=exercise.sets,
                    rep_min=exercise.rep_min,
                    rep_max=exercise.rep_max,
                    rir_start=exercise.rir_start,
                    rir_end=exercise.rir_end,
                    rest_seconds=exercise.rest_seconds,
                    tempo=exercise.tempo,
                    load_increment_kg=exercise.load_increment_kg,
                    notes=_join_notes(exercise.notes, EXERCISE_NOTES_MAX),
                )
            )
        routine.days.append(day_row)
    if previous is not None:
        previous.status = PlanStatus.SUPERSEDED
        previous.superseded_at = utcnow()
    db.session.add(routine)
    db.session.flush()
    logger.info("Routine v%s stored for user %s (%s)", routine.version, user.id, routine.split_type)
    return routine


def generate_for_profile(user: User, profile: Profile, today: date) -> GenerationResult:
    """Run both engines for ``profile`` and store whatever they produce.

    A blocked nutrition plan (safety hard stop or forbidden deficit) stores
    nothing: the caller shows the reasons and the person changes the answers.
    A blocked routine (nothing possible with that equipment) still keeps the
    nutrition plan.

    Raises:
        InputError: A profile value the engine cannot work with (should have
            been caught by the forms).
        SafetyError: The finished plan violated a hard limit (a bug upstream).
    """
    n_inputs = nutrition_inputs(profile, today)
    nutrition = build_nutrition_plan(n_inputs)
    if nutrition.is_blocked:
        logger.info(
            "Nutrition plan blocked for user %s: %s",
            user.id,
            ", ".join(note.code for note in nutrition.blocked_reasons),
        )
        return GenerationResult(profile, nutrition, None, None, None)

    plan = persist_plan(user, profile, n_inputs, nutrition, today)
    catalogue, by_slug = load_catalogue()
    r_inputs = routine_inputs(profile, frozenset(item.code for item in user.equipment), nutrition)
    routine_plan = build_routine(r_inputs, catalogue)
    routine: Routine | None = None
    if routine_plan.is_blocked:
        logger.info(
            "Routine blocked for user %s: %s",
            user.id,
            ", ".join(note.code for note in routine_plan.blocked_reasons),
        )
    else:
        routine = persist_routine(user, profile, r_inputs, routine_plan, today, by_slug)
        plan.routine = routine
    steps = (
        routine_plan.cardio.daily_steps_target
        if routine_plan.cardio is not None
        else default_steps_target(profile.daily_steps, profile.goal)
    )
    plan.details = {**plan.details, "steps_target": steps}
    return GenerationResult(profile, nutrition, plan, routine_plan, routine)


def messages_of(details: dict[str, Any]) -> list[dict[str, str]]:
    """Explanations of a stored plan or routine, in the language of this request.

    The notes are kept as ``code`` plus ``params`` so they can be rendered
    again: a plan generated in Spanish reads in English for an English user.
    Rows written before that (or with a malformed note) fall back to the text
    frozen at generation time.
    """
    raw = details.get("all_notes")
    if isinstance(raw, list):
        rendered: list[dict[str, str]] = []
        for item in raw:
            if not isinstance(item, dict) or "code" not in item:
                continue
            note = Note(
                code=str(item["code"]),
                level=str(item.get("level", "info")),
                params=item.get("params") or {},
            )
            rendered.append({"level": note.level, "text": messages.render(note)})
        if rendered:
            return rendered
    stored = details.get("messages", [])
    return [item for item in stored if isinstance(item, dict) and "text" in item]
