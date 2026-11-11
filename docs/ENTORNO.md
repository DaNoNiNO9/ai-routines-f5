# Entorno de desarrollo

Reconocimiento realizado el 2026-09-09 en la máquina de desarrollo (Fase 0). Si algo de esto cambia (otro PC, otro Python), actualiza este fichero.

## Resumen de decisiones de entorno

| Decisión | Valor |
|---|---|
| Intérprete | CPython 3.11.15 (gestionado por `uv`), ruta más abajo |
| Entorno virtual | `.venv/` en la raíz del proyecto, creado con `python -m venv` |
| pip dentro del venv | 26.2.1 (el venv nace con 24.0 vía `ensurepip` y se actualiza) |
| Dependencias | Directas fijadas en `requirements.in` / `requirements-dev.in`; árbol completo compilado a `requirements.txt` / `requirements-dev.txt` con `uv pip compile --universal` |
| Puerto de desarrollo | 5000 (`.flaskenv`) |
| BD de desarrollo | SQLite vía el módulo `sqlite3` de Python (librería 3.53.1) |

## Sistema

| Elemento | Valor |
|---|---|
| SO | Microsoft Windows 11 Pro 10.0.26200 (build 26200), 64 bits, AMD64 |
| CPU / RAM | AMD Ryzen 7 5800X (8 núcleos) / 31,9 GB |
| Shell principal | PowerShell 5.1 (sin `&&`, sin `?:`) |
| Shell secundaria | Git Bash (`D:\Git`) |
| Locale / zona horaria | es-ES / Romance Standard Time (Europe/Madrid) |
| Consola | UTF-8 |

## Python

- `python` en el PATH apunta a `C:\Users\ddany\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe`: es el venv de **otro** proyecto y no tiene `pip`. **No usar.**
- `python3` en el PATH es el stub de Microsoft Store (no hay Python detrás). **No usar.**
- El launcher `py` no está disponible.
- Único intérprete base real: **CPython 3.11.15**, gestionado por `uv 0.12.3` (`C:\Users\ddany\AppData\Local\hermes\bin\uv.exe`):
  - `C:\Users\ddany\AppData\Roaming\uv\python\cpython-3.11.15-windows-x86_64-none\python.exe`
  - alias en el PATH: `C:\Users\ddany\.local\bin\python3.11.exe`
  - trae `pip 26.2.1`, `venv` y `ensurepip 24.0`.
- SQLite embebido en ese Python: **3.53.1** (soporta `RETURNING`, tablas `STRICT`, funciones JSON).
- Versiones descargables con `uv python install` si hiciera falta: 3.12.13, 3.13.15, 3.14.7, 3.15.0rc1.
- El venv del proyecto se creó con la ruta explícita del intérprete base:

  ```powershell
  C:\Users\ddany\AppData\Roaming\uv\python\cpython-3.11.15-windows-x86_64-none\python.exe -m venv .venv
  .\.venv\Scripts\python.exe -m pip install --upgrade pip
  ```

## Node.js

- node v24.18.1, npm 11.16.0 (`C:\Program Files\nodejs`). Solo se usará, si acaso, para descargar assets JS a vendorizar. No hay build step.

## Bases de datos y contenedores

- `sqlite3` CLI: no instalado. La BD se inspecciona con `flask shell` o con Python (`import sqlite3`).
- PostgreSQL: no instalado, sin servicio. Llegará con el despliegue (VPS Linux).
- Docker: no instalado.

## Git

- git 2.55.0.windows.2 (`D:\Git\cmd`).
- Identidad global: `user.name=Daniel`, `user.email=ddany0332@gmail.com`.
- Sin `core.autocrlf` ni `init.defaultBranch` globales. En el repo: rama `main`, `core.autocrlf=false`, `core.eol=lf` y `.gitattributes` con `* text=auto eol=lf`.
- `D:\Proyectos` **no** es repositorio git; el proyecto tiene el suyo en `D:\Proyectos\ai-routines-f5`.
- `gh` CLI: no instalado. El remoto de GitHub se añade a mano con `git remote add origin <url>`.
- Remoto: `origin` → `https://github.com/DaNoNiNO9/ai-routines-f5.git` (añadido el 2026-11-11). La autenticación HTTPS la gestiona el Git Credential Manager de Git for Windows.

## Red y puertos

- Puertos 5000, 5001, 8000 y 8080 libres en el momento del reconocimiento. Se usa el **5000** (en Windows no existe el conflicto con AirPlay de macOS).
- `curl 8.21.0` en `C:\WINDOWS\system32\curl.exe`. En PowerShell hay que invocar **`curl.exe`**: `curl` a secas es un alias de `Invoke-WebRequest`.
- `wget`: no existe como binario (también es alias de `Invoke-WebRequest`).
- PyPI y el registro de npm son alcanzables.

## Disco y permisos

- Unidad D: 662,5 GB libres (269 GB usados).
- Escritura en `D:\Proyectos` verificada creando y borrando un fichero temporal.

## Dependencias: versiones consultadas en PyPI (2026-09-09)

