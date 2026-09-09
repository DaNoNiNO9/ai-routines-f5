# app/seeds/ — datos de referencia (equipamiento y ejercicios)

**Qué hace:** contiene los catálogos que la app necesita antes de poder generar rutinas (34 equipos, 190 ejercicios con imágenes) y los cargadores idempotentes que los meten en la base de datos con `flask seed ...`.

**Cómo funciona:**

1. `equipment.json` se escribe a mano: código estable, nombre es/en, categoría y orden.
2. `exercises.json` **se genera** con `python scripts/build_exercises.py` a partir de dos fuentes: la selección curada en `scripts/exercise_catalogue.py` (id de origen, nombre en español, patrón de movimiento, músculo primario, equipamiento necesario, unilateralidad, nivel y contraindicaciones) y el dataset público free-exercise-db (nombre en inglés, instrucciones, mecánica, fuerza, nivel, músculos secundarios e imágenes). El script descarga las dos imágenes de cada ejercicio, las reduce a 560 px y las guarda en `app/static/img/exercises/<slug>/`, calcula las alternativas (mismo patrón y músculo primario, hasta 4, priorizando otro material) y valida todo contra los enums.
3. `loaders.py` lee los JSON y hace *upsert* por `code` o `slug`: crea lo que falta, actualiza lo que cambió (incluidas relaciones de equipamiento y alternativas) y no toca lo demás. Cualquier entrada inválida aborta con `SeedError` y el mensaje señala la entrada.
4. `../cli.py` expone `flask seed equipment`, `flask seed exercises` y `flask seed all` (orden: equipamiento primero, los ejercicios lo referencian).

**Ficheros:**
- `equipment.json` — catálogo de material (fuente, editable).
- `exercises.json` — catálogo de ejercicios (generado, no editar a mano).
- `loaders.py` — `seed_equipment()`, `seed_exercises()`, `load_json_list()`, `SeedError`, `SeedResult`.
- `../../scripts/exercise_catalogue.py` — la curación: qué ejercicios entran y con qué metadatos propios.
- `../../scripts/build_exercises.py` — el generador (descarga, imágenes, alternativas, validación).
- `../static/img/exercises/<slug>/{0,1}.jpg` — ilustraciones (posición inicial y final).

**Por dónde tocar:**
- Añadir o quitar un ejercicio → `scripts/exercise_catalogue.py` (usar el `id` del dataset), después `python scripts/build_exercises.py` y `flask seed exercises`.
- Cambiar contraindicaciones, patrón, músculo o material de un ejercicio → misma entrada del catálogo y regenerar.
- Cambiar cómo se calculan las alternativas → `compute_alternatives()` en `build_exercises.py`.
- Añadir material → `equipment.json` (y, si procede, `app/engine/equipment_presets.py`), luego `flask seed equipment`.
- Traducir instrucciones al español → campo `instructions_es` (hoy vacío: las instrucciones están en inglés, ver limitación).
- Enlaces a vídeos concretos → campo `video_url`; hoy son búsquedas en YouTube (decisión T-25).

**Ojo con:**
- Semántica de `contraindications`: `min_severity` es la severidad declarada por el usuario a partir de la cual el ejercicio se excluye (`mild` excluye siempre que haya lesión en esa zona; `severe` solo en casos graves).
- `equipment` de un ejercicio es una conjunción: se necesitan todos los códigos. Para expresar alternativas de material hay dos entradas (por ejemplo remo invertido en barra y remo en suspensión).
- `is_bodyweight` se deriva del material: sin ningún elemento de carga (barras, mancuernas, máquinas, bandas...).
- El dataset se cachea en `scripts/cache/` (ignorado por git). Las imágenes que ya existen no se vuelven a descargar; para regenerarlas hay que borrar la carpeta.
- `seed_exercises()` falla a propósito si no hay equipamiento cargado.

**Tests:** `tests/unit/seeds/test_exercise_catalogue.py` (validez del JSON, imágenes en disco, cobertura de patrones por lugar de entrenamiento) y `tests/unit/seeds/test_exercise_seed.py` (carga, idempotencia, actualizaciones, errores y CLI).
