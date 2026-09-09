# Fase 8 — Cuestionario multipaso

Fecha: 2026-09-09. Estado: **cerrada**.

## Qué se ha hecho

- Modelo `QuestionnaireDraft` (`questionnaire_drafts`, migración `f3a8881022c3`): un borrador por usuario con las respuestas en JSON y el último paso completado. Relación `User.questionnaire_draft` y `User.today()` (fecha en la zona del usuario; `tzdata` añadido a las dependencias porque Windows no trae la base de zonas).
- `app/labels.py`: etiquetas traducibles de todos los enums, con textos de ayuda para trabajo, lugar, objetivo y ritmo; `choices()` para WTForms y `label()` para plantillas.
- `app/services/onboarding.py`: definición de los siete pasos y sus claves obligatorias, borrador (crear, pre-rellenar desde el perfil vigente, guardar paso, primer paso incompleto), conversión borrador ↔ perfil con revalidación, `complete()` (perfil versionado, lesiones, material, peso de hoy, generación, borrado del borrador, transacción única), catálogos para los formularios (`equipment_groups()`, `exercise_lookup()`).
- `app/services/plans.py`: entradas del motor desde el perfil (incluido el déficit no cubierto por el suelo calórico, que la rutina convierte en cardio), catálogo `ExerciseInfo` desde las filas, `persist_plan()` / `persist_routine()` versionados con `details` (salida completa + mensajes renderizados) e `inputs_snapshot`, auditoría en `plan_adjustments`, `generate_for_profile()` con las reglas de bloqueo (T-66).
- Blueprint `onboarding` (`/cuestionario`): `paso/<n>` (GET pre-rellenado, POST valida y guarda; no se puede saltar más allá del siguiente paso pendiente; atrás sin perder nada), `revisar` (resumen legible por bloque con enlaces "Editar"; POST genera), `resultado` (plan, comidas, ciclado, rutina por días, cardio, avisos; o motivos del bloqueo). Formularios por paso con validación cruzada; paso de material con preset por lugar y reinicio si el lugar cambia; lesiones por zona y gravedad; preferencias por nombre con `datalist`.
- Panel: CTA para empezar o continuar el cuestionario; con perfil, resumen (kcal, proteína, rutina) y enlaces a resultado y actualización.
- Plantillas: `_wizard.html` (barra de progreso con `aria-current`, "Paso n de 8", navegación), siete `step_*.html`, `review.html`, `result.html`; macros `radios` y `checkboxes`; CSS de pasos, opciones, rejillas, tablas, estadísticas y avisos.
- Motor: `_jsonable()` serializa `frozenset` (instantáneas de entradas de rutina); corrección del suelo de carbohidratos tras el redondeo (T-69).
- Documentación: `app/services/README.md` (nuevo), `app/README.md`, `app/models/README.md`, `docs/MODELO_DATOS.md`, `docs/ARQUITECTURA.md`, `docs/DECISIONES.md` T-61 a T-69, README raíz.

## Qué se ha probado

