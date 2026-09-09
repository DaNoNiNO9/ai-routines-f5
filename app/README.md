# app/ — capa web: factory, configuración, errores, logging y seguridad

**Qué hace:** construye la aplicación Flask con `create_app()` y contiene todo lo que depende del framework: blueprints, plantillas, estáticos, manejo de errores, logging, cabeceras de seguridad e i18n. El motor de cálculo (`engine/`), los modelos (`models/`) y los servicios (`services/`) viven en subpaquetes propios con su README.

**Cómo funciona:**

1. `create_app(config_name, overrides)` elige la clase de `config.py` (`development`, `testing` o `production`) por argumento o por la variable `FORJA_ENV`, aplica `overrides` (los usa la suite de tests) y, en producción, valida antes de nada que existan `SECRET_KEY` (32+ caracteres) y `DATABASE_URL`, y que `DEBUG` y `ENABLE_DEBUG_ROUTES` estén apagados. Si falla, la app no arranca y el error enumera todos los problemas.
2. Crea `instance/` y, si no hay `DATABASE_URL`, apunta SQLite a `instance/forja.db`.
3. `logging_config.configure_logging()` sustituye el handler por defecto de Flask por una consola legible y un fichero JSON rotativo (`logs/forja.log`, 5 MB x 5). Cada petición recibe un id (`X-Request-ID`: se respeta si llega en la cabecera, si no se genera) que aparece en cada línea de log y en la respuesta.
4. Inicializa las extensiones de `extensions.py`: SQLAlchemy, Migrate (Alembic con `render_as_batch=True` para que SQLite soporte `ALTER TABLE`), CSRF, Limiter y Babel. `LoginManager` se conecta en la Fase 7.
5. Registra blueprints: `main` siempre; `debug` (bajo `/_debug`) solo si `ENABLE_DEBUG_ROUTES`.
6. `errors.register_error_handlers()` captura `CSRFError` y cualquier `HTTPException`, incluido el 500 con el que Flask envuelve las excepciones no controladas (que Flask ya ha registrado con su traza). Responde con `errors/error.html`, o con JSON si la ruta empieza por `/api/` o el cliente acepta JSON pero no HTML.
7. `security.register_security_headers()` añade CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` y, solo con `ENABLE_HSTS`, HSTS.

**Ficheros:**
- `__init__.py` — `create_app()` y el context processor global (`app_name`, `app_version`, `current_locale`, `current_year`).
- `extensions.py` — instancias de las extensiones y la `Base` declarativa de SQLAlchemy 2.0.
- `logging_config.py` — handlers, filtro que inyecta el contexto de la petición, logger `app.request` (solo al fichero JSON).
- `errors.py` — textos por código (`ERROR_TEXTS`), handlers y decisión HTML/JSON.
- `security.py` — `CSP_DIRECTIVES` y el resto de cabeceras.
- `i18n.py` — `select_locale()`: `?lang=` → sesión → `Accept-Language` → `es`.
- `blueprints/main/routes.py` — `/` y `/health`.
- `blueprints/debug/routes.py` — `/_debug/boom` (500), `/_debug/echo` (CSRF), `/_debug/limited` (429), `/_debug/abort/<código>`.
- `templates/base.html` — esqueleto: cabecera, flashes, `<main>`, pie con el aviso permanente de "herramienta orientativa".
- `templates/errors/error.html` — única plantilla de error (código, título, mensaje, referencia).
- `static/css/app.css` — tokens de diseño (tema oscuro por defecto, claro disponible) y estilos base.

**Por dónde tocar:**
- Añadir un blueprint → crear `blueprints/<nombre>/routes.py` con `bp = Blueprint(...)` y registrarlo en `_register_blueprints()` de `__init__.py`.
- Cambiar los textos de las páginas de error → `errors.py`, diccionario `ERROR_TEXTS`.
- Relajar o endurecer la CSP → `security.py`, `CSP_DIRECTIVES`.
- Cambiar formato o destino de los logs → `logging_config.py` (`CONSOLE_FORMAT`, `JSON_FORMAT`, `_build_file_handler()`).
- Añadir un idioma → `config.py`, `LANGUAGES`, y generar su catálogo con pybabel (ver README raíz).
- Nueva variable de configuración → `config.py` en `BaseConfig` (valor por entorno en la subclase que lo necesite) y documentarla en `.env.example` y en el README raíz.

**Ojo con:**
- En `testing` las excepciones se propagan (comportamiento por defecto de Flask): para probar la página 500 hay que pasar `PROPAGATE_EXCEPTIONS=False` en `overrides`.
- Las clases de `config.py` leen `os.environ` al importarse: en tests, cambia valores con `overrides`, no con `monkeypatch.setenv` (salvo `FORJA_ENV`, que se lee en cada `create_app`).
- `limiter` es una instancia global compartida entre apps: los tests que activan el rate limiting llaman a `limiter.reset()`.
- El logger `app.request` no propaga: sus líneas solo van al fichero JSON, no a la consola (la consola ya tiene el access log de Werkzeug).
- La CSP permite `'unsafe-eval'` en scripts porque Alpine.js lo necesita. Si algún día se usa la build CSP de Alpine, quitarlo.
- `RotatingFileHandler` en Windows puede fallar al rotar si dos procesos tienen abierto el fichero (el reloader de `flask run` arranca dos). El error se imprime en consola y la app sigue; en producción hay un solo proceso por fichero de log o se usa un logger externo.

**Tests:** `tests/test_smoke.py` y `tests/integration/` (`test_factory.py`, `test_errors.py`, `test_security.py`, `test_i18n.py`, `test_logging.py`). Se lanzan con `pytest --cov` desde la raíz.
