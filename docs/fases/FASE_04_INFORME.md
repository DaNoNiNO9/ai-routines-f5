# Fase 4 — Motor de cálculo nutricional

Fecha: 2026-09-09. Estado: **cerrada**.

## Qué se ha hecho

- `app/engine/types.py`: `NutritionInputs` (validación de rangos con `InputError`), `Note` (código + nivel + parámetros) y las estructuras de salida inmutables (`BodyComposition`, `BmrEstimate`, `EnergyExpenditure`, `CalorieTarget`, `Macros`, `Hydration`, `MealSlot`, `CarbCycle`, `NutritionPlan` con `to_dict()` serializable).
- `body_composition.py`: % graso Navy (hombres y mujeres, con detección de perímetros imposibles), IMC, masa magra y confianza por método (DEXA alta; calibre, Navy y báscula media; visual o nada baja).
- `bmr.py`: Katch-McArdle, Mifflin-St Jeor y Harris-Benedict revisada; selección por prioridad y rango siempre disponible.
- `tdee.py`: `TDEE = BMR + NEAT + EAT + TEF` con NEAT por pasos (0,5 kcal/kg/km, 0,75 m/paso) más vida diaria y ocupación (150/250/400/650 kcal), pasos estimados por trabajo, EAT por METs netos (4,0 gimnasio; 3/6/9 otro deporte), TEF del 10 % resuelto por punto fijo sobre la ingesta objetivo, modificador por sueño y estrés (≤ 5 %) y contraste con el método clásico con aviso si difiere más del 15 %.
- `targets.py`: déficit 10-25 % escalado por % graso y agresividad; superávit 5-15 % por experiencia; recomposición 5 % solo si encaja; mantenimiento; rendimiento +5 %. Suelo calórico y tope del 1 %/semana aplicados en el cálculo. Viabilidad de la fecha objetivo.
- `macros.py`: proteína 1,6-2,2 g/kg (base magra 2,3-2,6 g/kg MM con grasa alta y fiable, nunca bajo 0,8 g/kg de peso), grasa 0,8 g/kg acotada al 20-35 %, carbohidratos con suelo funcional (baja grasa al mínimo y después reduce el déficit), fibra 14 g/1000 kcal, hidratación 35 ml/kg + 500 ml por sesión, ciclado de carbohidratos con media semanal exacta.
- `meals.py`: reparto por comidas con nombres en español, carbohidratos ×1,5 y grasa ×0,6 en las comidas pre/post entreno según `training_time`, reparto exacto por restos mayores, aviso de proteína por toma < 0,4 g/kg.
- `safety.py`: constantes de los límites, `evaluate_eligibility` (menores, embarazo/lactancia, TCA → sin plan; IMC < 18,5 o grasa esencial → sin déficit), `verify_plan` (última puerta) y `SafetyError`.
- `nutrition.py`: orquestador `build_nutrition_plan()`; `messages.py`: plantillas en español para cada nota.
- Perfil: columnas `training_time` y `wants_carb_cycling` con migración `021183cac637` (revisada a mano: `server_default` y CHECK explícito).
- Documentación: `app/engine/README.md` (cada fórmula con su fuente y qué constante tocar), README raíz, `docs/DECISIONES.md` (T-31 a T-39), `docs/ARQUITECTURA.md`.

## Qué se ha probado

