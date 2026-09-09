"""Human-readable text for engine notes.

The engine emits ``Note(code, level, params)`` so the web layer can translate
messages; these Spanish templates are the reference wording and are used by
the logs and the tests. Unknown codes render as the code itself, never crash.

Translation without dragging Flask in here: ``translator`` is a plain function
that the application replaces at start-up (see ``app.i18n``). Left alone it
returns the Spanish text, which is what the engine tests and the logs expect.
The strings reach the catalogue through ``scripts/babel_engine.py``.

Placeholders are printf-style with names (``%(pct)s``) and a literal percent
is written ``%%``, like every other string in the catalogue. Braces would
read better here, but Babel flags any msgid where a percent is followed by a
space and a conversion letter (``% sobre`` looks like ``%s``) and then
refuses to compile a catalogue that mixes both formats.
"""

from __future__ import annotations

from collections.abc import Callable

from app.engine.types import Note


def _as_written(text: str) -> str:
    """Default translator: the reference Spanish wording."""
    return text


translator: Callable[[str], str] = _as_written

TEMPLATES: dict[str, str] = {
    "body_fat.declared": "Porcentaje de grasa declarado (%(value)s %%, método: %(method)s).",
    "body_fat.navy": (
        "Grasa corporal estimada por el método Navy a partir de tus perímetros: %(value)s %%."
    ),
    "body_fat.navy_invalid": (
        "Los perímetros no permiten estimar la grasa (revisa cuello, cintura y cadera)."
    ),
    "body_fat.unknown": (
        "Sin dato de grasa corporal: la estimación es de baja confianza y se usa Mifflin-St Jeor."
    ),
    "bmr.katch_mcardle": "Metabolismo basal por Katch-McArdle (masa magra %(lean_mass_kg)s kg).",
    "bmr.mifflin": "Metabolismo basal por Mifflin-St Jeor.",
    "tdee.steps_estimated": (
        "Pasos diarios estimados en %(steps)s por tu tipo de trabajo (%(job)s)."
    ),
    "tdee.lifestyle_modifier": (
        "Gasto por actividad reducido un %(pct)s %% por sueño corto o estrés alto."
    ),
    "tdee.divergence": (
        "El gasto por componentes (%(components)s kcal) difiere un %(pct)s %% del método clásico "
        "(%(classic)s kcal): revisa pasos, trabajo o sesiones."
    ),
    "target.deficit": "Déficit del %(pct)s %% sobre el gasto.",
    "target.surplus": "Superávit del %(pct)s %% sobre el gasto.",
    "target.maintenance": "Calorías de mantenimiento.",
    "target.recomposition_not_ideal": (
        "La recomposición no encaja con tu experiencia y grasa actual: se usan calorías de "
        "mantenimiento; valora perder grasa o ganar músculo como objetivo."
    ),
    "target.raised_to_floor": "Calorías subidas al mínimo seguro (%(floor)s kcal).",
    "target.capped_by_max_loss": (
        "Ritmo limitado a %(max_weekly_kg)s kg por semana (1 %% del peso)."
    ),
    "target.date_in_past": "La fecha objetivo ya ha pasado.",
    "target.date_direction_mismatch": (
        "El peso objetivo va en dirección contraria al objetivo elegido."
    ),
    "target.date_unrealistic": (
        "Con este ritmo necesitas %(weeks_needed)s semanas y tienes %(weeks_available)s: fecha "
        "realista aproximada %(realistic_date)s."
    ),
    "target.date_realistic": (
        "Fecha objetivo alcanzable: unas %(weeks_needed)s semanas de %(weeks_available)s."
    ),
    "macros.protein_lean_basis": (
        "Proteína calculada sobre masa magra (%(per_kg)s g/kg de peso total)."
    ),
    "macros.fat_lowered_for_carbs": (
        "Grasa bajada al mínimo para no dejar los carbohidratos por debajo de %(floor)s g."
    ),
    "macros.deficit_reduced_for_carbs": (
        "Déficit reducido (%(kcal)s kcal más al día) para mantener al menos %(floor)s g de "
        "carbohidratos."
    ),
    "macros.calories_raised_for_carbs": (
        "Calorías subidas %(kcal)s kcal para cubrir el mínimo de carbohidratos (%(floor)s g)."
    ),
    "meals.protein_per_meal_low": (
        "Con este número de comidas tocan %(per_meal)s g de proteína por toma; con "
        "%(recommended_meals)s comidas cada toma superaría los 0,4 g/kg."
    ),
    "cycle.enabled": (
        "Ciclado de carbohidratos: %(high)s g los días de entreno y %(low)s g los de descanso."
    ),
    "cycle.low_day_at_floor": "Los días bajos se quedan en el mínimo de %(floor)s g.",
    "safety.minor": "Menores de 18 años: no se genera plan; consulta con un profesional sanitario.",
    "safety.pregnancy": (
        "Embarazo o lactancia: no se genera plan; consulta con un profesional sanitario."
    ),
    "safety.eating_disorder": (
        "Antecedentes de trastorno de la conducta alimentaria: no se genera plan; consulta con un "
        "profesional sanitario."
    ),
    "safety.underweight": "IMC %(bmi)s, por debajo de 18,5: no se genera un plan de déficit.",
    "safety.essential_fat": (
        "Grasa corporal en niveles esenciales (%(body_fat)s %%): perder más no es seguro."
    ),
    "safety.deficit_blocked": (
        "Puedes usar el módulo de entrenamiento y un plan de mantenimiento o ganancia; para perder "
        "peso consulta con un profesional sanitario."
    ),
    "safety.below_floor": "Calorías (%(calories)s) por debajo del mínimo (%(floor)s).",
    "safety.loss_too_fast": "Pérdida prevista %(weekly)s kg/semana por encima del máximo %(max)s.",
    "safety.deficit_while_underweight": "Déficit con IMC bajo.",
    "safety.protein_out_of_range": "Proteína fuera de rango (%(per_kg)s g/kg).",
    "safety.fat_too_low": "Grasa demasiado baja (%(fat_g)s g).",
    "safety.negative_macro": "Macronutriente negativo.",
    "safety.macros_mismatch": (
        "Los macros (%(energy)s kcal) no cuadran con las calorías (%(calories)s)."
    ),
    "routine.no_days": "Sin días de entrenamiento no se puede generar una rutina.",
    "routine.nothing_possible": (
        "Con el material y las limitaciones indicadas no hay ejercicios posibles; revisa el "
        "material o consulta con un profesional."
    ),
    "routine.days_capped": "Se planifican 6 días como máximo; el séptimo es descanso.",
    "routine.split": "Split %(split)s de %(days)s días.",
    "routine.mesocycle": (
        "Mesociclo de %(weeks)s semanas, descarga cada %(deload)s semanas; RIR por semana %(rir)s."
    ),
    "routine.double_progression": (
        "Progresión doble: al completar el máximo del rango en todas las series con el RIR "
        "previsto, añade el incremento indicado y vuelve al mínimo del rango."
    ),
    "routine.level_relaxed": (
        "%(exercise)s: exige más técnica de la habitual para tu experiencia; empieza ligero."
    ),
    "routine.slot_unfilled": (
        "En %(day)s no hay ejercicio disponible para el patrón %(pattern)s con tu material y "
        "limitaciones."
    ),
    "routine.pattern_missing": (
        "El patrón %(pattern)s no se puede cubrir con tu material: añadir %(suggestion)s lo "
        "resolvería."
    ),
    "routine.pull_bias": (
        "Con historial de hombro se programa un 30 %% más de tracción que de empuje."
    ),
    "routine.push_pull": "Series de empuje %(push)s y de tracción %(pull)s (ratio %(ratio)s).",
    "routine.time_trimmed": "%(day)s: series recortadas para encajar en %(minutes)s minutos.",
    "routine.session_too_long": (
        "%(day)s: aun recortando, la sesión estimada dura %(estimated)s min y tienes %(budget)s; "
        "añade minutos o un día."
    ),
    "routine.volume_scaled_by_time": (
        "Objetivos de volumen reducidos un %(pct)s %% para caber en tus sesiones; más días o "
        "minutos permitirían más series."
    ),
    "routine.pattern_trimmed": (
        "El patrón %(pattern)s ha quedado fuera esta semana por falta de tiempo."
    ),
    "routine.pattern_not_scheduled": (
        "El patrón %(pattern)s no entra en esta distribución de días; rota en el siguiente "
        "mesociclo."
    ),
    "routine.pattern_blocked_by_injury": (
        "El patrón %(pattern)s se omite por las lesiones o limitaciones declaradas."
    ),
    "routine.push_pull_unbalanced": (
        "Con tu material no hay suficientes ejercicios de tracción para equilibrar el empuje."
    ),
    "routine.priority_applied": "Volumen extra (+27 %%) para %(muscles)s, compensado en el resto.",
    "routine.priority_slot_added": (
        "Añadido un ejercicio de %(muscle)s en %(day)s por ser prioritario."
    ),
    "routine.volume_low": (
        "%(muscle)s: %(planned)s series efectivas, por debajo de las %(target_min)s objetivo (lo "
        "limita el material o el tiempo)."
    ),
    "cardio.not_punishment": (
        "El cardio se programa por su efecto sobre el gasto y la salud, nunca como castigo por "
        "saltarse la dieta."
    ),
    "cardio.deficit_not_covered": (
        "Quedan %(kcal)s kcal semanales de déficit sin cubrir con actividad: se alarga el plazo "
        "antes que añadir más cardio."
    ),
    "cardio.health_sessions": (
        "%(sessions)s sesiones suaves de cardio a la semana por salud cardiovascular (opcionales)."
    ),
    "cardio.summary": (
        "Objetivo de %(steps)s pasos al día, %(liss)s sesiones LISS y %(hiit)s HIIT (unas %(kcal)s "
        "kcal/semana)."
    ),
    "adjust.insufficient_data": (
        "Todavía no hay datos suficientes (%(weight_days)s pesajes en %(span_days)s días): sigue "
        "registrando el peso a diario."
    ),
    "adjust.too_early": "La próxima revisión toca el %(next_review)s.",
    "adjust.trend": (
        "Cambio observado %(observed)s kg/semana frente a %(expected)s esperado (media móvil de 7 "
        "días)."
    ),
    "adjust.tdee_observed": (
        "Gasto observado por balance energético: %(observed)s kcal/día (teórico %(theoretical)s; "
        "se usa %(blended)s, con %(days)s días de datos)."
    ),
    "adjust.adherence_first": (
        "La pérdida va lenta pero la adherencia media es del %(adherence)s %%: antes de tocar "
        "calorías, revisa el registro y la constancia."
    ),
    "adjust.keep": "Vas según lo previsto: sin cambios hasta la próxima revisión.",
    "adjust.reduce_calories": (
        "Calorías bajadas %(delta)s kcal (%(pct)s %%): de %(old)s a %(new)s kcal."
    ),
    "adjust.increase_calories": (
        "Calorías subidas %(delta)s kcal (%(pct)s %%): de %(old)s a %(new)s kcal."
    ),
    "adjust.add_steps": (
        "Las calorías ya están en el mínimo seguro: se suman %(steps)s pasos diarios en su lugar."
    ),
    "adjust.loss_too_fast": (
        "Pierdes %(observed)s kg/semana, por encima del máximo de %(max_weekly)s kg (1 %% del "
        "peso): se suben calorías."
    ),
    "adjust.diet_break": (
        "Llevas %(weeks)s semanas en déficit y el peso está estancado: descanso de dieta de 2 "
        "semanas a mantenimiento (%(calories)s kcal) antes de seguir."
    ),
    "adjust.refeed": (
        "Estancamiento tras %(weeks)s semanas de déficit: día de recarga a mantenimiento "
        "(%(calories)s kcal) esta semana, priorizando carbohidratos."
    ),
    "adjust.floor_reached": "No se baja de %(floor)s kcal (mínimo seguro).",
    "adjust.capped_step": "Cambio limitado al %(pct)s %% por revisión.",
    "adjust.next_review": "Próxima revisión: %(date)s.",
    "plan.confidence": "Confianza de la estimación: %(confidence)s.",
}


def render(note: Note) -> str:
    """Text for a note in the active language; falls back to the code when unknown."""
    template = TEMPLATES.get(note.code)
    if template is None:
        return note.code if not note.params else f"{note.code} {note.params}"
    try:
        return translator(template) % note.params
    except (KeyError, TypeError, ValueError):
        return f"{note.code} {note.params}"


def render_all(notes: tuple[Note, ...]) -> list[str]:
    """Render every note, prefixed with its level when it is not informational."""
    rendered: list[str] = []
    for note in notes:
        text = render(note)
        rendered.append(text if note.level == "info" else f"[{note.level}] {text}")
    return rendered
