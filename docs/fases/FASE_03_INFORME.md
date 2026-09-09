# Fase 3 — Base de datos de ejercicios

Fecha: 2026-09-09. Estado: **cerrada**.

## Qué se ha hecho

- Fuente elegida y verificada: free-exercise-db (876 ejercicios, licencia The Unlicense confirmada por la API de GitHub, imágenes JPEG por ejercicio). Registrada en `docs/CREDITOS.md`.
- Curación propia de **190 ejercicios** en `scripts/exercise_catalogue.py`: id de origen, nombre en español, patrón de movimiento (8 patrones), músculo primario (14 grupos), equipamiento necesario con nuestros códigos, unilateralidad, nivel técnico y contraindicaciones por lesión (`{area, min_severity}`) revisadas una a una.
- Generador `scripts/build_exercises.py`: fusiona la curación con el dataset (nombre en inglés, instrucciones, mecánica, fuerza, nivel, músculos secundarios), descarga las dos ilustraciones de cada ejercicio, las reduce (560 px, JPEG 75) a `app/static/img/exercises/<slug>/`, calcula hasta 4 alternativas por ejercicio (mismo patrón y músculo, otro material primero), valida contra los enums y escribe `app/seeds/exercises.json` (190 entradas, 702 alternativas).
- Cargador `seed_exercises()` en `app/seeds/loaders.py`: *upsert* por slug con relaciones de equipamiento y alternativas, validación completa con `SeedError`, exige equipamiento cargado. Comandos `flask seed exercises` y `flask seed all`.
- `app/engine/equipment_presets.py`: material asumido por lugar de entrenamiento (gimnasio completo, básico, casa con material, casa sin material), compartido por tests, cuestionario y generador.
- Dos códigos de máquina nuevos en `equipment.json` (abductores/aductores, curl de bíceps): 34 equipos.
- Pillow 12.3.0 añadido a las dependencias de desarrollo (solo para el generador).
- Documentación: `app/seeds/README.md`, `docs/CREDITOS.md`, README raíz, `docs/DECISIONES.md` (T-25 a T-30).

## Qué se ha probado

| Prueba | Cómo | Resultado |
|---|---|---|
| Suite completa | `pytest --cov` | 113 passed; cobertura de `app/` 99 % |
| Linter y formato | `ruff check .`, `ruff format --check .` | limpios |
| Tamaño del catálogo | test | 190 ≥ 150 |
| Vocabulario | test que valida cada campo contra los enums, slugs únicos y bien formados, primario no repetido en secundarios | OK (3 ejercicios sin instrucciones en el dataset, tolerancia del 3 %) |
| Material | test: todos los códigos existen en `equipment.json`; `is_bodyweight` coherente con el material | OK |
| Alternativas | test: apuntan a otro ejercicio existente con el mismo patrón y músculo; prioridades únicas; más del 90 % de los ejercicios tienen alternativa | OK |
| Cobertura de patrones por nivel de material | test parametrizado por lugar de entrenamiento: cada patrón con ≥ 2 ejercicios (≥ 1 sin material, donde la tracción vertical queda excluida por necesitar barra) | OK en los 4 presets |
| Opciones para principiantes en casa | test: cada patrón tiene al menos un ejercicio de nivel principiante con el material de casa | OK |
| Grupos musculares | test: cada grupo con ≥ 2 ejercicios como primario | OK |
| Imágenes | test: 2 ficheros locales por ejercicio, ninguno > 120 KB, total < 15 MB | 380 imágenes, 11,5 MB |
| Carga en BD | tests: sin equipamiento → error claro; carga completa (190 creados); segunda pasada 0/0; cambios en nombre, material y alternativas se reparan (2 actualizados); 7 tipos de entrada inválida rechazados con mensaje; slug duplicado rechazado | OK |
| CLI | tests: `seed all` y `seed exercises` idempotentes; `seed exercises` sin equipamiento → exit 1 | OK |
| BD de desarrollo | `flask seed all` dos veces sobre `instance/forja.db` | `190 created` y luego `0 created, 0 updated`; consulta SQL de comprobación |

## Errores aparecidos y cómo se corrigieron

1. **Imágenes demasiado pesadas** (18 MB a 640 px / calidad 82). Corrección: recodificadas en local a 560 px / calidad 75 (11,5 MB) y parámetros del generador ajustados; test que acota el tamaño.
2. **Tres ejercicios sin instrucciones en el dataset** (por ejemplo el swing con kettlebell): el test exigía texto en todos. Corrección: tolerancia del 3 % y campo presente; la UI mostrará imagen y vídeo.
3. **Clausura sobre variable de bucle** (ruff B023) al ordenar alternativas. Corrección: función de rango con `functools.partial`.
4. **Líneas largas en la tabla de curación**: regla E501 relajada solo para ese fichero de datos.
5. **Dos máquinas sin código** (abductores/aductores, curl de bíceps) necesarias para ejercicios curados. Corrección: añadidas a `equipment.json`.

## Limitaciones conocidas

- Instrucciones solo en inglés (`instructions_es` vacío). Traducirlas queda como tarea posterior (T-29).
- `video_url` es una búsqueda en YouTube, no un vídeo concreto (T-25).
- Sin material ninguno no hay tracción vertical posible: el generador deberá avisarlo y sugerir una barra de dominadas o bandas.

## Pendiente

- Fase 4: motor de cálculo nutricional (§3.2 a §3.6) como funciones puras y `safety.py`, con ≥ 40 tests y cobertura ≥ 95 %.

## Criterio de cierre

Seed cargado y test que verifica la cobertura de todos los patrones de movimiento con cada nivel de material. Cumplido.
