# app/services/ — orquestación entre web, modelos y motor

**Qué hace:** contiene la lógica de aplicación que no es ni cálculo puro (eso vive en `engine/`) ni presentación (blueprints y plantillas): cuentas, cuestionario y la conversión de un perfil en plan y rutina guardados. Los blueprints llaman a estas funciones y solo traducen resultados a mensajes y redirecciones.

**Cómo funciona:**

1. `auth.py` (Fase 7): registro con consentimiento, argon2id con rehash transparente, verificación ficticia para correos desconocidos, política de contraseñas por códigos, `load_user` para Flask-Login y tokens de recuperación firmados y caducables ligados al hash actual.
2. `onboarding.py` (Fase 8): el cuestionario se guarda paso a paso en `QuestionnaireDraft` (JSON plano: fechas ISO, enums por su valor, listas). `STEPS` define los siete pasos y las claves obligatorias de cada uno; `first_incomplete_step()` decide hasta dónde puede avanzar la persona y si puede revisar. `start_draft()` crea el borrador, pre-rellenado desde el perfil vigente si existe (`profile_to_data()`), para actualizar el cuestionario sin repetirlo entero. `complete()` convierte el borrador en una versión nueva de `Profile` (`data_to_profile_values()` revalida todo: un borrador manipulado nunca produce un perfil inválido), registra las lesiones, el material del usuario y el peso de hoy, llama a `plans.generate_for_profile()` y borra el borrador; todo en una transacción que se deshace si el motor rechaza los datos.
3. `plans.py` (Fase 8): `nutrition_inputs()` y `routine_inputs()` construyen las entradas del motor desde el perfil (edad calculada a la fecha, lesiones, hasta dos músculos prioritarios, material del usuario, déficit que la dieta no cubre por el suelo calórico). `load_catalogue()` convierte las filas activas de `exercises` en `ExerciseInfo`. `persist_plan()` y `persist_routine()` guardan versiones nuevas (`ACTIVE`), marcan la anterior como `SUPERSEDED`, guardan la instantánea de entradas y la salida completa del motor en `details` (con los mensajes ya renderizados en `details["messages"]`) y anotan la auditoría en `plan_adjustments` (`initial` la primera vez, `profile_change` después). `generate_for_profile()` orquesta: nutrición bloqueada por seguridad → no se guarda nada (ni rutina); rutina imposible con el material → se guarda solo la nutrición.

**Ficheros:**
- `auth.py` — cuentas y contraseñas.
- `onboarding.py` — pasos, borradores, perfil, catálogos para los formularios (`equipment_groups()`, `exercise_lookup()`), `complete()`.
- `plans.py` — entradas del motor, catálogo, persistencia de planes y rutinas, `active_plan()`, `active_routine()`, `GenerationResult`.

**Por dónde tocar:**
- Añadir una pregunta al cuestionario → columna en `Profile` (+ migración), campo en el formulario del paso (`blueprints/onboarding/forms.py`), plantilla del paso, `profile_to_data()` y `data_to_profile_values()` aquí, fila en `_summary()` de la vista de revisión y, si el motor la usa, `nutrition_inputs()` / `routine_inputs()`.
- Cambiar qué hace obligatorio un paso → `STEPS[...].required`.
- Guardar algo más al terminar el cuestionario (por ejemplo perímetros en `body_measurements`) → `complete()`.
- Cambiar cómo se versiona o se supersede un plan → `persist_plan()` / `persist_routine()`.

**Ojo con:**
- Nada en `plans.py` hace `commit()`: `complete()` (o el test) es dueño de la transacción.
- `details` y `inputs_snapshot` son JSON: `_jsonable()` del motor convierte enums, fechas y `frozenset` (ordenado). Si un tipo nuevo aparece en las dataclasses, hay que enseñárselo.
- Los enums de perfil se coaccionan con `Enum(valor)` al construir las entradas: un objeto recién creado puede llevar todavía la cadena en vez del miembro.
- El nombre de la rutina se guarda ya traducido (`labels.SPLIT_TYPE`); si se cambia el idioma, las rutinas antiguas conservan el nombre con el que se crearon.
- `exercise_lookup()` resuelve por nombre en español, en inglés o por slug, sin distinguir mayúsculas; dos ejercicios con el mismo nombre se pisarían (el catálogo no tiene duplicados: lo comprueban los tests de semillas).

**Tests:** `tests/unit/services/` (`test_auth_service.py`, `test_onboarding_service.py`, `test_plans_service.py`) y `tests/integration/test_onboarding.py`. La fixture `seeded` de `tests/conftest.py` carga los catálogos reales (0,2 s).
