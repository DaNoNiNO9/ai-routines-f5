"""Translatable labels for the domain enums, shared by forms, templates and services.

The engine stores stable English codes (``app/engine/enums.py``); everything
the user reads comes from here, so a new language only needs a catalogue.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any

from flask import has_app_context
from flask_babel import get_locale
from flask_babel import lazy_gettext as _l

from app.engine.enums import (
    ActivityIntensity,
    Aggressiveness,
    BmrMethod,
    BodyFatMethod,
    Confidence,
    DietPattern,
    EquipmentCategory,
    Goal,
    InjuryArea,
    JobActivity,
    Level,
    MealTiming,
    MovementPattern,
    MuscleGroup,
    Severity,
    Sex,
    SplitType,
    TrainingExperience,
    TrainingLocation,
    TrainingTime,
)

SEX: Mapping[Sex, Any] = {Sex.MALE: _l("Hombre"), Sex.FEMALE: _l("Mujer")}

BODY_FAT_METHOD: Mapping[BodyFatMethod, Any] = {
    BodyFatMethod.NONE: _l("No lo sé"),
    BodyFatMethod.NAVY: _l("Estimado por perímetros (fórmula Navy)"),
    BodyFatMethod.SCALE: _l("Báscula de bioimpedancia"),
    BodyFatMethod.CALIPERS: _l("Plicómetro (pliegues)"),
    BodyFatMethod.DEXA: _l("DEXA"),
    BodyFatMethod.VISUAL: _l("Estimación visual"),
}
# What a person can declare; Navy is computed by the engine from the tape measures.
BODY_FAT_DECLARED: Mapping[BodyFatMethod, Any] = {
    method: text for method, text in BODY_FAT_METHOD.items() if method is not BodyFatMethod.NAVY
}

JOB_ACTIVITY: Mapping[JobActivity, Any] = {
    JobActivity.SEDENTARY: _l("Sedentario"),
    JobActivity.STANDING: _l("De pie"),
    JobActivity.LIGHT_PHYSICAL: _l("Físico ligero"),
    JobActivity.HEAVY_PHYSICAL: _l("Físico duro"),
}
JOB_ACTIVITY_HELP: Mapping[str, Any] = {
    JobActivity.SEDENTARY.value: _l("Oficina, estudio, conducir: casi todo el día sentado."),
    JobActivity.STANDING.value: _l("Comercio, docencia, hostelería: muchas horas de pie."),
    JobActivity.LIGHT_PHYSICAL.value: _l("Reparto, limpieza, almacén: en movimiento continuo."),
    JobActivity.HEAVY_PHYSICAL.value: _l("Construcción, agricultura, cargas pesadas."),
}

ACTIVITY_INTENSITY: Mapping[ActivityIntensity, Any] = {
    ActivityIntensity.LOW: _l("Suave (paseo, yoga)"),
    ActivityIntensity.MODERATE: _l("Moderada (fútbol, natación, bici)"),
    ActivityIntensity.HIGH: _l("Alta (carrera, crossfit, deportes de combate)"),
}

TRAINING_EXPERIENCE: Mapping[TrainingExperience, Any] = {
    TrainingExperience.NONE: _l("Nunca he entrenado con pesas"),
    TrainingExperience.UNDER_6_MONTHS: _l("Menos de 6 meses"),
    TrainingExperience.MONTHS_6_TO_24: _l("Entre 6 meses y 2 años"),
    TrainingExperience.YEARS_2_TO_5: _l("Entre 2 y 5 años"),
    TrainingExperience.OVER_5_YEARS: _l("Más de 5 años"),
}

TRAINING_LOCATION: Mapping[TrainingLocation, Any] = {
    TrainingLocation.FULL_GYM: _l("Gimnasio completo"),
    TrainingLocation.BASIC_GYM: _l("Gimnasio básico"),
    TrainingLocation.HOME_EQUIPMENT: _l("En casa con material"),
    TrainingLocation.HOME_BODYWEIGHT: _l("En casa sin material"),
}
TRAINING_LOCATION_HELP: Mapping[str, Any] = {
    TrainingLocation.FULL_GYM.value: _l("Barras, mancuernas, poleas y máquinas de todo tipo."),
    TrainingLocation.BASIC_GYM.value: _l(
        "Barras, mancuernas, rack, poleas y las máquinas más comunes."
    ),
    TrainingLocation.HOME_EQUIPMENT.value: _l(
        "Mancuernas, bandas, barra de dominadas o banco. Ajusta la lista en el paso siguiente."
    ),
    TrainingLocation.HOME_BODYWEIGHT.value: _l("Solo tu peso corporal."),
}

TRAINING_TIME: Mapping[TrainingTime, Any] = {
    TrainingTime.NONE: _l("Varía o no lo sé"),
    TrainingTime.MORNING: _l("Por la mañana"),
    TrainingTime.MIDDAY: _l("A mediodía"),
    TrainingTime.EVENING: _l("Por la tarde o noche"),
}

GOAL: Mapping[Goal, Any] = {
    Goal.FAT_LOSS: _l("Perder grasa"),
    Goal.RECOMPOSITION: _l("Recomposición"),
    Goal.MUSCLE_GAIN: _l("Ganar músculo"),
    Goal.MAINTENANCE: _l("Mantenimiento"),
    Goal.PERFORMANCE: _l("Rendimiento"),
}
GOAL_HELP: Mapping[str, Any] = {
    Goal.FAT_LOSS.value: _l("Déficit calórico controlado conservando el músculo."),
    Goal.RECOMPOSITION.value: _l(
        "Perder algo de grasa y ganar músculo a la vez; funciona mejor en principiantes."
    ),
    Goal.MUSCLE_GAIN.value: _l("Superávit moderado para ganar masa muscular con poca grasa."),
    Goal.MAINTENANCE.value: _l("Mantener el peso y mejorar hábitos y fuerza."),
    Goal.PERFORMANCE.value: _l("Priorizar la fuerza y el rendimiento; el peso es secundario."),
}

AGGRESSIVENESS: Mapping[Aggressiveness, Any] = {
    Aggressiveness.CONSERVATIVE: _l("Conservador"),
    Aggressiveness.MODERATE: _l("Moderado"),
    Aggressiveness.AGGRESSIVE: _l("Decidido"),
}
AGGRESSIVENESS_HELP: Mapping[str, Any] = {
    Aggressiveness.CONSERVATIVE.value: _l("Cambios pequeños, más fáciles de mantener."),
    Aggressiveness.MODERATE.value: _l("El punto medio recomendado."),
    Aggressiveness.AGGRESSIVE.value: _l(
        "Más rápido, más hambre y fatiga. Los límites de seguridad se aplican igual."
    ),
}

DIET_PATTERN: Mapping[DietPattern, Any] = {
    DietPattern.OMNIVORE: _l("Omnívora"),
    DietPattern.VEGETARIAN: _l("Vegetariana"),
    DietPattern.VEGAN: _l("Vegana"),
    DietPattern.PESCETARIAN: _l("Pescetariana"),
    DietPattern.HALAL: _l("Halal"),
    DietPattern.KOSHER: _l("Kosher"),
}

LEVEL: Mapping[Level, Any] = {
    Level.LOW: _l("Bajo"),
    Level.MEDIUM: _l("Medio"),
    Level.HIGH: _l("Alto"),
}
COOKING_TIME: Mapping[Level, Any] = {
    Level.LOW: _l("Poco (menos de 20 min al día)"),
    Level.MEDIUM: _l("Normal (20-45 min)"),
    Level.HIGH: _l("Bastante (más de 45 min)"),
}

INJURY_AREA: Mapping[InjuryArea, Any] = {
    InjuryArea.SHOULDER: _l("Hombro"),
    InjuryArea.ELBOW: _l("Codo"),
    InjuryArea.WRIST: _l("Muñeca"),
    InjuryArea.NECK: _l("Cuello"),
    InjuryArea.LOWER_BACK: _l("Zona lumbar"),
    InjuryArea.HIP: _l("Cadera"),
    InjuryArea.KNEE: _l("Rodilla"),
    InjuryArea.ANKLE: _l("Tobillo"),
}

SEVERITY: Mapping[Severity, Any] = {
    Severity.MILD: _l("Leve (molesta a veces)"),
    Severity.MODERATE: _l("Moderada (limita algunos ejercicios)"),
    Severity.SEVERE: _l("Grave (en tratamiento o con dolor habitual)"),
}

MUSCLE_GROUP: Mapping[MuscleGroup, Any] = {
    MuscleGroup.CHEST: _l("Pecho"),
    MuscleGroup.BACK: _l("Espalda"),
    MuscleGroup.SHOULDERS: _l("Hombros"),
    MuscleGroup.BICEPS: _l("Bíceps"),
    MuscleGroup.TRICEPS: _l("Tríceps"),
    MuscleGroup.FOREARMS: _l("Antebrazos"),
    MuscleGroup.QUADS: _l("Cuádriceps"),
    MuscleGroup.HAMSTRINGS: _l("Isquiosurales"),
    MuscleGroup.GLUTES: _l("Glúteos"),
    MuscleGroup.CALVES: _l("Gemelos"),
    MuscleGroup.ABS: _l("Abdomen"),
    MuscleGroup.LOWER_BACK: _l("Lumbares"),
    MuscleGroup.TRAPS: _l("Trapecios"),
    MuscleGroup.ADDUCTORS: _l("Aductores"),
}
# Muscles a person can prioritise (the engine accepts up to two).
PRIORITY_MUSCLES: Mapping[MuscleGroup, Any] = {
    muscle: text
    for muscle, text in MUSCLE_GROUP.items()
    if muscle not in {MuscleGroup.FOREARMS, MuscleGroup.LOWER_BACK, MuscleGroup.ADDUCTORS}
}

MOVEMENT_PATTERN: Mapping[MovementPattern, Any] = {
    MovementPattern.HORIZONTAL_PUSH: _l("Empuje horizontal"),
    MovementPattern.VERTICAL_PUSH: _l("Empuje vertical"),
    MovementPattern.HORIZONTAL_PULL: _l("Tracción horizontal"),
    MovementPattern.VERTICAL_PULL: _l("Tracción vertical"),
    MovementPattern.KNEE_DOMINANT: _l("Dominante de rodilla"),
    MovementPattern.HIP_DOMINANT: _l("Dominante de cadera"),
    MovementPattern.CORE: _l("Core"),
    MovementPattern.ISOLATION: _l("Aislamiento"),
}

EQUIPMENT_CATEGORY: Mapping[EquipmentCategory, Any] = {
    EquipmentCategory.BODYWEIGHT: _l("Peso corporal"),
    EquipmentCategory.FREE_WEIGHTS: _l("Peso libre"),
    EquipmentCategory.CABLES: _l("Poleas"),
    EquipmentCategory.MACHINES: _l("Máquinas"),
    EquipmentCategory.ACCESSORIES: _l("Accesorios"),
}

SPLIT_TYPE: Mapping[SplitType, Any] = {
    SplitType.FULL_BODY: _l("Cuerpo completo"),
    SplitType.UPPER_LOWER: _l("Torso / pierna"),
    SplitType.PUSH_PULL_LEGS: _l("Empuje / tracción / pierna"),
    SplitType.UPPER_LOWER_PPL: _l("Torso / pierna + empuje / tracción / pierna"),
    SplitType.ARNOLD: _l("Arnold"),
    SplitType.PPL_TWICE: _l("Empuje / tracción / pierna, dos veces"),
}

CONFIDENCE: Mapping[Confidence, Any] = {
    Confidence.LOW: _l("baja"),
    Confidence.MEDIUM: _l("media"),
    Confidence.HIGH: _l("alta"),
}

BMR_METHOD: Mapping[BmrMethod, Any] = {
    BmrMethod.KATCH_MCARDLE: _l("Katch-McArdle (sobre masa magra)"),
    BmrMethod.MIFFLIN_ST_JEOR: _l("Mifflin-St Jeor"),
    BmrMethod.HARRIS_BENEDICT: _l("Harris-Benedict revisada"),
}

MEAL_TIMING: Mapping[MealTiming, Any] = {
    MealTiming.REGULAR: _l("normal"),
    MealTiming.PRE_WORKOUT: _l("antes de entrenar"),
    MealTiming.POST_WORKOUT: _l("después de entrenar"),
}

VOLUME_STATUS: Mapping[str, Any] = {
    "low": _l("por debajo"),
    "ok": _l("en rango"),
    "high": _l("por encima"),
}

STRESS_LEVEL: Mapping[int, Any] = {
    1: _l("1 · Muy bajo"),
    2: _l("2 · Bajo"),
    3: _l("3 · Normal"),
    4: _l("4 · Alto"),
    5: _l("5 · Muy alto"),
}

ROLE: Mapping[str, Any] = {
    "main": _l("principal"),
    "secondary": _l("secundario"),
    "accessory": _l("accesorio"),
    "isolation": _l("aislamiento"),
}


def choices(mapping: Mapping[Any, Any]) -> list[tuple[Any, Any]]:
    """``(value, label)`` pairs for a WTForms field; enum members become their ``.value``."""
    return [(key.value if isinstance(key, Enum) else key, text) for key, text in mapping.items()]


def label(mapping: Mapping[Any, Any], value: Any) -> str:
    """Text for ``value`` (an enum member or its raw value); the raw value when unknown."""
    if value is None or value == "":
        return ""
    for key, text in mapping.items():
        raw = key.value if isinstance(key, Enum) else key
        if key == value or raw == value:
            return str(text)
    return str(value)


def catalogue_name(row: Any) -> str:
    """Nombre de catálogo (ejercicio o material) en el idioma de la petición.

    Las semillas traen los dos idiomas. Fuera de una petición manda el
    castellano, que es lo que esperan los scripts, los tests y el CSV de datos.
    """
    spanish = str(getattr(row, "name_es", "") or "")
    english = str(getattr(row, "name_en", "") or "")
    if english and has_app_context() and str(get_locale() or "").startswith("en"):
        return english
    return spanish
