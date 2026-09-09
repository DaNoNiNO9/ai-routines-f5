"""Barrido de perfiles extremos por los tres motores (auditoría, Fase 13).

Los tests de las fases 4-6 comprueban que el motor acierta con datos normales.
Esto comprueba que no se rompe ni dice tonterías con los datos de los bordes:
25 y 350 kg, 100 y 250 cm, 10 y 110 años, 4 % y 60 % de grasa, cero días de
entrenamiento y siete de 240 minutos, todas las lesiones a la vez, sin material,
y series de peso vacías, planas, con ruido o con un hueco de un año.
"""

from __future__ import annotations

import itertools
from datetime import date, timedelta

import pytest

from app.engine import messages, safety
from app.engine.adjustment.rules import decide
from app.engine.adjustment.types import AdjustmentInputs, IntakePoint, WeightPoint
from app.engine.enums import (
    Aggressiveness,
    BodyFatMethod,
    Goal,
    InjuryArea,
    JobActivity,
    MuscleGroup,
    Severity,
    Sex,
    TrainingExperience,
    TrainingLocation,
)
from app.engine.equipment_presets import EQUIPMENT_PRESETS
from app.engine.nutrition import build_nutrition_plan
from app.engine.routines.generator import build_routine
from app.engine.routines.types import InjuryInput, RoutineInputs
from app.engine.types import InputError, NutritionInputs, NutritionPlan
from tests.engine_factories import TODAY
from tests.routine_factories import CATALOGUE

WEIGHTS = (25.0, 40.0, 200.0, 350.0)
HEIGHTS = (100.0, 140.0, 210.0, 250.0)
AGES = (10, 16, 85, 110)
BODY_FATS = (None, 4.0, 60.0)
TRAINING = ((0, 0), (2, 20), (6, 120), (7, 240))
ALL_INJURIES = tuple(InjuryInput(area=area, severity=Severity.SEVERE) for area in InjuryArea)
SEVERITY_ORDER = {Severity.MILD: 1, Severity.MODERATE: 2, Severity.SEVERE: 3}


def _every_note_renders(plan: NutritionPlan | object, problems: list[str]) -> None:
    """Una nota que no encuentra su plantilla se imprime como su código."""
    for note in plan.all_notes():  # type: ignore[union-attr]
        text = messages.render(note)
        if text == note.code or text.startswith(f"{note.code} "):
            problems.append(f"nota sin plantilla o con parámetros que no encajan: {note.code}")


def _check_nutrition(inputs: NutritionInputs, problems: list[str]) -> None:
    plan = build_nutrition_plan(inputs)
    _every_note_renders(plan, problems)
    if plan.is_blocked:
        if not plan.blocked_reasons:
            problems.append("plan bloqueado sin decir por qué")
        return
    macros, target, bmr = plan.macros, plan.target, plan.bmr
    if macros is None or target is None or bmr is None or plan.hydration is None:
        problems.append("plan sin bloquear pero incompleto")
        return
    if min(macros.protein_g, macros.carbs_g, macros.fat_g, macros.calories) < 0:
        problems.append(f"macro negativo: {macros}")
    energy = 4 * macros.protein_g + 4 * macros.carbs_g + 9 * macros.fat_g
    if abs(energy - macros.calories) > 25:
        problems.append(f"los macros suman {energy:.0f} kcal y el plan dice {macros.calories}")
    floor = safety.calorie_floor(inputs.sex, bmr.selected_kcal)
    if macros.calories < floor - 1:
        problems.append(f"calorías {macros.calories} por debajo del suelo {floor:.0f}")
    cap = safety.max_weekly_loss_kg(inputs.weight_kg)
    if -target.expected_weekly_change_kg > cap + 0.02:
        problems.append(
            f"pérdida {-target.expected_weekly_change_kg:.3f} sobre el máximo {cap:.3f}"
        )
    if plan.meals:
        total = sum(meal.calories for meal in plan.meals)
        if abs(total - macros.calories) > 12:
            problems.append(f"las comidas suman {total} y el plan {macros.calories}")
    if plan.hydration.base_ml <= 0 or plan.hydration.training_day_ml < plan.hydration.base_ml:
        problems.append(f"hidratación incoherente: {plan.hydration}")
    if plan.carb_cycle is not None:
        low, high = plan.carb_cycle.low_day, plan.carb_cycle.high_day
        if min(low.carbs_g, high.carbs_g) < 0:
            problems.append("ciclado con carbohidratos negativos")