| Prueba | Cómo | Resultado |
|---|---|---|
| Suite del motor | `pytest tests/unit/engine --cov=app/engine` | 91 passed; cobertura del motor 98,6 % (objetivo ≥ 95 %, ≥ 40 tests) |
| Suite completa | `pytest --cov` | 204 passed; cobertura de `app/` 99,2 % |
| Linter y formato | `ruff check .`, `ruff format --check .` | limpios |
| Fórmulas con valores de referencia calculados a mano | Navy hombre 14,5 %, mujer 26,9 %; Mifflin 1780 / 1330; Harris-Benedict 1853,6 / 1392,3; Katch-McArdle 1774; marcha 262,5 kcal/10 000 pasos; TEF `I = 0,8(base + 0,1 I)` | OK |
| Reglas de objetivo | tabla de déficit por % graso y agresividad (7 casos), superávit por experiencia, elegibilidad de recomposición, 7700 kcal/kg | OK |
| Límites de seguridad, uno por uno | menor, embarazo/lactancia, TCA, IMC < 18,5 (bloquea déficit, permite mantenimiento), grasa esencial, suelo calórico (subida al mínimo y redondeo hacia arriba), tope 1 %/semana, cada violación de `verify_plan`, `SafetyError` | OK |
| Macros y comidas | cuadre energético ±12 kcal, suelo de carbohidratos que reduce el déficit (caso 100 kg / 1500 kcal: sube a 2140 kcal), reparto exacto por comidas con pesos pre/post, aviso por comidas, ciclado con media semanal y día bajo en el suelo | OK |
| Perfiles extremos (§7) | 40 kg / 140 cm, 200 kg / 210 cm / 85 años / 60 % graso, 200 kg / 160 cm, 2 días × 20 min, 6 días × 120 min, 1 y 8 comidas, sin entreno | todos producen plan válido con invariantes |
| Propiedades con Hypothesis | 200 perfiles aleatorios en todo el rango de entradas | cada plan es válido (suelo, tope, cuadre, proteína 0,8-3,5 g/kg) o está bloqueado con motivo |
| Prueba manual | script sobre un perfil real (85 kg, 180 cm, 30 años, 4 días) | 18,4 % graso, BMR 1869, mantenimiento 2653 kcal, objetivo 2225 kcal, macros y comidas coherentes, notas legibles |
| Migración nueva | `flask db upgrade`, `flask db downgrade`, `flask db upgrade` sobre la BD de desarrollo recreada y en el test de migraciones | OK; DDL con un único CHECK nombrado por la convención |

## Errores aparecidos y cómo se corrigieron

1. **Import inexistente** (`Note` desde `enums`) dejado en `tdee.py`. Corregido en la primera importación.
2. **NEAT demasiado bajo para sedentarios**: con extra ocupacional 0 kcal casi cualquier oficinista disparaba el aviso de divergencia con el método clásico. Recalibrado con un componente de vida diaria de 150 kcal (Levine 2004): el perfil de referencia pasa de −14 % a −8 %.
3. **Tres tests con expectativas erróneas** (tope del 1 % y suelo calórico no se activaban con esos perfiles): corregidos con perfiles calculados a mano, y test adicional del redondeo hacia arriba en el suelo.
4. **Contraejemplo de Hypothesis**: 293 kg con 66 % de grasa daba 234 g de proteína, 0,7986 g/kg, bajo el mínimo por redondeo. Corrección: proteína redondeada hacia arriba.
5. **Bordes de redondeo** detectados al diseñar: objetivo redondeado a 5 kcal podía quedar bajo el suelo (ahora se redondea hacia arriba), balance de mantenimiento con IMC bajo podía ser −3 kcal (tolerancia de 40 kcal en la puerta final).
6. **Migración en SQLite con `sa.Enum` en modo batch**: creaba dos CHECK (uno sin convención) y el `downgrade` fallaba con "no such column". Corrección: columna `String` + `create_check_constraint` explícito y `drop_constraint` antes de borrar la columna; BD de desarrollo recreada.
7. **Documentación de Flask-Migrate**: `flask db downgrade` no admite `-1` (ya baja un paso por defecto).

## Pendiente

- Traducir los códigos de nota a través de Babel en la capa web (Fase 9): hoy `messages.py` es la referencia en español.
- Fase 5: generador de rutinas (§3.7) con tests para ≥ 30 perfiles.

## Criterio de cierre

≥ 40 tests unitarios con todos los casos límite y todos los límites de seguridad, cobertura del módulo ≥ 95 %. Cumplido: 91 tests, 98,6 %.
