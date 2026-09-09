# Forja (working title: AI Routines F5)

**Qué hace:** aplicación web de planificación de entrenamiento y nutrición personalizada. El usuario rellena un cuestionario guiado y recibe un plan nutricional (calorías objetivo, macros, reparto por comidas), una rutina de gimnasio completa (split, ejercicios, series, reps, RIR, progresión, descargas) y un seguimiento que recalcula el plan con sus datos reales. Cada número sale de una fórmula documentada con su fuente citada en el código.

**Estado actual:** Fase 12 cerrada: motor, autenticación, cuestionario, páginas del plan, registro real (diario, sesiones con temporizador, revisión quincenal) el diseño visual completo y la exportación (plan en PDF, datos en CSV), los ajustes de cuenta y el borrado RGPD. Siguiente: auditoría final (Fase 13). El estado vivo del proyecto está en `docs/ESTADO_ACTUAL.md`. Informes de cada fase en `docs/fases/`. Arquitectura en `docs/ARQUITECTURA.md`, esquema en `docs/MODELO_DATOS.md`, diseño en `docs/DISEÑO.md`.

**Cómo funciona:** flujo objetivo; se completa por fases y lo que aún no existe lleva su fase entre paréntesis.

1. Cuestionario multi-paso (Fase 8) → perfil versionado en base de datos (Fase 2).
2. `app/engine/`: funciones puras, sin Flask ni base de datos. Composición corporal → BMR → TDEE por componentes → objetivo calórico → macros → comidas (Fase 4) → rutina (Fase 5) → ajuste (Fase 6). `safety.py` es la última puerta antes de devolver cualquier plan.
3. `app/services/` orquesta motor y modelos y persiste planes y rutinas versionados.
4. Blueprints y plantillas Jinja2 muestran el plan; Alpine.js y Chart.js vendorizados para interacción y gráficas.
5. El usuario registra peso, medidas, ingesta y entrenos (Fase 10); el motor de ajuste (Fase 6) compara cada dos semanas lo real con lo esperado y recalcula.

## Instalación desde cero

Requisitos: Python 3.11 y git. En Windows se usa PowerShell; en Linux, bash.

```powershell
git clone <URL_DEL_REPO> ai-routines-f5
cd ai-routines-f5

# Usa un Python 3.11 real. En la máquina de desarrollo actual `python` a secas apunta
# a otro venv, así que se usa el alias `python3.11` (detalles en docs/ENTORNO.md).
python3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1          # Git Bash: source .venv/Scripts/activate | Linux: source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt   # incluye las dependencias de ejecución

copy .env.example .env                # Linux: cp .env.example .env ; ajusta SECRET_KEY si quieres
flask db upgrade                      # crea instance/forja.db con el esquema
flask seed all                        # catálogos de equipamiento y ejercicios
flask run                             # http://127.0.0.1:5000 (configuración en .flaskenv)
```

Comprobación rápida: `curl.exe -i http://127.0.0.1:5000/health` debe devolver un JSON con `"status": "ok"`.

## Variables de entorno

Las no secretas del CLI van en `.flaskenv` (versionado). El resto se leen del entorno o de `.env` (nunca versionado; plantilla en `.env.example`).

| Variable | Dónde | Valor por defecto | Para qué |
|---|---|---|---|
| `FLASK_APP` | `.flaskenv` | `app` | Paquete que expone `create_app()` |
| `FLASK_DEBUG` | `.flaskenv` | `1` | Depurador y recarga del servidor de desarrollo. Nunca en producción |
| `FLASK_RUN_PORT` | `.flaskenv` | `5000` | Puerto de `flask run` |
| `FORJA_ENV` | `.env` | `development` | `development`, `testing` o `production` (elige la clase de `config.py`) |
| `SECRET_KEY` | `.env` | clave insegura solo en desarrollo | Firma de sesiones y tokens CSRF. Obligatoria en producción (32+ caracteres) |
| `DATABASE_URL` | `.env` | vacío → `instance/forja.db` (SQLite) | Producción: `postgresql+psycopg://usuario:clave@host:5432/forja` |
| `LOG_LEVEL` | `.env` | `DEBUG` en dev, `INFO` en el resto | Nivel del logger `app` |
| `LOG_DIR` | `.env` | `logs/` | Carpeta de `forja.log` (JSON por línea, rotación 5 MB x 5) |
| `RATELIMIT_STORAGE_URI` | `.env` | `memory://` | Almacén del rate limiting; con varios workers usar Redis |
| `SQLALCHEMY_ECHO` | `.env` | `0` | Volcar SQL en el log (solo desarrollo) |
| `MAIL_BACKEND` | `.env` | `log` | `log` deja los correos en el log (desarrollo); `smtp` los envía (obligatorio en producción) |
| `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM` | `.env` | puerto 587, TLS activo | Servidor SMTP para la recuperación de contraseña |