| Prueba | Cómo | Resultado |
|---|---|---|
| Servicio de planes | `tests/unit/services/test_plans_service.py` (entradas desde el perfil, déficit no cubierto solo con suelo, catálogo desde filas e inactivos fuera, plan + comidas + rutina + auditoría, segunda generación que supersede, bloqueo sin filas, solo peso corporal, negativas a persistir bloqueados, comidas = slots) | 12 tests, 100 % de `plans.py` |
| Servicio de cuestionario | `tests/unit/services/test_onboarding_service.py` (paso incompleto, borrador idempotente y pre-rellenado, guardado que nunca retrocede, normalización, borradores inválidos con código, `complete()` con perfil/material/peso/plan, segunda versión, rollback si el motor falla, catálogos) | 14 tests, 100 % de `onboarding.py` |
| Web | `tests/integration/test_onboarding.py` (anónimo → login, panel con CTA, inicio en el primer paso pendiente y bloqueo de saltos, 404, errores de validación en su sitio, preset y cambio de lugar, nombres de ejercicios desconocidos, máximo dos músculos, revisión que exige completar, resumen, generación completa y página de resultado, actualización que crea la versión 2, parada dura (embarazo) sin plan, fallo del motor con borrador conservado, resultado sin perfil, ramas de validación, respuestas guardadas visibles al volver, material imposible que conserva la nutrición) | 15 tests, 99 % de `routes.py`, 99 % de `forms.py` |
| Etiquetas y helpers | `tests/unit/test_labels_and_forms.py` | 5 tests, 100 % de `labels.py` |
| Migración | `tests/integration/test_migrations.py` (upgrade = modelos, downgrade limpio) con la tabla nueva | OK; `flask db upgrade` aplicado en `instance/forja.db` |
| Suite completa | `pytest --cov` | 434 passed; cobertura de `app/` 98,9 % |
| Linter y formato | `ruff check .`, `ruff format --check .` | limpios |
| Servidor real | `flask run --no-reload` + `curl.exe` con tarro de cookies y CSRF: registro → panel con "Empezar el cuestionario" → `/cuestionario` → paso 1 (barra con 8 pasos; menor de edad rechazado con mensaje) → pasos 1-7 (302 en cadena; paso 4 con 19 casillas pre-marcadas del preset de gimnasio básico) → revisión (muestra "Gimnasio básico", "Perder grasa", "Rodilla (Leve…)", el ejercicio evitado) → POST genera → resultado 200 con "Plan y rutina generados", 2075 kcal, 4 días (Torso A/Pierna A/Torso B/Pierna B), 32 filas de tabla, 0 apariciones del ejercicio evitado → panel con "Ver mi plan" → `/cuestionario` redirige a la revisión pre-rellenada | OK, sin errores nuevos en `logs/forja.log` ni trazas en consola |

## Errores aparecidos y cómo se corrigieron

1. **`frozenset` no serializable** al guardar `inputs_snapshot` de la rutina: `_jsonable()` del motor ahora ordena conjuntos.
2. **`ZoneInfoNotFoundError` en Windows** (sin base de zonas horarias): dependencia `tzdata` y `User.today()` con respaldo en UTC.
3. **Validador inline `validate_hip_cm` nunca se ejecutaba**: `Optional()` corta la cadena cuando el campo está vacío. La comprobación pasó al `validate()` del formulario (documentado en el docstring).
4. **Objetos recién creados con cadenas en columnas enum** (antes de recargar de la base de datos): las entradas del motor coaccionan con `Enum(valor)`.
5. **Suma de comidas ≠ objetivo calórico** en un test: las comidas se reconstruyen desde gramos, así que difieren en unos kcal; el test admite ±10.
6. **Slugs reales del catálogo** distintos de los supuestos en los tests (`barbell-bench-press-medium-grip`, `barbell-squat`).
7. **Hypothesis encontró un caso** (100 cm, 121 kg) en que el redondeo dejaba los carbohidratos 2 g bajo el suelo: corregido en el motor (T-69), la base de ejemplos de Hypothesis conserva el caso.
8. **`EXPECTED_TABLES` del test de migraciones** sin la tabla nueva: añadida.
9. **Comando de shell demasiado largo** (más de 8 KB) truncado: ficheros grandes con la herramienta de escritura, parches pequeños por script.

## Limitaciones conocidas

- El resultado se muestra en una sola página sencilla; las páginas de nutrición y entrenamiento con gráficas, sustitución de ejercicios e imágenes llegan en la Fase 9.
- Sin JavaScript no hay guardado automático a mitad de paso: se guarda al pulsar "Continuar" (o al volver atrás tras haber continuado). Con Alpine.js (Fase 9) se puede añadir sin cambiar el servidor.
- Aversiones y alergias se guardan pero todavía no filtran sugerencias de alimentos (no hay base de alimentos: fuera del alcance del prompt).
- Los perímetros del cuestionario van a `profiles`, no a `body_measurements`; el registro periódico de perímetros llega con el seguimiento (Fase 10).

## Pendiente

- Fase 9: panel con gráficas (Alpine.js y Chart.js vendorizados), página de nutrición (comidas, ciclado, explicaciones), página de entrenamiento (días, ejercicios con imagen, alternativas, progresión).
- Fase 10: registro de entrenos, pesajes e ingestas y motor de ajuste conectado (`plan_adjustments` con motivos de revisión).

## Criterio de cierre

Flujo completo del cuestionario en el servidor real: registro, siete pasos con validación, guardado parcial, revisión, generación, resultado y actualización con versionado. Cumplido.
