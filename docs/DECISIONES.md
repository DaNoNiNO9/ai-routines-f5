# Decisiones de producto y técnicas

Registro de las decisiones tomadas con el propietario del proyecto. Cada entrada lleva fecha. Si una decisión cambia, se añade una entrada nueva que la sustituye y enlaza la anterior; no se borra nada.

## 2026-09-09 — Arranque (Fase 0)

### Decisiones de producto (respondidas por el propietario)

| ID | Tema | Decisión | Alternativas descartadas |
|---|---|---|---|
| D-01 | Carpeta y nombre | Carpeta `D:\Proyectos\ai-routines-f5`, paquete Python `app`, nombre visible del producto **Forja** (constante `APP_NAME`, fácil de cambiar) | Carpeta `forja/` |
| D-02 | Python | 3.11.15, el único instalado (gestionado por uv). Objetivo de compatibilidad: 3.11 | Instalar 3.12 / 3.13 con uv |
| D-03 | Migraciones | Flask-Migrate (Alembic integrado en la factory): `flask db migrate` / `upgrade` / `downgrade` | Alembic puro |
| D-04 | Idiomas | Identificadores, comentarios y docstrings **en inglés**. UI, documentación (`docs/`, READMEs), informes de fase y mensajes de commit **en español** | Todo en español; todo en inglés |
| D-05 | Traducciones | Flask-Babel + pybabel. Se cablea en la Fase 1 y todos los textos de UI se marcan con `_()` desde el principio; los catálogos (inglés) se generan en una fase aparte al final, para no mezclar | Traducir al final (retrofit caro) |
| D-06 | Ámbito | Multiusuario. Desarrollo en Windows; despliegue futuro en VPS Linux con PostgreSQL y gunicorn. Email de recuperación de contraseña: log/consola en dev, SMTP configurado por `.env` en prod | Uso personal local |
| D-07 | Registro de ingesta | Registro diario simple: kcal y macros del día introducidos a mano, más indicador de adherencia. Es lo que alimenta la estimación de TDEE observado del motor de ajuste (§3.8) | Diario de comidas con BD de alimentos; sin registro |
| D-08 | Frontend | Jinja2 + Alpine.js 3.17 + Chart.js 4.5 vendorizados en `app/static/vendor/`, CSS propio con design tokens, sin build step | JS vanilla puro; HTMX + Alpine |
| D-09 | Unidades | Solo métrico (kg, cm, ml) | Métrico + imperial |
| D-10 | Ejercicios | Fuente base free-exercise-db (`yuhonas/free-exercise-db`, 876 ejercicios, Unlicense, con imágenes): traducir al español, curar 150-250 y enriquecer con patrón de movimiento, contraindicaciones, alternativas y enlace a vídeo de YouTube (solo enlace, no embebido) | wger (CC-BY-SA); base manual desde cero |
| D-11 | Git | Repo local en la carpeta del proyecto, rama `main`, identidad global de git (Daniel). Remoto en GitHub: **pendiente de recibir la URL del repo vacío** | Solo local |

### Decisiones técnicas tomadas por el ingeniero (revisables)

| ID | Tema | Decisión | Motivo |
|---|---|---|---|
| T-01 | Entorno virtual | `python -m venv .venv` + pip. `uv` solo para compilar los requirements (acelerador opcional, no dependencia) | Cualquier máquina con Python 3.11 y pip reproduce el entorno |
| T-02 | Dependencias | Directas fijadas en `requirements.in` / `requirements-dev.in`; `requirements*.txt` compilados con `uv pip compile --universal` (todo el árbol fijado, con marcadores de plataforma) | Reproducible en Windows y Linux con el mismo fichero |
| T-03 | Linter y formateador | ruff con las reglas de `pyproject.toml`. Incluye BLE, S110, S112, T20, DTZ, G, LOG y TRY para hacer cumplir la regla de oro 4 (cero errores silenciosos) y las fechas con zona horaria | Una sola herramienta, rápida |
| T-04 | Tests | pytest + pytest-cov (ramas) + hypothesis para el motor. `--strict-config --strict-markers --import-mode=importlib` | Property-based testing para fórmulas; sin `__init__.py` en tests |
| T-05 | Logging | `logging` estándar: JSON a fichero (python-json-logger) y formato legible en consola | Menos piezas que structlog |
| T-06 | Cabeceras de seguridad | A mano en un `after_request` | Flask-Talisman sin releases desde 2023 |
| T-07 | Contraseñas | argon2id (argon2-cffi) | Recomendación OWASP actual |
| T-08 | Fechas | Se guardan en UTC, siempre timezone-aware; se muestran en Europe/Madrid | Regla DTZ de ruff lo vigila |
| T-09 | Servidor | `flask run` en dev; waitress (Windows) o gunicorn (Linux) en prod a través de `wsgi.py` (Fase 1) | |
| T-10 | Estilo | Línea de 100 caracteres, comillas dobles, docstrings estilo Google | |
| T-11 | Exportación a PDF | Pendiente hasta la Fase 12: WeasyPrint exige GTK en Windows; alternativas reportlab o CSS de impresión | Se decide con el propietario en su momento |