## Comandos de desarrollo

| Comando | Qué hace |
|---|---|
| `flask run` | Servidor de desarrollo con recarga automática |
| `flask run --no-reload` | Un solo proceso (útil para pruebas con `curl`) |
| `flask db upgrade` / `flask db downgrade -1` | Aplicar o deshacer migraciones |
| `flask db migrate -m "descripción"` | Autogenerar una migración tras cambiar modelos (revisar el fichero) |
| `flask seed equipment` / `flask seed exercises` / `flask seed all` | Cargar datos de referencia (idempotente) |
| `python scripts/build_exercises.py` | Regenerar `app/seeds/exercises.json` y las imágenes desde la curación de `scripts/exercise_catalogue.py` |
| `pytest` | Suite de tests |
| `pytest --cov` | Tests con cobertura de `app/`, ramas incluidas (`--cov-report=html` genera `htmlcov/`) |
| `pytest tests/unit/engine --cov=app/engine` | Solo el motor, con su cobertura (objetivo ≥ 95 %) |
| `ruff check .` | Linter |
| `ruff format .` | Formateador (`--check` solo verifica) |
| `waitress-serve --port 8000 wsgi:app` | Servidor de producción en Windows o Linux (`FORJA_ENV=production`) |
| `uv pip compile --universal --python-version 3.11 requirements.in -o requirements.txt` | Recompilar dependencias tras tocar `requirements.in` (igual con `-dev`) |

Rutas de diagnóstico, solo en desarrollo y testing: `/_debug/boom` (provoca un 500), `/_debug/echo` (formulario con CSRF), `/_debug/limited` (2 peticiones por minuto), `/_debug/abort/<código>`.

## Traducciones

Los textos se marcan con `{{ _('...') }}` en plantillas y `lazy_gettext` en Python desde el principio. Los catálogos se generan al final del proyecto:

```powershell
pybabel extract -F babel.cfg -k _l -o messages.pot .
pybabel init -i messages.pot -d app/translations -l en     # solo la primera vez
pybabel update -i messages.pot -d app/translations         # siguientes veces
pybabel compile -d app/translations
```

## Arquitectura (objetivo)

```
 Navegador (Jinja2 + Alpine.js + Chart.js vendorizados)
        │ HTTP
 ┌──────▼──────────────────────────────────────────────┐
 │ Flask: create_app() · blueprints (auth, onboarding, │
 │ dashboard, nutrition, training, tracking, account,  │
 │ api) · forms (WTForms) · errors · logging           │
 └──────┬──────────────────────────────────────────────┘
        │
 ┌──────▼───────┐          ┌────────────────────────────┐
 │ services/    │ ───────► │ engine/ (funciones puras)  │
 │ orquestación │          │ nutrición · rutinas ·      │
 │              │          │ ajuste · safety (última    │
 └──────┬───────┘          │ puerta)                    │
        │                  └────────────────────────────┘
 ┌──────▼───────────────────────────┐
 │ models/ (SQLAlchemy) + Alembic   │
 │ SQLite en dev · PostgreSQL prod  │
 └──────────────────────────────────┘
```

Regla de dependencia: `engine/` no importa nada de Flask ni de `models/`. `services/` es la única capa que habla con ambos. Detalle en `docs/ARQUITECTURA.md`.

