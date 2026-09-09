# app/engine/ — motor de cálculo (nutrición, rutinas y ajuste)

**Qué hace:** convierte los datos del cuestionario en (1) un plan nutricional completo y (2) una rutina de gimnasio completa, con los límites de seguridad aplicados y verificados. Son funciones puras: sin Flask, sin base de datos, con dataclasses inmutables de entrada y salida y salida determinista. Cada fórmula lleva su fuente en el docstring del módulo.

## Nutrición (`nutrition.build_nutrition_plan(inputs)`)

1. `types.NutritionInputs` valida rangos amplios al construirse (`InputError` si algo es imposible).
2. `body_composition.assess_body_composition()`: % graso declarado (con su método) > estimación Navy por perímetros > nada. Calcula IMC, masa magra y la confianza (DEXA alta; calibre, Navy y báscula media; visual o nada baja).
   - Navy hombres: `495 / (1.0324 − 0.19077·log10(cintura − cuello) + 0.15456·log10(altura)) − 450`.
   - Navy mujeres: `495 / (1.29579 − 0.35004·log10(cintura + cadera − cuello) + 0.22100·log10(altura)) − 450`.
3. `safety.evaluate_eligibility()`: paradas duras (menor de 18, embarazo o lactancia, antecedentes de TCA → sin plan) y prohibición de déficit (IMC < 18,5 o grasa en niveles esenciales → solo mantenimiento, ganancia y entrenamiento).
4. `bmr.estimate_bmr()`: Katch-McArdle (`370 + 21.6·MM`) si hay % graso; si no, Mifflin-St Jeor (`10·kg + 6.25·cm − 5·edad + 5 / −161`). Harris-Benedict revisada se calcula para mostrar el rango.
5. `tdee.estimate_expenditure()`: `TDEE = BMR + NEAT + EAT + TEF`. NEAT = pasos × 0,75 m × 0,5 kcal/kg/km × peso + vida diaria y ocupación (150/250/400/650 kcal); pasos estimados por trabajo si no se conocen (4000/7000/9000/12000). EAT = Σ (MET − 1) × kg × horas / 7 con MET 4,0 en gimnasio y 3/6/9 para otro deporte. Modificador por sueño y estrés (hasta −5 % sobre NEAT + EAT). TEF = 10 % de la ingesta, resuelto por punto fijo sobre el objetivo. Contraste con el método clásico (BMR × 1,2-1,9) y aviso si difieren más del 15 %.
6. `targets.calorie_target()`: déficit 10-25 % escalado por % graso (12-30 % hombres, 20-38 % mujeres) y desplazado ±5 puntos por agresividad; superávit 5-15 % por experiencia (principiantes 5 %); recomposición 5 % de déficit solo si encaja; mantenimiento 0; rendimiento +5 %. Aplica el suelo calórico (`max(BMR, 1500 hombres / 1200 mujeres)`) y el tope de pérdida (1 % del peso/semana, 7700 kcal/kg). Comprueba si la fecha objetivo es realista.
7. `macros.compute_macros()`: proteína 1,6-2,2 g/kg por objetivo (+0,2 avanzados, +0,2 déficit agresivo; sobre masa magra a 2,3-2,6 g/kg cuando la grasa es alta y fiable, nunca bajo 0,8 g/kg de peso). Grasa 0,8 g/kg acotada al 20-35 %. Carbohidratos: el resto; si quedan bajo el suelo (1-2 g/kg según días, mínimo 100 g) primero baja la grasa al mínimo y después **reduce el déficit**. Fibra 14 g/1000 kcal. `hydration()`: 35 ml/kg + 500 ml por sesión.
8. `meals.distribute_meals()`: proteína repartida por igual; carbohidratos ×1,5 y grasa ×0,6 en las comidas pre y post entreno según `training_time`; reparto exacto por restos mayores; aviso si tocan menos de 0,4 g/kg de proteína por comida.
9. `macros.carb_cycle()` (opcional): días de entreno con +25 % de carbohidratos y días de descanso con menos, media semanal exacta, día bajo nunca bajo el suelo.
10. `safety.verify_plan()`: última puerta sobre los números finales. Cualquier violación lanza `SafetyError`: sería un bug del pipeline, nunca se devuelve un plan inválido.

## Rutinas (`routines.generator.build_routine(inputs, catalogue)`)

