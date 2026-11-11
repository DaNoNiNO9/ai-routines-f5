"""Human-readable text for engine notes.

The engine emits ``Note(code, level, params)`` so the web layer can translate
messages; these Spanish templates are the reference wording and are used by
the logs and the tests. Unknown codes render as the code itself, never crash.

Translation without dragging Flask in here: ``translator`` is a plain function
that the application replaces at start-up (see ``app.i18n``). Left alone it
returns the Spanish text, which is what the engine tests and the logs expect.
The strings reach the catalogue through ``scripts/babel_engine.py``.

``params_translator`` does the same for the values: the engine puts stable
codes in the parameters (``upper_lower``, ``glutes``) and the application
swaps them for their label, so no internal code reaches the reader.

Placeholders are printf-style with names (``%(pct)s``) and a literal percent
is written ``%%``, like every other string in the catalogue. Braces would
read better here, but Babel flags any msgid where a percent is followed by a
space and a conversion letter (``% sobre`` looks like ``%s``) and then
refuses to compile a catalogue that mixes both formats.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.engine.types import Note


def _as_written(text: str) -> str:
    """Default translator: the reference Spanish wording."""
    return text


def _as_produced(code: str, params: Mapping[str, Any]) -> Mapping[str, Any]:  # noqa: ARG001
    """Default parameter translator: the codes the engine produced."""
    return params


translator: Callable[[str], str] = _as_written
params_translator: Callable[[str, Mapping[str, Any]], Mapping[str, Any]] = _as_produced

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
        "Tu gasto calculado (%(components)s kcal) se aleja un %(pct)s %% de la estimación "
        "clásica (%(classic)s kcal): revisa pasos, trabajo o sesiones."
    ),
    "target.deficit": "Comes un %(pct)s %% menos de lo que gastas.",
    "target.surplus": "Comes un %(pct)s %% más de lo que gastas.",
    "target.maintenance": "Comes lo mismo que gastas.",
    "target.recomposition_not_ideal": (
        "La recomposición no encaja con tu experiencia y grasa actual: se usan calorías de "
        "mantenimiento; valora perder grasa o ganar músculo como objetivo."
    ),
    "target.raised_to_floor": "Calorías subidas al mínimo seguro (%(floor)s kcal).",
    "target.capped_by_max_loss": (
        "El ritmo se limita a %(max_weekly_kg)s kg por semana, el 1 %% de tu peso."
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
        "Proteína calculada sobre tu masa magra (%(per_kg)s g por kg de peso total)."
    ),
    "macros.protein_vegan": (
        "Como sigues una dieta vegana, la proteína sube %(extra)s g por kg: la vegetal se "
        "aprovecha algo peor. Combina legumbres con cereales o tira de soja, tofu y seitán."
    ),
    "macros.alcohol": (
        "Tus %(drinks)s bebidas a la semana son unas %(kcal)s kcal, el %(pct)s %% de tu semana. "
        "Van dentro del total, no aparte: apúntalas en el diario."
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
    "cycle.enabled": "Más hidratos los días de entreno: %(high)s g, y %(low)s g los de descanso.",
    "cycle.low_day_at_floor": (
        "Los días de descanso se quedan en el mínimo de %(floor)s g de hidratos."
    ),
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
    "safety.loss_too_fast": (
        "Pérdida prevista de %(weekly)s kg a la semana, por encima del máximo de %(max)s."
    ),
    "safety.deficit_while_underweight": "Déficit con un IMC bajo.",
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
    "routine.days_dropped": (
        "Con tu material y tus limitaciones no hay ejercicios posibles para algunos días "
        "(%(dropped)s): la semana queda en %(days)s días de entrenamiento."
    ),
    "routine.split": "Reparto %(split)s, %(days)s días a la semana.",
    "routine.mesocycle": (
        "Bloques de %(weeks)s semanas, con una semana suave cada %(deload)s. Reserva de cada "
        "semana: %(rir)s."
    ),
    "routine.double_progression": (
        "Cómo progresar: cuando hagas el máximo de repeticiones en todas las series dejando la "
        "reserva que toca, sube el peso indicado y vuelve al mínimo de repeticiones."
    ),
    "routine.level_relaxed": (
        "%(exercise)s: exige más técnica de la habitual para tu experiencia; empieza ligero."
    ),
    "routine.slot_unfilled": (
        "En %(day)s no hay ningún ejercicio de %(pattern)s posible con tu material y tus "
        "limitaciones."
    ),
    "routine.pattern_missing": (
        "No hay ejercicios de %(pattern)s con tu material: con %(suggestion)s se resolvería."
    ),
    "routine.pull_bias": (
        "Por tu historial de hombro hay un 30 %% más de series de tirar que de empujar."
    ),
    "routine.push_pull": "Series de empujar: %(push)s. Series de tirar: %(pull)s.",
    "routine.time_trimmed": "%(day)s: series recortadas para encajar en %(minutes)s minutos.",
    "routine.exercises_dropped_for_time": (
        "%(day)s: se quitan ejercicios de aislamiento (%(n)s) para caber en %(minutes)s "
        "minutos. El descanso entre series no se recorta: manda el trabajo básico."
    ),
    "routine.session_too_long": (
        "%(day)s: aun recortando, la sesión estimada dura %(estimated)s min y tienes %(budget)s; "
        "añade minutos o un día."
    ),
    "routine.volume_scaled_by_time": (
        "Objetivos de volumen reducidos un %(pct)s %% para caber en tus sesiones; más días o "
        "minutos permitirían más series."
    ),
    "routine.pattern_trimmed": (
        "Los ejercicios de %(pattern)s quedan fuera esta semana por falta de tiempo."
    ),
    "routine.pattern_not_scheduled": (
        "Los ejercicios de %(pattern)s no entran en este reparto de días; vuelven en el "
        "siguiente bloque."
    ),
    "routine.pattern_blocked_by_injury": (
        "Los ejercicios de %(pattern)s se omiten por las lesiones o molestias que has indicado."
    ),
    "routine.push_pull_unbalanced": (
        "Con tu material no hay suficientes ejercicios de tirar para equilibrar los de empujar."
    ),
    "routine.priority_applied": "Volumen extra (+27 %%) para %(muscles)s, compensado en el resto.",
    "routine.priority_slot_added": (
        "Se añade un ejercicio de %(muscle)s en %(day)s porque es prioritario para ti."
    ),
    "routine.volume_low": (
        "Para %(muscle)s salen %(planned)s series efectivas, por debajo de las %(target_min)s "
        "recomendadas: lo limita el material o el tiempo."
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
    "cardio.liss_machine": (
        "El cardio suave, en la máquina que prefieras: cinta a ritmo vivo, bici, elíptica o "
        "remo. Ritmo de poder hablar sin quedarte sin aire."
    ),
    "cardio.liss_outdoor": (
        "El cardio suave: andar rápido, bici o trote cómodo. Ritmo de poder hablar sin "
        "quedarte sin aire."
    ),
    "cardio.liss_low_impact": (
        "Por lo que has contado de tus articulaciones, el cardio suave mejor sin impacto: "
        "bici, elíptica, remo o andar. Nada de correr ni saltar."
    ),
    "cardio.hiit_machine": (
        "Los intervalos, en bici estática, remo o cinta en cuesta: 30 segundos fuertes y 90 "
        "suaves, con 10 minutos de calentamiento y vuelta a la calma."
    ),
    "cardio.hiit_outdoor": (
        "Los intervalos: cuestas, comba o sprints en bici. 30 segundos fuertes y 90 suaves, con"
        " 10 minutos de calentamiento y vuelta a la calma."
    ),
    "cardio.hiit_low_impact": (
        "Los intervalos, sin impacto: bici o remo, 30 segundos fuertes y 90 suaves."
    ),
    "cardio.summary": (
        "Objetivo de %(steps)s pasos al día, %(liss)s sesiones de cardio suave y %(hiit)s de "
        "intervalos (unas %(kcal)s kcal a la semana)."
    ),
    "adjust.insufficient_data": (
        "Todavía no hay datos suficientes (%(weight_days)s pesajes en %(span_days)s días): "
        "sigue apuntando tu peso; con tres pesajes repartidos ya se puede revisar."
    ),
    "adjust.too_early": "La próxima revisión toca el %(next_review)s.",
    "adjust.sparse_trend": (
        "Con %(weight_days)s pesajes en %(span_days)s días la tendencia se ve, pero con "
        "margen: se mira un mes entero y se ajusta la mitad. Pesándote más a menudo se "
        "afina antes."
    ),
    "adjust.trend": (
        "Tu peso cambia %(observed)s kg a la semana; se esperaba %(expected)s (media de 7 días)."
    ),
    "adjust.trend_raw": (
        "Tu peso cambia %(observed)s kg a la semana; se esperaba %(expected)s, contando los "
        "pesajes que has apuntado."
    ),
    "adjust.tdee_observed": (
        "Con lo que has apuntado, gastas unas %(observed)s kcal al día (estimábamos "
        "%(theoretical)s). Se usa %(blended)s, con %(days)s días de datos."
    ),
    "adjust.adherence_first": (
        "Vas más lento de lo previsto, pero has seguido el plan un %(adherence)s %% de los "
        "días: antes de tocar calorías, intenta ser más constante y apuntarlo todo."
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
        "Pierdes %(observed)s kg a la semana, más del máximo de %(max_weekly)s kg (el 1 %% de "
        "tu peso): suben las calorías."
    ),
    "adjust.diet_break": (
        "Llevas %(weeks)s semanas en déficit y el peso está estancado: pausa de dieta de 2 "
        "semanas comiendo lo que gastas (%(calories)s kcal) antes de seguir."
    ),
    "adjust.refeed": (
        "Estancamiento tras %(weeks)s semanas de déficit: un día de recarga comiendo lo que "
        "gastas (%(calories)s kcal) esta semana, sobre todo hidratos."
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
        return translator(template) % params_translator(note.code, note.params)
    except (KeyError, TypeError, ValueError):
        return f"{note.code} {note.params}"


def render_all(notes: tuple[Note, ...]) -> list[str]:
    """Render every note, prefixed with its level when it is not informational."""
    rendered: list[str] = []
    for note in notes:
        text = render(note)
        rendered.append(text if note.level == "info" else f"[{note.level}] {text}")
    return rendered
