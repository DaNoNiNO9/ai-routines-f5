"""Human-readable text for engine notes.

The engine emits ``Note(code, level, params)`` so the web layer can translate
messages; these Spanish templates are the reference wording and are used by
the logs and the tests. Unknown codes render as the code itself, never crash.
"""

from __future__ import annotations

from app.engine.types import Note

TEMPLATES: dict[str, str] = {
    "body_fat.declared": "Porcentaje de grasa declarado ({value} %, método: {method}).",
    "body_fat.navy": (
        "Grasa corporal estimada por el método Navy a partir de tus perímetros: {value} %."
    ),
    "body_fat.navy_invalid": (
        "Los perímetros no permiten estimar la grasa (revisa cuello, cintura y cadera)."
    ),
    "body_fat.unknown": (
        "Sin dato de grasa corporal: la estimación es de baja confianza y se usa Mifflin-St Jeor."
    ),
    "bmr.katch_mcardle": "Metabolismo basal por Katch-McArdle (masa magra {lean_mass_kg} kg).",
    "bmr.mifflin": "Metabolismo basal por Mifflin-St Jeor.",
    "tdee.steps_estimated": "Pasos diarios estimados en {steps} por tu tipo de trabajo ({job}).",
    "tdee.lifestyle_modifier": (
        "Gasto por actividad reducido un {pct} % por sueño corto o estrés alto."
    ),
    "tdee.divergence": (
        "El gasto por componentes ({components} kcal) difiere un {pct} % del método clásico "
        "({classic} kcal): revisa pasos, trabajo o sesiones."
    ),
    "target.deficit": "Déficit del {pct} % sobre el gasto.",
    "target.surplus": "Superávit del {pct} % sobre el gasto.",
    "target.maintenance": "Calorías de mantenimiento.",
    "target.recomposition_not_ideal": (
        "La recomposición no encaja con tu experiencia y grasa actual: se usan calorías de "
        "mantenimiento; valora perder grasa o ganar músculo como objetivo."
    ),
    "target.raised_to_floor": "Calorías subidas al mínimo seguro ({floor} kcal).",
    "target.capped_by_max_loss": "Ritmo limitado a {max_weekly_kg} kg por semana (1 % del peso).",
    "target.date_in_past": "La fecha objetivo ya ha pasado.",
    "target.date_direction_mismatch": (
        "El peso objetivo va en dirección contraria al objetivo elegido."
    ),
    "target.date_unrealistic": (
        "Con este ritmo necesitas {weeks_needed} semanas y tienes {weeks_available}: "
        "fecha realista aproximada {realistic_date}."
    ),
    "target.date_realistic": (
        "Fecha objetivo alcanzable: unas {weeks_needed} semanas de {weeks_available}."
    ),
    "macros.protein_lean_basis": (
        "Proteína calculada sobre masa magra ({per_kg} g/kg de peso total)."
    ),
    "macros.fat_lowered_for_carbs": (
        "Grasa bajada al mínimo para no dejar los carbohidratos por debajo de {floor} g."
    ),
    "macros.deficit_reduced_for_carbs": (
        "Déficit reducido ({kcal} kcal más al día) para mantener al menos {floor} g "
        "de carbohidratos."
    ),
    "macros.calories_raised_for_carbs": (
        "Calorías subidas {kcal} kcal para cubrir el mínimo de carbohidratos ({floor} g)."
    ),
    "meals.protein_per_meal_low": (
        "Con este número de comidas tocan {per_meal} g de proteína por toma; "
        "con {recommended_meals} comidas cada toma superaría los 0,4 g/kg."
    ),
    "cycle.enabled": (
        "Ciclado de carbohidratos: {high} g los días de entreno y {low} g los de descanso."
    ),
    "cycle.low_day_at_floor": "Los días bajos se quedan en el mínimo de {floor} g.",
    "safety.minor": (
        "Menores de 18 años: no se genera plan; consulta con un profesional sanitario."
    ),
    "safety.pregnancy": (
        "Embarazo o lactancia: no se genera plan; consulta con un profesional sanitario."
    ),
    "safety.eating_disorder": (
        "Antecedentes de trastorno de la conducta alimentaria: no se genera plan; "
        "consulta con un profesional sanitario."
    ),
    "safety.underweight": "IMC {bmi}, por debajo de 18,5: no se genera un plan de déficit.",
    "safety.essential_fat": (
        "Grasa corporal en niveles esenciales ({body_fat} %): perder más no es seguro."
    ),
    "safety.deficit_blocked": (
        "Puedes usar el módulo de entrenamiento y un plan de mantenimiento o ganancia; "
        "para perder peso consulta con un profesional sanitario."
    ),
    "safety.below_floor": "Calorías ({calories}) por debajo del mínimo ({floor}).",
    "safety.loss_too_fast": "Pérdida prevista {weekly} kg/semana por encima del máximo {max}.",
    "safety.deficit_while_underweight": "Déficit con IMC bajo.",
    "safety.protein_out_of_range": "Proteína fuera de rango ({per_kg} g/kg).",
    "safety.fat_too_low": "Grasa demasiado baja ({fat_g} g).",
    "safety.negative_macro": "Macronutriente negativo.",
    "safety.macros_mismatch": (
        "Los macros ({energy} kcal) no cuadran con las calorías ({calories})."
    ),
    "routine.no_days": "Sin días de entrenamiento no se puede generar una rutina.",
    "routine.nothing_possible": (
        "Con el material y las limitaciones indicadas no hay ejercicios posibles; "
        "revisa el material o consulta con un profesional."
    ),
    "routine.days_capped": "Se planifican 6 días como máximo; el séptimo es descanso.",
    "routine.split": "Split {split} de {days} días.",
    "routine.mesocycle": (
        "Mesociclo de {weeks} semanas, descarga cada {deload} semanas; RIR por semana {rir}."
    ),
    "routine.double_progression": (
        "Progresión doble: al completar el máximo del rango en todas las series con el RIR "
        "previsto, añade el incremento indicado y vuelve al mínimo del rango."
    ),
    "routine.level_relaxed": (
        "{exercise}: exige más técnica de la habitual para tu experiencia; empieza ligero."
    ),
    "routine.slot_unfilled": (
        "En {day} no hay ejercicio disponible para el patrón {pattern} con tu material "
        "y limitaciones."
    ),
    "routine.pattern_missing": (
        "El patrón {pattern} no se puede cubrir con tu material: añadir {suggestion} lo resolvería."
    ),
    "routine.pull_bias": (
        "Con historial de hombro se programa un 30 % más de tracción que de empuje."
    ),
    "routine.push_pull": "Series de empuje {push} y de tracción {pull} (ratio {ratio}).",
    "routine.time_trimmed": "{day}: series recortadas para encajar en {minutes} minutos.",
    "routine.session_too_long": (
        "{day}: aun recortando, la sesión estimada dura {estimated} min y tienes {budget}; "
        "añade minutos o un día."
    ),
    "routine.volume_scaled_by_time": (
        "Objetivos de volumen reducidos un {pct} % para caber en tus sesiones; "
        "más días o minutos permitirían más series."
    ),
    "routine.pattern_trimmed": (
        "El patrón {pattern} ha quedado fuera esta semana por falta de tiempo."
    ),
    "routine.pattern_not_scheduled": (
        "El patrón {pattern} no entra en esta distribución de días; rota en el siguiente mesociclo."
    ),
    "routine.pattern_blocked_by_injury": (
        "El patrón {pattern} se omite por las lesiones o limitaciones declaradas."
    ),
    "routine.push_pull_unbalanced": (
        "Con tu material no hay suficientes ejercicios de tracción para equilibrar el empuje."
    ),
    "routine.priority_applied": "Volumen extra (+27 %) para {muscles}, compensado en el resto.",
    "routine.priority_slot_added": "Añadido un ejercicio de {muscle} en {day} por ser prioritario.",
    "routine.volume_low": (
        "{muscle}: {planned} series efectivas, por debajo de las {target_min} objetivo "
        "(lo limita el material o el tiempo)."
    ),
    "cardio.not_punishment": (
        "El cardio se programa por su efecto sobre el gasto y la salud, nunca como castigo "
        "por saltarse la dieta."
    ),
    "cardio.deficit_not_covered": (
        "Quedan {kcal} kcal semanales de déficit sin cubrir con actividad: se alarga el plazo "
        "antes que añadir más cardio."
    ),
    "cardio.health_sessions": (
        "{sessions} sesiones suaves de cardio a la semana por salud cardiovascular (opcionales)."
    ),
    "cardio.summary": (
        "Objetivo de {steps} pasos al día, {liss} sesiones LISS y {hiit} HIIT "
        "(unas {kcal} kcal/semana)."
    ),
    "plan.confidence": "Confianza de la estimación: {confidence}.",
}


def render(note: Note) -> str:
    """Spanish text for a note; falls back to the code when unknown or incomplete."""
    template = TEMPLATES.get(note.code)
    if template is None:
        return note.code if not note.params else f"{note.code} {note.params}"
    try:
        return template.format(**note.params)
    except (KeyError, IndexError):
        return f"{note.code} {note.params}"


def render_all(notes: tuple[Note, ...]) -> list[str]:
    """Render every note, prefixed with its level when it is not informational."""
    rendered: list[str] = []
    for note in notes:
        text = render(note)
        rendered.append(text if note.level == "info" else f"[{note.level}] {text}")
    return rendered