@pytest.mark.parametrize("goal", list(Goal))
def test_the_nutrition_engine_survives_every_extreme_body(goal: Goal) -> None:
    problems: list[str] = []
    tested = 0
    for index, (weight, height, age, fat, (days, minutes), sex) in enumerate(
        itertools.product(WEIGHTS, HEIGHTS, AGES, BODY_FATS, TRAINING, Sex)
    ):
        inputs = NutritionInputs(
            sex=sex,
            age=age,
            height_cm=height,
            weight_kg=weight,
            goal=goal,
            training_days_per_week=days,
            session_minutes=minutes,
            training_experience=TrainingExperience.NONE,
            job_activity=JobActivity.SEDENTARY,
            sleep_hours=7.0,
            stress_level=3,
            meals_per_day=1 if index % 2 else 8,
            body_fat_pct=fat,
            body_fat_method=BodyFatMethod.VISUAL if fat else BodyFatMethod.NONE,
            daily_steps=0 if index % 2 else 60000,
            aggressiveness=list(Aggressiveness)[index % len(Aggressiveness)],
            today=TODAY,
        )
        tested += 1
        _check_nutrition(inputs, problems)
    assert tested == 1536
    assert problems == []


def test_the_nutrition_engine_rejects_impossible_numbers() -> None:
    base: dict[str, object] = {
        "sex": Sex.FEMALE,
        "age": 30,
        "height_cm": 165.0,
        "weight_kg": 60.0,
        "goal": Goal.FAT_LOSS,
        "training_days_per_week": 3,
        "session_minutes": 60,
        "training_experience": TrainingExperience.NONE,
        "job_activity": JobActivity.SEDENTARY,
        "sleep_hours": 7.0,
        "stress_level": 3,
        "meals_per_day": 4,
        "today": TODAY,
    }
    for field, value in (
        ("age", 9),
        ("age", 111),
        ("height_cm", 99.0),
        ("weight_kg", 24.0),
        ("body_fat_pct", 1.0),
        ("body_fat_pct", 71.0),
        ("daily_steps", -1),
        ("meals_per_day", 0),
        ("session_minutes", 241),
        ("stress_level", 6),
        ("sleep_hours", 17.0),
    ):
        with pytest.raises(InputError):
            NutritionInputs(**{**base, field: value})  # type: ignore[arg-type]


def _check_routine(inputs: RoutineInputs, problems: list[str]) -> None:
    plan = build_routine(inputs, CATALOGUE)
    _every_note_renders(plan, problems)
    if inputs.training_days_per_week == 0 and plan.days:
        problems.append("rutina con días sin días de entrenamiento")
    for day in plan.days:
        if not day.exercises:
            problems.append(f"día {day.index} sin ningún ejercicio")
        names = [item.slug for item in day.exercises]
        if len(names) != len(set(names)):
            problems.append(f"ejercicio repetido en el día {day.index}")
        for item in day.exercises:
            if item.sets <= 0 or item.rep_min <= 0 or item.rep_max < item.rep_min:
                problems.append(f"prescripción imposible: {item.slug}")
            if item.rir_start < item.rir_end or item.rest_seconds <= 0:
                problems.append(f"progresión o descanso imposibles: {item.slug}")
            entry = next(row for row in CATALOGUE if row.slug == item.slug)
            if not entry.equipment <= set(inputs.equipment):
                problems.append(f"{item.slug} pide material que no hay")
            for area, severity in entry.contraindications:
                for injury in inputs.injuries:
                    if (
                        injury.area is area
                        and SEVERITY_ORDER[injury.severity] >= (SEVERITY_ORDER[severity])
                    ):
                        problems.append(f"{item.slug} está contraindicado por {area.value}")


@pytest.mark.parametrize("location", list(TrainingLocation))
def test_the_routine_generator_survives_every_extreme_week(location: TrainingLocation) -> None:
    problems: list[str] = []
    for (days, minutes), experience, injuries, priorities, equipment in itertools.product(
        TRAINING,
        TrainingExperience,
        ((), ALL_INJURIES),
        ((), (MuscleGroup.GLUTES, MuscleGroup.SHOULDERS)),
        (EQUIPMENT_PRESETS[location], frozenset()),
    ):
        _check_routine(
            RoutineInputs(
                sex=Sex.FEMALE,
                goal=Goal.FAT_LOSS,
                training_experience=experience,
                training_days_per_week=days,
                session_minutes=minutes,
                training_location=location,
                equipment=frozenset(equipment),
                weight_kg=40.0,
                injuries=injuries,
                priority_muscles=priorities,
                daily_steps=0,
            ),
            problems,
        )
    assert problems == []