**Ficheros (raíz):**
- `app/` — capa web. Su `README.md` explica factory, configuración, errores, logging, seguridad, autenticación, correo y diseño.
- `app/services/` — orquestación entre motor, modelos y web (`auth.py`, `onboarding.py`, `plans.py`, `dashboard.py`, `tracking.py`, `workouts.py`, `adjustments.py`); ver su `README.md`.
- `app/models/` — esquema SQLAlchemy 2.0 (20 tablas). Su `README.md` explica tipos, mixins, cascadas y cómo migrar.
- `app/engine/` — motor de cálculo. Su `README.md` recorre cada etapa con sus fórmulas y fuentes y dice qué constante tocar para cambiar cada regla.
- `app/engine/enums.py` — vocabulario de dominio compartido por motor, modelos y formularios.
- `app/seeds/` — datos de referencia (`equipment.json`, `exercises.json` generado) y cargadores idempotentes; comandos en `app/cli.py`. Su `README.md` explica cómo se genera el catálogo.
- `scripts/` — `exercise_catalogue.py` (curación de 190 ejercicios) y `build_exercises.py` (generador con descarga de imágenes).
- `app/static/img/exercises/` — 380 ilustraciones de dominio público (ver `docs/CREDITOS.md`).
- `migrations/` — Alembic (Flask-Migrate). `env.py` editado a mano: engine directo y sin silenciar loggers.
- `config.py` — clases de configuración por entorno y validación de producción.
- `wsgi.py` — punto de entrada para waitress o gunicorn.
- `tests/` — `conftest.py` (fixtures `make_app`, `app`, `client`), `test_smoke.py` e `integration/`.
- `pyproject.toml` — configuración de ruff, pytest y coverage.
- `requirements.in` / `requirements-dev.in` — dependencias directas fijadas (fuente).
- `requirements.txt` / `requirements-dev.txt` — árbol completo compilado. Generados: no editar a mano.
- `.flaskenv` — variables no secretas del CLI de Flask. `.env.example` — plantilla del resto.
- `babel.cfg` — qué ficheros rastrea pybabel.
- `docs/ENTORNO.md` — máquina de desarrollo, versiones y trampas.
- `docs/DECISIONES.md` — decisiones de producto y técnicas, con fecha.
- `docs/ARQUITECTURA.md` — capas, ciclo de petición, convenciones.
- `docs/MODELO_DATOS.md` — tablas, relaciones, rangos comprobados y flujo de migraciones.
- `docs/CREDITOS.md` — origen y licencia de cada recurso externo.
- `docs/fases/` — informe de cierre de cada fase.

**Por dónde tocar:**
- Añadir o subir una dependencia → `requirements.in` (o `requirements-dev.in`), recompilar con el comando de arriba y reinstalar.
- Nueva variable de configuración → `config.py` (`BaseConfig` y la subclase que la cambie), `.env.example` y la tabla de arriba.
- Cambiar reglas de lint o de tests → `pyproject.toml`, tablas `[tool.ruff]` y `[tool.pytest.ini_options]`.
- Cambiar el puerto de desarrollo → `.flaskenv`, `FLASK_RUN_PORT`.
- Cambiar el nombre visible del producto → `APP_NAME` en `config.py`.

**Ojo con:**
- Nunca `db.create_all()` fuera de los tests: el esquema se crea y evoluciona solo con `flask db upgrade`.
- `app/seeds/exercises.json` está generado: se edita la curación en `scripts/exercise_catalogue.py` y se regenera.
- `requirements*.txt` están generados: editar los `.in` y recompilar, nunca el `.txt`.
- En PowerShell, `curl` es un alias de `Invoke-WebRequest`; usa `curl.exe`.
- Con `FLASK_DEBUG=1` un error 500 muestra el depurador de Werkzeug, no la página de error de la app. Para ver la página real: `$env:FLASK_DEBUG="0"; flask run --no-reload`.
- Producción no arranca sin `SECRET_KEY` y `DATABASE_URL`, ni con `DEBUG` o `ENABLE_DEBUG_ROUTES` activos. Es a propósito.
- `pytest` corre con `--strict-config --strict-markers`: una clave desconocida en `pyproject.toml` o un marker no declarado hacen fallar la suite a propósito.
- ruff prohíbe `print()`, `except Exception` a ciegas y `datetime.now()` sin zona horaria. No es un capricho del linter: son las reglas de oro del proyecto.

**Tests:** en `tests/`. Desde la raíz, con el venv activado: `pytest`. Cobertura: `pytest --cov`.