1. `routines/types.py`: `RoutineInputs` (días, minutos, experiencia, lugar y material, lesiones con severidad, hasta 2 músculos prioritarios, preferencias y aversiones, pasos, déficit que la dieta no cubre, fatiga) y `ExerciseInfo` (lo que el generador sabe de cada ejercicio; `catalog.exercise_from_dict()` lo construye desde el JSON o las filas).
2. `routines/catalog.py`: filtros duros. Material: todo el que exige el ejercicio debe estar en el del usuario. Lesiones: se excluye el ejercicio si la severidad declarada en esa zona es igual o mayor a la `min_severity` de su contraindicación. Aversiones. Nivel técnico permitido por experiencia (principiante / intermedio / avanzado), con una relajación de un nivel anotada cuando no hay nada más.
3. `routines/splits.py`: 2 días full body; 3 full body (avanzados PPL); 4 upper/lower; 5 upper/lower + PPL (Arnold con más de 5 años); 6 PPL ×2. Cada día es una lista de slots (patrón, rol `main`/`secondary`/`accessory`/`isolation`, músculo objetivo, unilateral): compuestos primero, todos los patrones cubiertos en la semana.
4. `routines/selection.py`: puntuación determinista por slot (preferidos +100, staples +25, músculo objetivo +40, mecánica del rol +20, material cargable sobre bandas y peso corporal, unilateral donde se pide, −30 por cada uso previo en la semana); desempate por CRC32 del slug.
5. `routines/volume.py`: series efectivas (primario 1, secundario 0,5) contra 8-12 / 12-18 / 16-22 por experiencia; prioritarios +27,5 % con el resto reducido para no disparar el total. El generador escala los objetivos al tiempo disponible (2,5 min por serie) y luego sube o baja series slot a slot hasta acercarse.
6. Equilibrio empuje/tracción: tracción ≥ empuje (≥ 1,3 con historial de hombro); primero más series de tracción, luego un accesorio de tracción, y si no hay más material, menos series de empuje.
7. Tiempo: cada serie cuesta reps máximas × 3 s + descanso (unilateral ×1,8), más 8 min de calentamiento y 1 min por ejercicio. Se recorta aislamiento → accesorio → secundario → principal (manteniendo las series de tracción y un mínimo de 3 ejercicios); si aun así no entra, aviso honesto.
8. `routines/prescription.py`: reps 6-10 principales (3-6 con objetivo rendimiento y experiencia), 10-15 accesorios, 12-20 aislamiento, 10-15 core; RIR de 3 a 1 (aislamiento hasta 0) semana a semana; descansos 180/150/90/60 s (90/90/60/45 con peso corporal); tempo 2-0-1-0 y 3-1-1-0; incremento de carga por material y sexo (barra 5/2,5 kg abajo, 2,5/1,25 arriba; mancuernas 2/1; máquinas 5/2,5); mesociclo 6/5/4 semanas y descarga cada 8/6/4 según experiencia, acortados con fatiga alta. Progresión doble explicada en una nota.
9. `routines/cardio.py`: pasos objetivo (+2000 en pérdida de grasa, 8-12k; ≥ 7000 en el resto) y LISS/HIIT solo para el déficit que la dieta no cubre (máximo 3 LISS + 1 HIIT, HIIT solo con experiencia y sin lesión inferior); si sobra déficit, nota para alargar el plazo. Nunca como castigo.
10. Cobertura: cada patrón obligatorio ausente se explica: recortado por tiempo, no programado en esa distribución de días, bloqueado por lesiones o imposible con el material (con sugerencia).

## Ajuste (`adjustment.rules.decide(inputs)`)

