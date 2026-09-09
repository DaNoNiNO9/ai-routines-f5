# Fase 2 — Modelos y migraciones

Fecha: 2026-09-09. Estado: **cerrada**.

## Qué se ha hecho

- Vocabulario de dominio en `app/engine/enums.py` (27 `StrEnum`: sexo, objetivo, patrón de movimiento, grupo muscular, lesiones, estados...), sin dependencias de Flask, compartido por motor, modelos y formularios.
- Infraestructura común en `app/models/base.py`: `UTCDateTime` (solo fechas-hora *aware*, normalizadas a UTC), `JSONType` (JSONB en PostgreSQL), `enum_column()` (VARCHAR + CHECK), `TimestampMixin`, `SoftDeleteMixin`, `PRAGMA foreign_keys=ON` en SQLite y `render_migration_item()` para que las migraciones no importen código de la app. Convención de nombres de constraints en la `Base` declarativa.
- 20 tablas en SQLAlchemy 2.0 (`Mapped[...]`): `users`, `user_equipment`, `profiles` (versionado, bloques A-E y banderas de seguridad), `injuries`, `weight_logs`, `body_measurements`, `intake_logs`, `activity_logs`, `equipment`, `exercises`, `exercise_equipment`, `exercise_alternatives`, `plans`, `meals`, `plan_adjustments`, `routines`, `routine_days`, `routine_exercises`, `workout_sessions`, `set_logs`. Claves foráneas con `ondelete` (CASCADE desde el usuario, RESTRICT en ejercicios usados, SET NULL en referencias opcionales), 40+ CHECK de rangos, únicos por (usuario, día) y (usuario, versión), índices en columnas de consulta.
- Alembic con Flask-Migrate: `flask db init`, `env.py` ajustado (`disable_existing_loggers=False`, `db.engine` directo) y primera migración `196ae6a460b6_esquema_inicial.py` autogenerada y revisada (20 `create_table`, solo tipos estándar).
- Seeds: `app/seeds/equipment.json` (32 equipos con nombre es/en y categoría) y `app/seeds/loaders.py` (carga idempotente con validación y `SeedError`); comandos `flask seed equipment` y `flask seed all` en `app/cli.py`.
- Tests: `tests/factories.py`, `tests/unit/models/` (4 ficheros) y `tests/integration/test_migrations.py`. Fixture `database` (esquema en memoria por test).
- Documentación: `app/models/README.md`, `docs/MODELO_DATOS.md` (tablas, diagrama ER, rangos, migraciones), README raíz (instalación con `flask db upgrade` y `flask seed all`, comandos), `docs/DECISIONES.md` (T-17 a T-24).

## Qué se ha probado

| Prueba | Cómo | Resultado |
|---|---|---|
| Suite completa | `pytest --cov` | 85 passed; cobertura de `app/` 99 % |
| Linter y formato | `ruff check .`, `ruff format --check .` | limpios (código generado por Alembic con reglas relajadas) |
| `flask db upgrade` sobre `instance/forja.db` | CLI | 20 tablas + `alembic_version`, revisión `196ae6a460b6 (head)` |
| `flask db downgrade base` | CLI | solo queda `alembic_version`; `upgrade` posterior recrea las 20 tablas |
| Migración = modelos | `tests/integration/test_migrations.py` con `compare_metadata` sobre una BD de fichero migrada | sin diferencias; `downgrade base` limpio; `upgrade` de nuevo correcto |
| Migración sin tipos de la app | test que inspecciona `migrations/versions/*.py` | sin `app.models` ni `UTCDateTime` |
| `flask seed equipment` dos veces | CLI | `32 created, 0 updated` y luego `0 created, 0 updated` |
| Integridad referencial en SQLite | tests con `PRAGMA foreign_keys` | FK inexistente → `IntegrityError`; borrar ejercicio en uso → `IntegrityError` |
| Constraints | tests parametrizados | rangos de perfil, únicos por día/versión/posición, `rep_max >= rep_min`, `finished_at >= started_at`, alternativa ≠ ejercicio |
| Cascadas | test que borra un usuario con perfil, lesiones, pesos, plan, comidas, ajuste, rutina, sesión y series | todas las tablas del usuario a 0; el ejercicio del catálogo sobrevive |
| Tipos | tests de `UTCDateTime` (rechaza naive, normaliza offsets), enums (valor almacenado como texto, valor desconocido rechazado), JSON (ida y vuelta) | OK |
| Servidor real con la BD migrada | `flask run --no-reload` + `curl.exe` | `/health` 200, `/` 200, puerto liberado |

## Errores aparecidos y cómo se corrigieron

1. **`Mapped[datetime]` con el import bajo `TYPE_CHECKING`** en `exercise.py`: SQLAlchemy necesita el tipo en tiempo de ejecución para resolver la anotación. Corrección: import real.
2. **Migración autogenerada no ejecutable**: Alembic renderizó el tipo JSON/JSONB con `astext_type=Text()` sin importar `Text`; el primer `upgrade` falló a mitad (SQLite no es transaccional en DDL, quedó una tabla huérfana). Corrección: `render_migration_item()` emite `sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')` y añade el import; BD de desarrollo recreada y migración regenerada.
3. **Nombres de `UniqueConstraint` no únicos entre tablas** (`user_day` en cuatro tablas): en PostgreSQL los índices comparten espacio de nombres por esquema y habrían colisionado. Corrección: sin nombre explícito, la convención genera `uq_<tabla>_<columnas>`; migración regenerada.
4. **`fileConfig` de Alembic silenciaba el logger de la app** (`disable_existing_loggers=True` por defecto) y `get_engine()` está obsoleto en Flask-SQLAlchemy 3.1. Corrección: `env.py` editado a mano y documentado.
5. **Avisos de ruff**: `TRY400` en el CLI (ahora `logger.exception`), `ARG002` en `TypeDecorator`, código generado por Alembic (reglas relajadas solo para `migrations/`), dos `datetime` naive deliberados en tests (`noqa: DTZ001`).

## Pendiente

- Fase 3: catálogo de 150+ ejercicios desde free-exercise-db (traducción, patrón de movimiento, contraindicaciones, alternativas, imágenes locales, enlaces a vídeo) y `flask seed exercises`, con test de cobertura de patrones por nivel de material.
- `LoginManager` (Fase 7) usará `User`, que ya incluye `UserMixin`.

## Criterio de cierre

`flask db upgrade` y `flask db downgrade` funcionan (probado a mano y en test); tests de modelos y constraints en verde. Cumplido.
