# app/engine/ — motor de cálculo (nutrición)

**Qué hace:** convierte los datos del cuestionario en un plan nutricional completo: composición corporal, metabolismo basal, gasto total por componentes, objetivo calórico según la meta, macronutrientes, reparto por comidas, ciclado de carbohidratos e hidratación, con los límites de seguridad aplicados y verificados. Son funciones puras: sin Flask, sin base de datos, con dataclasses inmutables de entrada y salida. Cada fórmula lleva su fuente en el docstring del módulo.

**Cómo funciona** (`nutrition.build_nutrition_plan(inputs)`):

1. `types.NutritionInputs` valida rangos amplios al construirse (`InputError` si algo es imposible).
2. `body_composition.assess_body_composition()`: % graso declarado (con su método) > estimación Navy por perímetros > nada. Calcula IMC, masa magra y la confianza (DEXA alta; calibre, Navy y báscula media; visual o nada baja).
   - Navy hombres: `495 / (1.0324 − 0.19077·log10(cintura − cuello) + 0.15456·log10(altura)) − 450`.
   - Navy mujeres: `495 / (1.29579 − 0.35004·log10(cintura + cadera − cuello) + 0.22100·log10(altura)) − 450`.
3. `safety.evaluate_eligibility()`: paradas duras (menor de 18, embarazo o lactancia, antecedentes de TCA → sin plan) y prohibición de déficit (IMC < 18,5 o grasa en niveles esenciales → solo mantenimiento, ganancia y entrenamiento).
4. `bmr.estimate_bmr()`: Katch-McArdle (`370 + 21.6·MM`) si hay % graso; si no, Mifflin-St Jeor (`10·kg + 6.25·cm − 5·edad + 5 / −161`). Harris-Benedict revisada se calcula para mostrar el rango.
5. `tdee.estimate_expenditure()`: `TDEE = BMR + NEAT + EAT + TEF`. NEAT = pasos × 0,75 m × 0,5 kcal/kg/km × peso + extra ocupacional (0/100/250/500 kcal); pasos estimados por trabajo si no se conocen (4000/7000/9000/12000). EAT = Σ (MET − 1) × kg × horas / 7 con MET 4,0 en gimnasio y 3/6/9 para otro deporte. Modificador por sueño y estrés (hasta −5 % sobre NEAT + EAT). TEF = 10 % de la ingesta, resuelto por punto fijo sobre el objetivo. Se contrasta con el método clásico (BMR × 1,2-1,9) y se avisa si difieren más del 15 %.
6. `targets.calorie_target()`: déficit 10-25 % escalado por % graso (12-30 % hombres, 20-38 % mujeres) y desplazado ±5 puntos por agresividad; superávit 5-15 % por experiencia (principiantes 5 %); recomposición 5 % de déficit solo si encaja; mantenimiento 0; rendimiento +5 %. Aplica el suelo calórico (`max(BMR, 1500 hombres / 1200 mujeres)`) y el tope de pérdida (1 % del peso/semana, 7700 kcal/kg). Comprueba si la fecha objetivo es realista.
7. `macros.compute_macros()`: proteína 1,6-2,2 g/kg por objetivo (+0,2 avanzados, +0,2 déficit agresivo; sobre masa magra a 2,3-2,6 g/kg cuando la grasa es alta y fiable). Grasa 0,8 g/kg acotada al 20-35 % de las calorías. Carbohidratos: el resto; si quedan bajo el suelo (1-2 g/kg según días, mínimo 100 g) primero baja la grasa al mínimo (0,6 g/kg y 20 %) y después **reduce el déficit** subiendo calorías. Fibra 14 g/1000 kcal. `hydration()`: 35 ml/kg + 500 ml por sesión (+250 ml por cada media hora extra).
8. `meals.distribute_meals()`: proteína repartida por igual; carbohidratos ×1,5 y grasa ×0,6 en las comidas pre y post entreno según `training_time`; reparto exacto por restos mayores; aviso si tocan menos de 0,4 g/kg de proteína por comida.
9. `macros.carb_cycle()` (opcional): días de entreno con +25 % de carbohidratos y días de descanso con menos, media semanal igual al objetivo, día bajo nunca bajo el suelo.
10. `safety.verify_plan()`: última puerta sobre los números finales (suelo, tope de pérdida, déficit con IMC bajo, proteína 0,8-3,5 g/kg, grasa ≥ 15 %, cuadre energético ±40 kcal). Cualquier violación lanza `SafetyError`: sería un bug del pipeline, nunca se devuelve un plan inválido.

**Ficheros:**
- `enums.py` — vocabulario de dominio compartido con modelos y formularios.
- `types.py` — `NutritionInputs`, `Note` (código + parámetros), estructuras de salida y `NutritionPlan.to_dict()`.
- `body_composition.py`, `bmr.py`, `tdee.py`, `targets.py`, `macros.py`, `meals.py` — cada etapa.
- `safety.py` — constantes de los límites, elegibilidad y verificación final.
- `nutrition.py` — orquestador.
- `messages.py` — plantillas en español de cada `Note` (`render`, `render_all`).
- `equipment_presets.py` — material por lugar de entrenamiento (para el generador de rutinas).

**Por dónde tocar:**
- Cambiar el rango de déficit → `targets.py`, `DEFICIT_MIN` / `DEFICIT_MAX` y la escala `LEAN_BODY_FAT` / `HIGH_BODY_FAT`.
- Cambiar el superávit por experiencia → `targets.py`, `SURPLUS_BY_EXPERIENCE`.
- Cambiar la proteína por objetivo → `macros.py`, `PROTEIN_PER_KG_BY_GOAL` (y `PROTEIN_MAX_PER_KG`).
- Cambiar el suelo de carbohidratos → `macros.py`, `carb_floor_g()`.
- Cambiar un límite de seguridad → `safety.py` (constantes al principio). `targets.py` los lee de ahí: un solo sitio.
- Cambiar los METs o el coste de la marcha → `tdee.py`, `GYM_SESSION_MET`, `OTHER_ACTIVITY_MET`, `WALKING_NET_KCAL_PER_KG_KM`.
- Añadir una explicación al usuario → emitir un `Note("codigo", params=...)` en la etapa y su plantilla en `messages.py`.
- Cambiar los nombres de las comidas → `meals.py`, `MEAL_NAMES`.

**Ojo con:**
- El TEF se resuelve sobre la ingesta objetivo: el "mantenimiento" mostrado es `base / 0,9`, y el gasto real a la ingesta objetivo es menor (`base + 0,1 × ingesta`). El déficit porcentual se define sobre ese gasto real.
- Las calorías finales pueden ser mayores que el objetivo inicial por el suelo de carbohidratos; `target` se recalcula con `with_calories()` para que balance y cambio semanal sean coherentes.
- `safety.verify_plan()` no "arregla" nada: si falla, hay un bug. Los tests con Hypothesis generan cientos de perfiles aleatorios para garantizar que nunca falla.
- La semántica de `Note.level`: `info` explica, `warning` pide revisar, `error` es un motivo de bloqueo.
- Las notas de elegibilidad que no bloquean (IMC bajo con objetivo de mantenimiento) se reemiten como `warning` en `NutritionPlan.notes`.
- Los nombres de comidas son texto en español dentro del motor (etiquetas), lo único no traducible por código; el resto son códigos.

**Tests:** `tests/unit/engine/` (fórmulas con valores de referencia calculados a mano, reglas de objetivo, macros y suelo de carbohidratos, comidas, ciclado, cada límite de seguridad, pipeline con perfiles extremos y test de propiedades con Hypothesis). `pytest tests/unit/engine --cov=app/engine`.
