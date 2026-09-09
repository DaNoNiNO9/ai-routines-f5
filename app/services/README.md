# app/services/ — orquestación entre web, modelos y motor

**Qué hace:** contiene la lógica de aplicación que no es ni cálculo puro (eso vive en `engine/`) ni presentación (blueprints y plantillas): cuentas, cuestionario y la conversión de un perfil en plan y rutina guardados. Los blueprints llaman a estas funciones y solo traducen resultados a mensajes y redirecciones.

**Cómo funciona:**

1. `auth.py` (Fase 7): registro con consentimiento, argon2id con rehash transparente, verificación ficticia para correos desconocidos, política de contraseñas por códigos, `load_user` para Flask-Login y tokens de recuperación firmados y caducables ligados al hash actual.
2. `onboarding.py` (Fase 8): el cuestionario se guarda paso a paso en `QuestionnaireDraft` (JSON plano: fechas ISO, enums por su valor, listas). `STEPS` define los siete pasos y las claves obligatorias de cada uno; `first_incomplete_step()` decide hasta dónde puede avanzar la persona y si puede revisar. `start_draft()` crea el borrador, pre-rellenado desde el perfil vigente si existe (`profile_to_data()`), para actualizar el cuestionario sin repetirlo entero. `complete()` convierte el borrador en una versión nueva de `Profile` (`data_to_profile_values()` revalida todo: un borrador manipulado nunca produce un perfil inválido), registra las lesiones, el material del usuario y el peso de hoy, llama a `plans.generate_for_profile()` y borra el borrador; todo en una transacción que se deshace si el motor rechaza los datos.
3. `plans.py` (Fase 8): `nutrition_inputs()` y `routine_inputs()` construyen las entradas del motor desde el perfil (edad calculada a la fecha, lesiones, hasta dos músculos prioritarios, material del usuario, déficit que la dieta no cubre por el suelo calórico). `load_catalogue()` convierte las filas activas de `exercises` en `ExerciseInfo`. `persist_plan()` y `persist_routine()` guardan versiones nuevas (`ACTIVE`), marcan la anterior como `SUPERSEDED`, guardan la instantánea de entradas y la salida completa del motor en `details` (con los mensajes ya renderizados en `details["messages"]`) y anotan la auditoría en `plan_adjustments` (`initial` la primera vez, `profile_change` después). `generate_for_profile()` orquesta: nutrición bloqueada por seguridad → no se guarda nada (ni rutina); rutina imposible con el material → se guarda solo la nutrición.

4. `dashboard.py` (Fase 9): lecturas para las páginas del plan. `weight_series()` devuelve los pesajes de los últimos 90 días con la misma media móvil de 7 días del motor de ajuste (`WeightSeries.to_chart()` alinea ambas series para Chart.js); `next_routine_day()` es el día siguiente a la última sesión completada de la rutina vigente (día 1 si no hay ninguna); `next_review_on()` suma 14 días al último ajuste del plan (o a su inicio); `plan_history()` empareja cada versión con el ajuste que la creó; `today_targets()` saca del plan los objetivos de hoy (y, con ciclado, los de día de entreno y de descanso); `usable_alternatives()` filtra las alternativas del catálogo con el material, las lesiones, el nivel y las aversiones de la persona; `image_frames()` devuelve las dos ilustraciones de un ejercicio.

5. `tracking.py` (Fase 10): diario por día. Una fila por usuario y día en `weight_logs`, `intake_logs` y `activity_logs`; guardar el mismo día otra vez reemplaza la entrada entera. `diary_rows()` devuelve los últimos 14 días completos (con huecos incluidos) y `recent_measurements()` los perímetros más recientes.
6. `workouts.py` (Fase 10): sesiones. `start_session()` devuelve la sesión abierta si ya hay una (T-77); `log_set()` escribe una fila por sesión, ejercicio y número de serie, y repetir el número corrige en vez de duplicar (T-78); `substitute()` guarda el ejercicio alternativo solo para esa sesión y solo si es viable (T-79); `session_blocks()` monta la página en vivo con la última actuación y la carga sugerida por progresión doble (T-80); `summarise()` da totales y marcas con el 1RM de Epley (T-81); `history()` y `exercise_progress()` alimentan el historial y la gráfica.
7. `adjustments.py` (Fase 10): la revisión quincenal. `build_inputs()` traduce el plan vigente y el diario a `AdjustmentInputs`; `preview()` ejecuta el motor **sin escribir nada**; `apply()` guarda exactamente una de tres cosas: versión nueva del plan (si cambian las calorías), objetivo de pasos nuevo, o solo la fila de auditoría (T-82, T-83). Los tres casos dejan la decisión completa en `plan_adjustments.data`.