def test_a_day_with_no_possible_exercise_is_dropped_not_left_empty() -> None:
    """Peso corporal en casa y todas las lesiones graves: quedan pocos días, pero llenos."""
    plan = build_routine(
        RoutineInputs(
            sex=Sex.FEMALE,
            goal=Goal.FAT_LOSS,
            training_experience=TrainingExperience.NONE,
            training_days_per_week=6,
            session_minutes=120,
            training_location=TrainingLocation.HOME_BODYWEIGHT,
            equipment=frozenset(EQUIPMENT_PRESETS[TrainingLocation.HOME_BODYWEIGHT]),
            weight_kg=40.0,
            injuries=ALL_INJURIES,
            daily_steps=0,
        ),
        CATALOGUE,
    )
    assert plan.days, "algo se tenía que poder entrenar"
    assert all(day.exercises for day in plan.days)
    assert [day.index for day in plan.days] == list(range(1, len(plan.days) + 1))
    assert plan.days_per_week == len(plan.days)
    assert "routine.days_dropped" in [note.code for note in plan.notes]


def _weights(days: int, start: float, per_day: float, step: int = 1) -> tuple[WeightPoint, ...]:
    return tuple(
        WeightPoint(day=TODAY - timedelta(days=offset), weight_kg=start + per_day * offset)
        for offset in range(0, days, step)
    )


def _intakes(days: int, calories: float, adherence: float | None) -> tuple[IntakePoint, ...]:
    return tuple(
        IntakePoint(day=TODAY - timedelta(days=offset), calories=calories, adherence_pct=adherence)
        for offset in range(days)
    )


WEIGHT_SERIES: dict[str, tuple[WeightPoint, ...]] = {
    "un solo punto": _weights(1, 80.0, 0.0),
    "plana": _weights(30, 80.0, 0.0),
    "bajada suave": _weights(30, 80.0, 0.02),
    "bajada brutal": _weights(30, 80.0, 0.25),
    "subida brutal": _weights(30, 80.0, -0.25),
    "una vez por semana": _weights(60, 80.0, 0.01, step=7),
    "hueco de un año": (
        *_weights(2, 80.0, 0.0),
        WeightPoint(day=TODAY - timedelta(days=400), weight_kg=95.0),
    ),
    "sierra": tuple(
        WeightPoint(
            day=TODAY - timedelta(days=offset), weight_kg=80.0 + (2.5 if offset % 2 else -2.5)
        )
        for offset in range(30)
    ),
    "los dos extremos": (
        WeightPoint(day=TODAY, weight_kg=25.0),
        WeightPoint(day=TODAY - timedelta(days=14), weight_kg=350.0),
    ),
}

INTAKE_SERIES: dict[str, tuple[IntakePoint, ...]] = {
    "sin ingestas": (),
    "cero kcal": _intakes(20, 0.0, 0.0),
    "veinte mil kcal": _intakes(20, 20000.0, 100.0),
    "normal": _intakes(20, 1800.0, 90.0),
    "sin adherencia": _intakes(20, 1800.0, None),
    "adherencia cero": _intakes(20, 1800.0, 0.0),
}


