# app/models/ — esquema de datos (SQLAlchemy 2.0 + Alembic)

**Qué hace:** define las 20 tablas de la aplicación con SQLAlchemy 2.0 (estilo `Mapped[...]`), portables entre SQLite (desarrollo) y PostgreSQL (producción). Las migraciones viven en `migrations/` (Flask-Migrate sobre Alembic) y se generan a partir de estos modelos. El detalle tabla a tabla está en `docs/MODELO_DATOS.md`.

**Cómo funciona:**

1. `app/extensions.py` crea `db` con una `Base` declarativa cuyo `MetaData` lleva la convención de nombres (`pk_`, `fk_`, `uq_`, `ck_`, `ix_`). Sin nombres deterministas, Alembic en modo *batch* (imprescindible en SQLite) no puede borrar constraints.
2. `base.py` aporta los tipos y mixins comunes: `UTCDateTime` (fechas siempre con zona horaria, normalizadas a UTC; rechaza fechas *naive*), `JSONType` (JSON en SQLite, JSONB en PostgreSQL), `enum_column()` (VARCHAR + CHECK con los valores del enum), `TimestampMixin` (`created_at`, `updated_at`) y `SoftDeleteMixin` (`deleted_at`).
3. Los enums de dominio (`Sex`, `Goal`, `MuscleGroup`...) viven en `app/engine/enums.py`, sin dependencias de Flask, para que motor, modelos y formularios compartan el mismo vocabulario.
4. Al importar `app.models` (lo hace `create_app()`), todas las tablas quedan registradas en `db.metadata`; Alembic las compara con la base de datos para autogenerar migraciones.
5. SQLite no aplica claves foráneas por defecto: `base.py` activa `PRAGMA foreign_keys=ON` en cada conexión, así los tests de integridad se comportan igual que en PostgreSQL.
6. Borrado: un usuario se borra en cascada con todo lo suyo (GDPR, borrado físico). Planes, rutinas y sesiones tienen además borrado lógico (`soft_delete()`) para que el usuario pueda deshacer. Los ejercicios referenciados por rutinas o series no se pueden borrar (`ondelete=RESTRICT`).

**Ficheros:**
- `base.py` — convención de nombres, `UTCDateTime`, `JSONType`, `enum_column()`, mixins, pragma de SQLite y `render_migration_item()` (cómo se escriben los tipos propios en las migraciones).
- `user.py` — `User` (con `UserMixin` de Flask-Login) y la tabla `user_equipment`.
- `profile.py` — `Profile` (cuestionario versionado, bloques A-E y banderas de seguridad) e `Injury`.
- `onboarding.py` — `QuestionnaireDraft`: respuestas parciales del cuestionario (JSON) y último paso completado, una por usuario.
- `tracking.py` — `WeightLog`, `BodyMeasurement`, `IntakeLog`, `ActivityLog` (una fila por usuario y día).
- `exercise.py` — `Equipment`, `Exercise`, `ExerciseAlternative` y la tabla `exercise_equipment`.
- `plan.py` — `Plan` (nutricional, versionado), `Meal`, `PlanAdjustment` (auditoría de recálculos).
- `routine.py` — `Routine` (versionada), `RoutineDay`, `RoutineExercise` (prescripción).
- `workout.py` — `WorkoutSession`, `SetLog`.
- `../seeds/` — `equipment.json` y `loaders.py` (cargas idempotentes); comandos en `../cli.py` (`flask seed equipment`, `flask seed all`).

**Por dónde tocar:**
- Añadir una columna → el modelo, luego `flask db migrate -m "descripción"`, revisar el fichero generado en `migrations/versions/` y `flask db upgrade`. El test `tests/integration/test_migrations.py` falla si la migración no coincide con los modelos.
- Añadir un valor a un enum → `app/engine/enums.py`; como los enums son VARCHAR + CHECK, hace falta migración (Alembic la genera en modo batch).
- Cambiar un rango permitido (por ejemplo el peso máximo) → el `CheckConstraint` del modelo y migración.
- Nueva tabla → nuevo fichero en este paquete, importarla en `__init__.py`, migración.
- Cambiar qué se borra en cascada → `ondelete` en la `ForeignKey` y `cascade` en la `relationship`.
- Añadir equipamiento → `app/seeds/equipment.json` y `flask seed equipment`.

**Ojo con:**
- Las fechas-hora deben ser *aware* (`datetime.now(tz=UTC)`); `UTCDateTime` lanza `ValueError` con fechas *naive*. Las fechas de calendario (`logged_on`, `birth_date`) son `date` sin zona.
- Los `UniqueConstraint` no llevan nombre explícito a propósito: la convención genera `uq_<tabla>_<columnas>`, que es único en todo el esquema (PostgreSQL exige nombres de índice únicos por esquema).
- Un enum usado dos veces en la misma tabla necesita `name=` distinto en `enum_column()` (ver `budget_level` y `cooking_time` en `Profile`).
- `Float` en vez de `Numeric`: SQLite no tiene decimales nativos y SQLAlchemy avisaría en cada consulta. Para pesos y medidas la precisión de `float` sobra.
- Las listas y objetos en columnas JSON (`priority_muscles`, `contraindications`, `details`) no tienen integridad referencial: los valida el código (seed loader, formularios, motor).
- `migrations/env.py` está editado a mano: `fileConfig(..., disable_existing_loggers=False)` para que Alembic no silencie el logger de la app.
- `db.create_all()` solo se usa en tests. En desarrollo y producción, siempre `flask db upgrade`.

**Tests:** `tests/unit/models/` (tipos, constraints, versionado, cascadas, catálogo, seeds y CLI) y `tests/integration/test_migrations.py` (upgrade, comparación migración-modelos, downgrade). Fixture `database` en `tests/conftest.py`; datos de prueba en `tests/factories.py`.