8. `exports.py` (Fase 12): `plan_pdf()` maqueta el plan con ReportLab (objetivo, comidas, ciclado, cómo se ha calculado con las fórmulas nombradas, rutina día a día y el aviso legal en todas las páginas); funciona también sin plan, listando los motivos del bloqueo. `data_archive()` devuelve un ZIP con un CSV por tipo de dato y un LEEME; los CSV llevan BOM para que las hojas de cálculo respeten los acentos. `export_filename()` pasa el nombre a ASCII porque viaja en una cabecera HTTP.

**Ficheros:**
- `auth.py` — cuentas y contraseñas (incluye cambio de correo, de contraseña y borrado en cascada).
- `onboarding.py` — pasos, borradores, perfil, catálogos para los formularios (`equipment_groups()`, `exercise_lookup()`), `complete()`.
- `plans.py` — entradas del motor, catálogo (`exercise_info()`, `load_catalogue()`), persistencia de planes y rutinas, `active_plan()`, `active_routine()`, `GenerationResult`.
- `dashboard.py` — lecturas del panel y de las páginas de plan (nunca escribe).
- `exports.py` — PDF del plan y ZIP con los datos personales.
- `tracking.py` — diario y perímetros.
- `workouts.py` — sesiones, series, sustituciones, resúmenes y progreso.
- `adjustments.py` — revisión quincenal (`preview`/`apply`).

**Por dónde tocar:**
- Añadir una pregunta al cuestionario → columna en `Profile` (+ migración), campo en el formulario del paso (`blueprints/onboarding/forms.py`), plantilla del paso, `profile_to_data()` y `data_to_profile_values()` aquí, fila en `_summary()` de la vista de revisión y, si el motor la usa, `nutrition_inputs()` / `routine_inputs()`.
- Cambiar qué hace obligatorio un paso → `STEPS[...].required`.
- Guardar algo más al terminar el cuestionario (por ejemplo perímetros en `body_measurements`) → `complete()`.
- Cambiar cómo se versiona o se supersede un plan → `persist_plan()` / `persist_routine()`.
- Cambiar el intervalo de revisión → `AdjustmentInputs.review_interval_days` (motor) y `dashboard.REVIEW_INTERVAL_DAYS`, que un test obliga a mantener iguales.
- Cambiar cuántas series de más se admiten → `workouts.EXTRA_SETS_ALLOWED`.

**Ojo con:**
- Nada en `plans.py` hace `commit()`: `complete()` (o el test) es dueño de la transacción.
- `details` y `inputs_snapshot` son JSON: `_jsonable()` del motor convierte enums, fechas y `frozenset` (ordenado). Si un tipo nuevo aparece en las dataclasses, hay que enseñárselo.
- Los enums de perfil se coaccionan con `Enum(valor)` al construir las entradas: un objeto recién creado puede llevar todavía la cadena en vez del miembro.
- El nombre de la rutina se guarda ya traducido (`labels.SPLIT_TYPE`); si se cambia el idioma, las rutinas antiguas conservan el nombre con el que se crearon.
- `exercise_lookup()` resuelve por nombre en español, en inglés o por slug, sin distinguir mayúsculas; dos ejercicios con el mismo nombre se pisarían (el catálogo no tiene duplicados: lo comprueban los tests de semillas).
- Las series se guardan contra el ejercicio **efectivo** (el sustituto si lo hay), no contra el prescrito: por eso no se puede sustituir con series ya registradas.
- `adjustments.apply()` no hace `commit()`: la ruta decide, y ante `SafetyError` hace `rollback()` y no deja nada a medias.
- `auth.delete_account()` sí hace `commit()`: es un borrado real en cascada y no tiene vuelta atrás.
- El PDF usa Helvetica, no las tipografías de la app: ReportLab necesita TTF y las nuestras están en woff2.
- La fila de auditoría de una revisión que cambia las calorías cuelga del plan **nuevo**, no del que cerró: así la próxima revisión se cuenta desde el cambio.

**Tests:** `tests/unit/services/` (`test_auth_service.py`, `test_onboarding_service.py`, `test_plans_service.py`, `test_dashboard_service.py`), `tests/integration/test_onboarding.py` y `tests/integration/test_plan_pages.py`. La fixture `seeded` de `tests/conftest.py` carga los catálogos reales (0,2 s).
