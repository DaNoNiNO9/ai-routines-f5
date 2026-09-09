# Forja (working title: AI Routines F5)

**Qué hace:** aplicación web de planificación de entrenamiento y nutrición personalizada. El usuario rellena un cuestionario guiado y recibe un plan nutricional (calorías objetivo, macros, reparto por comidas), una rutina de gimnasio completa (split, ejercicios, series, reps, RIR, progresión, descargas) y un seguimiento que recalcula el plan con sus datos reales. Cada número sale de una fórmula documentada con su fuente citada en el código.

**Estado actual:** Fase 0 cerrada (entorno, esqueleto Flask, tests). Informes de cada fase en `docs/fases/`.

**Cómo funciona:** flujo objetivo; se completa por fases y lo que aún no existe lleva su fase entre paréntesis.

1. Cuestionario multi-paso (Fase 8) → perfil versionado en base de datos (Fase 2).
2. `app/engine/` (Fases 4-6): funciones puras, sin Flask ni base de datos. Composición corporal → BMR → TDEE por componentes → objetivo calórico → macros → rutina. `safety.py` es la última puerta antes de devolver cualquier plan.
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

flask run                             # http://127.0.0.1:5000 (configuración en .flaskenv)
```

Comprobación rápida: `curl.exe -i http://127.0.0.1:5000/health` debe devolver un JSON con `"status": "ok"`.

## Variables de entorno

| Variable | Dónde | Valor por defecto | Para qué |
|---|---|---|---|
| `FLASK_APP` | `.flaskenv` (versionado) | `app` | Paquete que expone `create_app()` |
| `FLASK_DEBUG` | `.flaskenv` | `1` | Depurador y recarga del servidor de desarrollo. Nunca en producción |
| `FLASK_RUN_PORT` | `.flaskenv` | `5000` | Puerto de `flask run` |

La Fase 1 añade `.env.example` con los secretos y la configuración por entorno. `.env` nunca se versiona.

## Comandos de desarrollo

| Comando | Qué hace |
|---|---|
| `flask run` | Servidor de desarrollo con recarga automática |
| `pytest` | Suite de tests |
| `pytest --cov` | Tests con cobertura de `app/`, ramas incluidas (`--cov-report=html` genera `htmlcov/`) |
| `ruff check .` | Linter |
| `ruff format .` | Formateador (`--check` solo verifica) |
| `uv pip compile --universal --python-version 3.11 requirements.in -o requirements.txt` | Recompilar dependencias tras tocar `requirements.in` (igual con `-dev`) |

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

Regla de dependencia: `engine/` no importa nada de Flask ni de `models/`. `services/` es la única capa que habla con ambos.

**Ficheros (raíz):**
- `app/__init__.py` — factory `create_app()`. Hoy solo dos rutas: `/` y `/health`.
- `tests/` — `conftest.py` (fixtures `app` y `client`) y `test_smoke.py`.
- `pyproject.toml` — configuración de ruff, pytest y coverage.
- `requirements.in` / `requirements-dev.in` — dependencias directas fijadas (fuente).
- `requirements.txt` / `requirements-dev.txt` — árbol completo compilado. Generados: no editar a mano.
- `.flaskenv` — variables no secretas del CLI de Flask.
- `docs/ENTORNO.md` — máquina de desarrollo, versiones y trampas.
- `docs/DECISIONES.md` — decisiones de producto y técnicas, con fecha.
- `docs/fases/` — informe de cierre de cada fase.

**Por dónde tocar:**
- Añadir o subir una dependencia → `requirements.in` (o `requirements-dev.in`), recompilar con el comando de arriba y reinstalar.
- Cambiar reglas de lint o de tests → `pyproject.toml`, tablas `[tool.ruff]` y `[tool.pytest.ini_options]`.
- Cambiar el puerto de desarrollo → `.flaskenv`, `FLASK_RUN_PORT`.
- Cambiar el nombre visible del producto → `APP_NAME` en `app/__init__.py` (pasará a `config.py` en la Fase 1).

**Ojo con:**
- `requirements*.txt` están generados: editar los `.in` y recompilar, nunca el `.txt`.
- En PowerShell, `curl` es un alias de `Invoke-WebRequest`; usa `curl.exe`.
- `FLASK_DEBUG=1` activa el depurador interactivo de Werkzeug: solo para desarrollo local.
- `pytest` corre con `--strict-config --strict-markers`: una clave desconocida en `pyproject.toml` o un marker no declarado hacen fallar la suite a propósito.
- ruff prohíbe `print()`, `except Exception` a ciegas y `datetime.now()` sin zona horaria. No es un capricho del linter: son las reglas de oro del proyecto.

**Tests:** en `tests/`. Desde la raíz, con el venv activado: `pytest`. Cobertura: `pytest --cov`.