@pytest.mark.parametrize("mode", ["deficit", "surplus", "maintenance"])
def test_the_adjustment_engine_survives_every_kind_of_log(mode: str) -> None:
    problems: list[str] = []
    for weights, intakes, sex, (calories, bmr, tdee, steps) in itertools.product(
        WEIGHT_SERIES.values(),
        INTAKE_SERIES.values(),
        Sex,
        ((500, 1400.0, 1500.0, 0), (10000, 2500.0, 4000.0, 30000)),
    ):
        inputs = AdjustmentInputs(
            sex=sex,
            goal=Goal.FAT_LOSS,
            mode=mode,
            plan_calories=calories,
            plan_started_on=TODAY - timedelta(days=30),
            expected_weekly_change_kg=-0.5 if mode == "deficit" else 0.25,
            bmr_kcal=bmr,
            theoretical_tdee_kcal=tdee,
            weights=weights,
            intakes=intakes,
            today=TODAY,
            steps_target=steps,
            weeks_in_deficit=30,
            stalled_reviews=5,
        )
        decision = decide(inputs)
        codes = [note.code for note in decision.notes]
        for note in decision.notes:
            if messages.render(note) == note.code:
                problems.append(f"nota sin plantilla: {note.code}")
        floor = safety.calorie_floor(sex, bmr)
        if decision.calorie_delta < 0 and decision.new_calories < floor - 1:
            problems.append(f"baja a {decision.new_calories} con el suelo en {floor:.0f}")
        if decision.new_calories != calories + decision.calorie_delta:
            problems.append("el delta no cuadra con las calorías nuevas")
        if decision.calorie_delta > 0 and "adjust.reduce_calories" in codes:
            problems.append("dice que baja las calorías y las sube")
        if decision.calorie_delta < 0 and "adjust.increase_calories" in codes:
            problems.append("dice que sube las calorías y las baja")
        limit = 0.10 if decision.calorie_delta > 0 else 0.05
        if decision.action not in ("diet_break", "refeed") and abs(decision.calorie_delta) > (
            round(calories * limit) + 25
        ):
            problems.append(f"escalón de {decision.calorie_delta} kcal sobre {calories}")
        if not 0 <= decision.new_steps_target <= 30000:
            problems.append(f"pasos fuera de rango: {decision.new_steps_target}")
        if decision.next_review_on < TODAY:
            problems.append("la próxima revisión cae en el pasado")
    assert problems == []


def test_a_review_without_weigh_ins_waits_instead_of_guessing() -> None:
    """Sin pesajes no se inventa una tendencia: se espera y se dice por qué."""
    decision = decide(
        AdjustmentInputs(
            sex=Sex.FEMALE,
            goal=Goal.FAT_LOSS,
            mode="deficit",
            plan_calories=1800,
            plan_started_on=TODAY - timedelta(days=30),
            expected_weekly_change_kg=-0.5,
            bmr_kcal=1400.0,
            theoretical_tdee_kcal=2000.0,
            weights=(),
            today=TODAY,
        )
    )
    assert decision.action == "wait"
    assert not decision.changes_plan
    assert decision.observed_weekly_change_kg is None
    assert "adjust.insufficient_data" in [note.code for note in decision.notes]


def test_a_cut_that_would_break_the_floor_moves_steps_instead() -> None:
    """Si el plan ya está en el suelo, la palanca son los pasos, no bajar más."""
    decision = decide(
        AdjustmentInputs(
            sex=Sex.MALE,
            goal=Goal.MAINTENANCE,
            mode="maintenance",
            plan_calories=1500,
            plan_started_on=date(2026, 8, 1),
            expected_weekly_change_kg=0.0,
            bmr_kcal=1600.0,
            theoretical_tdee_kcal=2200.0,
            weights=_weights(30, 80.0, -0.1),
            today=TODAY,
            steps_target=8000,
        )
    )
    assert decision.calorie_delta == 0
    assert decision.steps_delta > 0
    assert "adjust.floor_reached" in [note.code for note in decision.notes]


def test_the_routine_engine_rejects_impossible_numbers() -> None:
    base: dict[str, object] = {
        "sex": Sex.FEMALE,
        "goal": Goal.FAT_LOSS,
        "training_experience": TrainingExperience.NONE,
        "training_days_per_week": 3,
        "session_minutes": 60,
        "training_location": TrainingLocation.FULL_GYM,
        "equipment": frozenset(EQUIPMENT_PRESETS[TrainingLocation.FULL_GYM]),
    }
    for field, value in (
        ("training_days_per_week", 8),
        ("training_days_per_week", -1),
        ("session_minutes", 241),
        ("weight_kg", 24.0),
        ("weight_kg", 351.0),
        ("daily_steps", 60001),
        ("reported_fatigue", 6),
        ("extra_deficit_kcal_per_day", -1.0),
        ("priority_muscles", (MuscleGroup.GLUTES, MuscleGroup.SHOULDERS, MuscleGroup.BACK)),
    ):
        with pytest.raises(InputError):
            RoutineInputs(**{**base, field: value})  # type: ignore[arg-type]