| Paquete | Última versión | Fecha | requires_python | Uso |
|---|---|---|---|---|
| Flask | 3.1.3 | 2026-02-19 | >=3.9 | runtime |
| Werkzeug | 3.1.8 | 2026-04-02 | >=3.9 | transitiva (Flask) |
| Jinja2 | 3.1.6 | 2025-03-05 | >=3.7 | transitiva (Flask) |
| SQLAlchemy | 2.0.52 | 2026-08-11 | >=3.7 | runtime |
| Flask-SQLAlchemy | 3.1.1 | 2023-09-11 | >=3.8 | runtime |
| alembic | 1.19.2 | 2026-09-04 | >=3.10 | runtime |
| Flask-Migrate | 4.1.0 | 2025-01-10 | >=3.6 | runtime |
| Flask-WTF | 1.3.0 | 2026-04-23 | >=3.10 | runtime |
| WTForms | 3.2.2 | 2026-05-03 | >=3.10 | runtime |
| email-validator | 2.3.0 | 2025-08-26 | >=3.8 | runtime |
| Flask-Login | 0.6.3 | 2023-10-30 | >=3.7 | runtime |
| argon2-cffi | 25.1.0 | 2025-06-03 | >=3.8 | runtime |
| Flask-Limiter | 4.1.1 | 2025-12-06 | >=3.10 | runtime |
| Flask-Babel | 4.0.0 | 2023-10-02 | >=3.8,<4.0 | runtime (i18n, D-05) |
| Babel | 2.18.0 | 2026-02-01 | >=3.8 | runtime |
| python-dotenv | 1.2.3 | 2026-08-16 | >=3.10 | runtime |
| python-json-logger | 4.2.0 | 2026-08-15 | >=3.10 | runtime (logging JSON) |
| waitress | 3.0.2 | 2024-11-16 | >=3.9 | runtime (servidor WSGI) |
| pytest | 9.1.1 | 2026-06-19 | >=3.10 | dev |
| pytest-cov | 7.1.0 | 2026-03-21 | >=3.9 | dev |
| coverage | 7.16.0 | 2026-08-28 | >=3.10 | dev |
| hypothesis | 6.168.0 | 2026-09-08 | >=3.10 | dev |
| ruff | 0.16.6 | 2026-09-03 | >=3.7 | dev |
| gunicorn | 26.2.0 | 2026-08-24 | >=3.10 | despliegue Linux (no instalado aún) |
| psycopg | 3.3.5 | 2026-08-31 | >=3.10 | despliegue PostgreSQL (no instalado aún) |
| Flask-Mail | 0.10.0 | 2024-05-23 | >=3.8 | Fase 7 |
| freezegun | 1.5.5 | 2025-08-09 | >=3.8 | cuando haga falta (tests con fechas) |
| Faker | 40.38.0 | 2026-09-01 | >=3.10 | cuando haga falta (datos sintéticos) |
| reportlab | 5.0.1 | 2026-08-20 | >=3.9,<4 | candidato Fase 12 (PDF) |
| weasyprint | 70.0 | 2026-09-08 | >=3.10 | candidato Fase 12; exige GTK en Windows |
| mypy | 2.3.1 | 2026-08-15 | >=3.10 | opcional, no adoptado |
| structlog | 26.1.0 | 2026-06-06 | >=3.10 | descartado (se usa `logging` + python-json-logger) |
| Flask-Talisman | 1.1.0 | 2023-08-03 | — | descartado (sin releases desde 2023; cabeceras a mano) |

Frontend a vendorizar en la Fase 1/11: alpinejs 3.17.2 (MIT), chart.js 4.5.1 (MIT).

## Verificación de la instalación (Fase 0)

- `pip install -r requirements-dev.txt`: 46 paquetes instalados en Windows sin errores.
- Import de las 20 dependencias directas comprobado una a una (script en `docs/fases/FASE_00_INFORME.md`).
- Marcadores de plataforma generados por `--universal`: `colorama` solo en `win32`, `tomli` solo en Python ≤ 3.11, `greenlet` por arquitectura, `pycparser` fuera de PyPy. El mismo fichero sirve para el VPS Linux.

## Trampas conocidas de este entorno

1. Nunca ejecutar `python` a secas fuera del venv activado: cae en el venv de `hermes-agent`. Dentro del proyecto, usar `.\.venv\Scripts\python.exe` o activar el venv.
2. En PowerShell usar `curl.exe`, no `curl`.
3. PowerShell 5.1 no admite `&&`; encadenar con `;` o `if ($?) { ... }`.
4. Sin `sqlite3` CLI: inspeccionar con `flask shell` o `python -c "import sqlite3; ..."`.
5. WeasyPrint en Windows exige el runtime GTK3 (Pango/Cairo) aparte: decidir alternativa en la Fase 12.
6. Para pruebas con el servidor en segundo plano, arrancar con `--no-reload`: con el reloader activo hay dos procesos y al matar el padre puede quedar el hijo escuchando en el puerto.
