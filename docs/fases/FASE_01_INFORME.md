# Fase 1 — Arquitectura

Fecha: 2026-09-09. Estado: **cerrada**.

## Qué se ha hecho

- `config.py` con `BaseConfig` y `DevelopmentConfig` / `TestingConfig` / `ProductionConfig`, selección por argumento o `FORJA_ENV`, carga de `.env` con python-dotenv y validación de producción que impide arrancar sin `SECRET_KEY` (32+), sin `DATABASE_URL` o con `DEBUG` / `ENABLE_DEBUG_ROUTES` activos. `.env.example` documentado.
- Factory `create_app(config_name, overrides)` en `app/__init__.py`: crea `instance/`, resuelve la URI de SQLite por defecto, configura logging, inicializa SQLAlchemy, Migrate (`render_as_batch` para SQLite), CSRF, Limiter y Babel, registra blueprints, handlers de error y cabeceras de seguridad, y un context processor global.
- Logging estructurado (`app/logging_config.py`): consola legible + fichero JSON rotativo `logs/forja.log`; id de petición (`X-Request-ID`) en cada registro y en cada respuesta; logger `app.request` con línea de acceso solo al fichero.
- Manejo global de errores (`app/errors.py`): una plantilla `errors/error.html` para 400/403/404/405/429/500 con referencia de petición; JSON automático para `/api/` o clientes que solo aceptan JSON; handler de `CSRFError`; se conservan `Allow`, `Retry-After` y `WWW-Authenticate`.
- Cabeceras de seguridad (`app/security.py`): CSP, nosniff, `X-Frame-Options: DENY`, Referrer-Policy, Permissions-Policy, HSTS solo en producción. Cookies `HttpOnly` + `SameSite=Lax` (+ `Secure` en producción).
- i18n (`app/i18n.py` + Flask-Babel + `babel.cfg`): `?lang=` → sesión → `Accept-Language` → `es`. Plantillas con `_()` desde el principio.
- Blueprints `main` (`/`, `/health`) y `debug` (`/_debug/boom`, `/echo`, `/limited`, `/abort/<código>`), este último solo en desarrollo y testing.
- Plantilla base con cabecera, flashes, pie con el aviso permanente de "herramienta orientativa", y `app.css` con tokens de diseño (oscuro por defecto).
- `wsgi.py` para waitress/gunicorn. `pythonpath = ["."]` en pytest para que `pytest` funcione sin `python -m`.
- Documentación: `app/README.md`, `docs/ARQUITECTURA.md`, README raíz actualizado (variables, comandos, traducciones), `docs/DECISIONES.md` (T-12 a T-16).

## Qué se ha probado

| Prueba | Cómo | Resultado |
|---|---|---|
| Suite | `pytest --cov` | 40 passed; cobertura de `app/` 98,7 % (ramas incluidas) |
| Linter y formato | `ruff check .`, `ruff format --check .` | limpios |
| Selección de entorno | tests de `create_app` con `FORJA_ENV`, nombre desconocido, producción incompleta y producción válida | OK; producción con `DEBUG` o rutas debug activas no arranca |
| Servidor real sin depurador | `FLASK_DEBUG=0 flask run --no-reload` en segundo plano + `curl.exe` | `/` 200 con CSP, `X-Frame-Options` y `X-Request-ID`; `/health` JSON; `/no-existe` página 404 con referencia; `/_debug/boom` página 500 con referencia `manual-boom-1`; `/api/x` JSON 404; `POST /_debug/echo` sin token 400; `/_debug/limited` 200, 200, 429; `/?lang=en` cambia `lang` |
| Error 500 logueado | inspección de `logs/forja.log` | 3 líneas JSON con `request_id=manual-boom-1`: traza completa (`exc_info`), línea del handler y línea de acceso `-> 500` |
| Parada del servidor | `Stop-Process` + `Get-NetTCPConnection` | puerto 5000 liberado |
| CSRF con token válido | test que extrae el token del formulario y lo reenvía | 200 y eco del mensaje |
| Cookies | test de `Set-Cookie` con CSRF activo | `HttpOnly` y `SameSite=Lax` presentes |

## Errores aparecidos y cómo se corrigieron

1. **Scripts de shell largos truncados**: dos veces, al escribir varios ficheros en un solo comando (más de ~8 KB), el shell recibió el comando cortado y falló con "unexpected EOF". Nada se escribió (fallo de parseo). Corrección: ficheros grandes con la herramienta de escritura directa; comandos de shell cortos.
2. **Validación de producción no detectaba `DATABASE_URL` vacío**: la factory rellenaba la URI de SQLite antes de validar. Corrección: validar antes de preparar `instance/`; test `test_production_refuses_missing_secret_and_database` en verde.
3. **isort trataba `tests` y `config` como terceros**: corrección en `pyproject.toml` (`known-first-party`).
4. **Tres avisos de ruff**: docstring en `RequestContextFilter.filter`, falso positivo `ERA001` en un comentario con paréntesis (reformulado) y patrón regex sin `r""` en un test. Corregidos.
5. **Textos de error sin tildes** (por precaución con `RUF001`): repuestas las tildes; ruff no se queja de vocales acentuadas.

## Pendiente

- `LoginManager` se inicializa en la Fase 7 (aún no hay usuarios).
- Catálogos de traducción (inglés): fase aparte al final (D-05).
- Fase 2: esquema completo, modelos SQLAlchemy 2.0, `flask db init`, primera migración, seeds mínimos y tests de modelos y constraints.

## Criterio de cierre

Endpoints de prueba respondiendo; un 500 provocado a propósito devuelve la página de error de la app y queda registrado con traza e id de petición en `logs/forja.log`. Cumplido.