1. `adjustment/types.py`: `AdjustmentInputs` (modo del plan, calorías y cambio semanal esperado, BMR y TDEE teórico, pesajes e ingestas registradas, semanas en déficit, último ajuste) y `AdjustmentDecision` (acción, motivo, calorías y pasos nuevos, tendencia, TDEE estimado, adherencia, próxima revisión y notas).
2. `smoothing.py`: media móvil de 7 días (ventana de calendario, mínimo 3 pesajes) y tendencia en kg/semana por mínimos cuadrados sobre la serie suavizada; hacen falta ≥ 8 pesajes en ≥ 10 días. Nunca se comparan días sueltos.
3. `energy_balance.py`: `TDEE observado = ingesta media + (−Δpeso × 7700) / días` con ≥ 70 % de días de ingesta registrados, acotado a ±25 % del teórico, y mezclado con el teórico según los días de historia (confianza total a los 28 días). Se calcula sobre los últimos 42 días, no solo sobre la ventana de revisión, para que la estimación converja al gasto real aunque las calorías hayan cambiado.
4. `rules.py`: revisión cada 14 días (antes, "esperar"; sin datos, nueva cita en 7 días). Déficit: pérdida < 50 % de la esperada → adherencia primero (< 85 % no se recorta), después recorte ≤ 5 % sin bajar del suelo ni superar el tope del 1 %, y +1000 pasos si ya está en el suelo; pérdida > 1 %/semana → subir calorías; estancamiento con ≥ 4 semanas y un estancamiento previo → refeed; con ≥ 8 semanas → descanso de dieta de 2 semanas a mantenimiento. Superávit: ±5 %. Mantenimiento: ±3 % ante derivas > 0,25 kg/semana.

**Ficheros:**
- `enums.py`, `types.py`, `messages.py`, `equipment_presets.py` — vocabulario, estructuras, plantillas en español de cada `Note`, material por lugar.
- `body_composition.py`, `bmr.py`, `tdee.py`, `targets.py`, `macros.py`, `meals.py`, `safety.py`, `nutrition.py` — etapas de nutrición y orquestador.
- `routines/types.py`, `catalog.py`, `splits.py`, `volume.py`, `selection.py`, `prescription.py`, `cardio.py`, `generator.py` — etapas de rutinas y orquestador.
- `adjustment/types.py`, `smoothing.py`, `energy_balance.py`, `rules.py` — motor de ajuste.

**Por dónde tocar:**
- Rango de déficit / superávit / proteína / suelo de carbohidratos → `targets.py` y `macros.py` (constantes al principio). Límites de seguridad → `safety.py`.
- METs y coste de la marcha → `tdee.py`.
- Qué split se elige → `splits.select_split()`; qué lleva cada día → las `DayTemplate` de `splits.py`.
- Preferencias del entrenador (staples, bonus por material) → `selection.py` (`STAPLES`, `EQUIPMENT_BONUS`).
- Rangos de volumen y factor de prioridad → `volume.py`. Reps, RIR, descansos, tempo, incrementos, mesociclo → `prescription.py`.
- Cardio → `cardio.py` (`steps_target()`, METs, máximos de sesiones).
- Cadencia de revisión, umbrales de adherencia, tamaño de los pasos de ajuste, semanas para refeed y descanso → constantes de `adjustment/rules.py`; ventana y confianza del TDEE observado → `adjustment/energy_balance.py`.
- Añadir una explicación → emitir un `Note("codigo", params=...)` y su plantilla en `messages.py`.

**Ojo con:**
- El TEF se resuelve sobre la ingesta objetivo: el "mantenimiento" mostrado es `base / 0,9` y el gasto real a la ingesta objetivo es menor.
- Las calorías finales pueden superar el objetivo inicial por el suelo de carbohidratos; `target` se recalcula con `with_calories()`.
- `safety.verify_plan()` no arregla nada: si falla, hay un bug. Los tests con Hypothesis generan cientos de perfiles para garantizar que nunca falla.
- El generador de rutinas es determinista: mismo perfil y mismo catálogo → misma rutina. La variedad entre mesociclos vendrá de rotar plantillas y de la penalización por reuso, no del azar.
- Sin material ninguno no hay tracción vertical; el generador lo dice y sugiere material. Con todas las lesiones graves, puede devolver una rutina parcial o bloquearse con explicación.
- Los objetivos de volumen se escalan al tiempo: una sesión de 45 min × 3 días no puede sostener 12-18 series por grupo; el plan lo dice en vez de fingir.
- Los nombres de comidas y de días son texto en español dentro del motor (etiquetas); el resto son códigos traducibles.

**Tests:** `tests/unit/engine/adjustment/` (suavizado, balance energético, cada regla y una simulación de 12 semanas con cinco semillas que debe converger al gasto real sin cruzar límites), `tests/unit/engine/` (nutrición: fórmulas con valores de referencia, límites, extremos, Hypothesis) y `tests/unit/engine/routines/` (unidades y generador: rejilla de 100 perfiles experiencia × días × lugar, lesiones, prioridades, tiempo, preferencias, determinismo, bloqueos). `pytest tests/unit/engine --cov=app/engine`.
