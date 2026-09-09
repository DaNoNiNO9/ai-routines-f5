# Fase 0 — Reconocimiento del entorno y esqueleto

Fecha: 2026-09-09. Estado: **cerrada, pendiente de visto bueno del propietario**.

## Qué se ha hecho

- Reconocimiento completo de la máquina de desarrollo → `docs/ENTORNO.md`.
- Tanda inicial de preguntas respondida y registrada → `docs/DECISIONES.md` (D-01 a D-11 de producto, T-01 a T-11 técnicas).
- Carpeta `D:\Proyectos\ai-routines-f5` con repositorio git propio (rama `main`, finales de línea LF normalizados).
- Entorno virtual `.venv` con Python 3.11.15 (intérprete base gestionado por uv) y pip 26.2.1.
- Dependencias directas fijadas en `requirements.in` y `requirements-dev.in`; árbol completo compilado con `uv pip compile --universal` a `requirements.txt` y `requirements-dev.txt`, con marcadores de plataforma para que el mismo fichero sirva en Linux. Instaladas y con el import de cada una verificado.
- Esqueleto: `app/__init__.py` con `create_app()` (factory) y dos rutas (`/` texto, `/health` JSON), `.flaskenv`, `pyproject.toml` (ruff, pytest, coverage), `.gitignore`, `.gitattributes`, `.editorconfig`.
- Tests de humo en `tests/test_smoke.py` (5 tests) con fixtures en `tests/conftest.py`.
- README raíz con instalación desde cero, variables de entorno, comandos y diagrama de la arquitectura objetivo.

## Qué se ha probado

| Prueba | Cómo | Resultado |
|---|---|---|
| Instalación de dependencias | `pip install -r requirements-dev.txt` en el venv | 46 paquetes, sin errores |
| Import de las 20 dependencias directas | Script Python (abajo) | OK todas, 0 fallos |
| Tests | `pytest --cov` | 5 passed, cobertura 100 % de `app/` (ramas incluidas) |
| Linter | `ruff check .` | All checks passed |
| Formato | `ruff format --check .` | 3 files already formatted |
| Servidor | `flask --app app run --port 5000 --no-reload` en segundo plano | Arranca en 127.0.0.1:5000 |
| `GET /` | `curl.exe -i` | 200, `Forja: Fase 0 operativa.` |
| `GET /health` | `curl.exe -i` | 200, `{"status": "ok", "version": "0.0.1"}` |
| `GET /no-existe` | `curl.exe -w %{http_code}` | 404 |
| Parada del servidor | `Stop-Process` + `Get-NetTCPConnection` | Puerto 5000 liberado |
| Logs del servidor | stdout/stderr redirigidos a fichero | 3 peticiones registradas, sin trazas de error |

Script de verificación de imports (ejecutado con `.venv\Scripts\python.exe`):

```python
import importlib
from importlib.metadata import version

MODULES = {
    "flask": "Flask", "sqlalchemy": "SQLAlchemy", "flask_sqlalchemy": "Flask-SQLAlchemy",
    "flask_migrate": "Flask-Migrate", "alembic": "alembic", "flask_wtf": "Flask-WTF",
    "wtforms": "WTForms", "email_validator": "email-validator", "flask_login": "Flask-Login",
    "argon2": "argon2-cffi", "flask_limiter": "Flask-Limiter", "flask_babel": "Flask-Babel",
    "babel": "Babel", "dotenv": "python-dotenv", "pythonjsonlogger": "python-json-logger",
    "waitress": "waitress", "pytest": "pytest", "pytest_cov": "pytest-cov",
    "coverage": "coverage", "hypothesis": "hypothesis",
}
for module, dist in MODULES.items():
    importlib.import_module(module)
    print(f"OK {dist} {version(dist)}")
```

## Errores aparecidos y cómo se corrigieron

1. **`python` del PATH era el venv de otro proyecto** (`hermes-agent`), sin pip; `python3` era el stub de la Microsoft Store. Corrección: venv creado con la ruta explícita del intérprete base de uv; documentado en `docs/ENTORNO.md` y en el README.
2. **URL del dataset de ejercicios equivocada** (`yuxiaoy/free-exercise-db` → 404). Corrección: el repositorio correcto es `yuhonas/free-exercise-db`; verificado (876 ejercicios, licencia Unlicense, 2 imágenes por ejercicio).
3. **El venv nace con pip 24.0** (versión empaquetada por `ensurepip`). Corrección: actualizado a 26.2.1 y añadido el paso al procedimiento de instalación.
4. **Cobertura inicial del 94,7 %**: la rama de `create_app()` sin `test_config` no se ejercitaba. Corrección: test `test_create_app_without_overrides_uses_defaults`; cobertura al 100 %.

## Pendiente

- URL del repositorio remoto en GitHub (decisión D-11): añadir `origin` y hacer `git push`.
- Fase 1: configuración por entorno (`config.py`, `.env.example`), logging estructurado a fichero y consola, manejo global de errores (404/500/CSRF), blueprints, `wsgi.py` y Flask-Babel cableado.

## Criterio de cierre

`flask --app app run` sirve el Hello World, verificado con `curl.exe`, y `pytest` ejecuta 5 tests en verde. Cumplido.
