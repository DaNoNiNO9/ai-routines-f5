# app/ — capa web: factory, configuración, errores, logging y seguridad

**Qué hace:** construye la aplicación Flask con `create_app()` y contiene todo lo que depende del framework: blueprints, plantillas, estáticos, manejo de errores, logging, cabeceras de seguridad e i18n. El motor de cálculo (`engine/`), los modelos (`models/`) y los servicios (`services/`) viven en subpaquetes propios con su README.

**Cómo funciona:**

1. `create_app(config_name, overrides)` elige la clase de `config.py` (`development`, `testing` o `production`) por argumento o por la variable `FORJA_ENV`, aplica `overrides` (los usa la suite de tests) y, en producción, valida antes de nada que existan `SECRET_KEY` (32+ caracteres) y `DATABASE_URL`, y que `DEBUG` y `ENABLE_DEBUG_ROUTES` estén apagados. Si falla, la app no arranca y el error enumera todos los problemas.
2. Crea `instance/` y, si no hay `DATABASE_URL`, apunta SQLite a `instance/forja.db`.
3. `logging_config.configure_logging()` sustituye el handler por defecto de Flask por una consola legible y un fichero JSON rotativo (`logs/forja.log`, 5 MB x 5). Cada petición recibe un id (`X-Request-ID`: se respeta si llega en la cabecera, si no se genera) que aparece en cada línea de log y en la respuesta.
4. Inicializa las extensiones de `extensions.py`: SQLAlchemy, Migrate (Alembic con `render_as_batch=True` para que SQLite soporte `ALTER TABLE`), CSRF, Limiter y Babel. `LoginManager` se conecta en la Fase 7.
5. Registra blueprints: `main`, `auth`, `dashboard`, `onboarding` (`/cuestionario`), `nutrition` (`/nutricion`) y `training` (`/entrenamiento`) siempre; `debug` (bajo `/_debug`) solo si `ENABLE_DEBUG_ROUTES`.
6. `errors.register_error_handlers()` captura `CSRFError` y cualquier `HTTPException`, incluido el 500 con el que Flask envuelve las excepciones no controladas (que Flask ya ha registrado con su traza). Responde con `errors/error.html`, o con JSON si la ruta empieza por `/api/` o el cliente acepta JSON pero no HTML.
7. `security.register_security_headers()` añade CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` y, solo con `ENABLE_HSTS`, HSTS.
8. Autenticación (Fase 7): `services/auth.py` hace el trabajo (argon2id, verificación ficticia para correos desconocidos, tokens de recuperación firmados y caducables ligados al hash actual, cargador de usuario para Flask-Login) y `blueprints/auth/routes.py` solo traduce errores a mensajes y redirecciones. Rutas: `/registro`, `/entrar`, `/salir` (POST), `/recuperar`, `/restablecer/<token>`; `/panel` (blueprint `dashboard`) exige sesión. Límites por IP en los POST (login 5/min y 30/h, registro 10/h, recuperación 5/h).
9. Cuestionario (Fase 8): `blueprints/onboarding/` muestra un formulario por bloque (`/cuestionario/paso/<n>`, siete pasos), guarda cada paso en un borrador (`services/onboarding.py`), no deja saltar pasos sin completar los anteriores, permite volver atrás sin perder nada, resume todo en `/cuestionario/revisar` y, al generar, crea la versión nueva del perfil con su plan y su rutina; `/cuestionario/resultado` los muestra o explica por qué no hay plan. Los textos de los enums salen de `labels.py`.
10. Panel y plan (Fase 9): `blueprints/dashboard` (hoy, próxima sesión, peso con media de 7 días, próxima revisión), `blueprints/nutrition` (objetivo, macros, comidas, ciclado, cómo se calculó, avisos, protocolo de ajuste, historial de versiones) y `blueprints/training` (rutina, volumen, cardio; un día por página con ilustraciones, prescripción, instrucciones y alternativas viables). Solo leen: `services/dashboard.py` hace las consultas. Las gráficas son Chart.js vendorizado, alimentado por bloques JSON (`components/charts.html` + `static/js/forja.js`); Alpine.js solo alterna la ilustración inicial/final. Todo funciona sin JavaScript salvo las gráficas.
11. Correo: `email.py` con backend `log` (desarrollo y tests; mensajes en `app.extensions["outbox"]`) o `smtp` (producción, `smtplib` + STARTTLS). Los fallos se registran con traza y se convierten en `EmailDeliveryError`.

**Ficheros:**
- `__init__.py` — `create_app()` y el context processor global (`app_name`, `app_version`, `current_locale`, `current_year`).
- `extensions.py` — instancias de las extensiones y la `Base` declarativa de SQLAlchemy 2.0.
- `logging_config.py` — handlers, filtro que inyecta el contexto de la petición, logger `app.request` (solo al fichero JSON).
- `errors.py` — textos por código (`ERROR_TEXTS`), handlers y decisión HTML/JSON.
- `security.py` — `CSP_DIRECTIVES` y el resto de cabeceras.
- `i18n.py` — `select_locale()`: `?lang=` → sesión → `Accept-Language` → `es`.
- `blueprints/main/routes.py` — `/` y `/health`.
- `blueprints/debug/routes.py` — `/_debug/boom` (500), `/_debug/echo` (CSRF), `/_debug/limited` (429), `/_debug/abort/<código>`.
- `blueprints/auth/forms.py` y `routes.py` — formularios (WTForms) y vistas de cuentas; `blueprints/dashboard/routes.py` — panel (CTA al cuestionario o resumen del plan).
- `blueprints/onboarding/forms.py` — un formulario por paso (`STEP_FORMS`), con la validación cruzada (cadera en mujeres, intensidad si hay otro deporte, máximo dos músculos, fecha objetivo futura); `routes.py` — pasos, revisión (`_summary()`), resultado.
- `labels.py` — etiquetas traducibles de todos los enums (`choices()` para WTForms, `label()` para plantillas).
- `blueprints/nutrition/routes.py`, `blueprints/training/routes.py`, `blueprints/dashboard/routes.py` — páginas del plan (solo lectura).
- `static/vendor/` — Alpine.js 3.17.2 y Chart.js 4.5.1 con sus licencias (ver `docs/CREDITOS.md`); `static/js/forja.js` — construcción de gráficas desde `<canvas data-chart>`.
- `templates/components/charts.html` — macro `chart(id, kind, data, label)`; `templates/nutrition/plan.html`, `templates/training/{routine,day}.html`, `templates/dashboard/index.html`.
- `services/auth.py` — registro, autenticación, política de contraseñas, tokens de recuperación, `load_user`.
- `email.py` — envío de correo con backend `log` o `smtp`.
- `templates/components/forms.html` — macros `field`, `checkbox`, `radios` (con ayuda por opción) y `checkboxes` para formularios accesibles con errores en línea.
- `templates/onboarding/_wizard.html` — barra de progreso y navegación del cuestionario; `step_*.html`, `review.html`, `result.html`.
- `templates/base.html` — esqueleto: cabecera, flashes, `<main>`, pie con el aviso permanente de "herramienta orientativa".
- `templates/errors/error.html` — única plantilla de error (código, título, mensaje, referencia).
- `static/css/app.css` — tokens de diseño (tema oscuro por defecto, claro disponible) y estilos base.

**Por dónde tocar:**
- Añadir un blueprint → crear `blueprints/<nombre>/routes.py` con `bp = Blueprint(...)` y registrarlo en `_register_blueprints()` de `__init__.py`.
- Cambiar los textos de las páginas de error → `errors.py`, diccionario `ERROR_TEXTS`.
- Relajar o endurecer la CSP → `security.py`, `CSP_DIRECTIVES`.
- Cambiar formato o destino de los logs → `logging_config.py` (`CONSOLE_FORMAT`, `JSON_FORMAT`, `_build_file_handler()`).
- Añadir un idioma → `config.py`, `LANGUAGES`, y generar su catálogo con pybabel (ver README raíz).
- Añadir o cambiar una pregunta del cuestionario → ver `services/README.md` ("Por dónde tocar").
- Cambiar la política de contraseñas → `services/auth.py` (`password_problems`, `COMMON_PASSWORDS`) y `PASSWORD_MIN_LENGTH` en `config.py`.
- Cambiar los límites de peticiones de las cuentas → decoradores `limiter.limit` en `blueprints/auth/routes.py`.
- Caducidad del enlace de recuperación → `PASSWORD_RESET_MAX_AGE` en `config.py`.
- Nueva variable de configuración → `config.py` en `BaseConfig` (valor por entorno en la subclase que lo necesite) y documentarla en `.env.example` y en el README raíz.

**Ojo con:**
- En `testing` las excepciones se propagan (comportamiento por defecto de Flask): para probar la página 500 hay que pasar `PROPAGATE_EXCEPTIONS=False` en `overrides`.
- Las clases de `config.py` leen `os.environ` al importarse: en tests, cambia valores con `overrides`, no con `monkeypatch.setenv` (salvo `FORJA_ENV`, que se lee en cada `create_app`).
- `limiter` es una instancia global compartida entre apps: los tests que activan el rate limiting llaman a `limiter.reset()`.
- El logger `app.request` no propaga: sus líneas solo van al fichero JSON, no a la consola (la consola ya tiene el access log de Werkzeug).
- La CSP permite `'unsafe-eval'` en scripts porque Alpine.js lo necesita. Si algún día se usa la build CSP de Alpine, quitarlo. No hay scripts inline: los datos de las gráficas van en `<script type="application/json">` (no se ejecutan) y `forja.js` los lee.
- Chart.js (208 KB) se carga solo en las páginas con gráficas, mediante el bloque `scripts` de la plantilla; Alpine (56 KB) siempre.
- `RotatingFileHandler` en Windows puede fallar al rotar si dos procesos tienen abierto el fichero (el reloader de `flask run` arranca dos). El error se imprime en consola y la app sigue; en producción hay un solo proceso por fichero de log o se usa un logger externo.

**Tests:** `tests/test_smoke.py`, `tests/integration/` (`test_factory.py`, `test_errors.py`, `test_security.py`, `test_i18n.py`, `test_logging.py`, `test_auth.py`, `test_onboarding.py`, `test_plan_pages.py`) y `tests/unit/test_labels_and_forms.py`. Se lanzan con `pytest --cov` desde la raíz.
