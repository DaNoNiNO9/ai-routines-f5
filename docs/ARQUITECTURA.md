# Arquitectura

Estado: Fase 1. Este documento describe la arquitectura objetivo y marca lo que ya existe.

## Capas y regla de dependencia

```
 Navegador (Jinja2 + Alpine.js + Chart.js vendorizados)
        │ HTTP
 ┌──────▼──────────────────────────────────────────────┐
 │ app/ (Flask): create_app() · blueprints · forms ·   │  ← existe (Fase 1)
 │ templates · errors · logging · security · i18n      │
 └──────┬──────────────────────────────────────────────┘
        │
 ┌──────▼───────┐          ┌────────────────────────────┐
 │ services/    │ ───────► │ engine/ (funciones puras)  │  ← completo (Fases 4-6)
 │ orquestación │          │ nutrición · rutinas ·      │
 │ (auth hecho) │          │ ajuste · safety            │
 └──────┬───────┘          └────────────────────────────┘
        │
 ┌──────▼───────────────────────────┐
 │ models/ (SQLAlchemy 2.0) +       │  ← Fase 2
 │ migrations/ (Alembic)            │
 └──────────────────────────────────┘
```

Regla de dependencia, de arriba abajo y nunca al revés:

- `engine/` no importa Flask ni `models/`. Recibe dataclasses y devuelve dataclasses. Así se testea al 100 % sin base de datos.
- `models/` solo importa SQLAlchemy y `app.extensions.db`.
- `services/` es la única capa que habla con `engine/` y con `models/`: convierte filas en entradas del motor, guarda resultados y registra ajustes.
- Los blueprints solo hablan con `services/` y con formularios. No contienen cálculos.

## Ciclo de vida de una petición (Fase 1)

1. `before_request`: se asigna `g.request_id` (cabecera `X-Request-ID` entrante o 12 hex generados).
2. Flask-Babel elige el idioma con `app.i18n.select_locale()`.
3. La vista del blueprint responde; si lanza `HTTPException` o falla, entra `app.errors`.
4. `after_request` (en orden inverso de registro): cabeceras de seguridad, línea de acceso en el logger `app.request` (solo fichero JSON) y cabecera `X-Request-ID` en la respuesta.

## Configuración

`config.py` en la raíz define `BaseConfig` y tres subclases: `DevelopmentConfig`, `TestingConfig`, `ProductionConfig`. `create_app()` elige por argumento o por `ALZA_ENV`. Los secretos y valores de máquina llegan por variables de entorno (o `.env`, cargado por python-dotenv y nunca versionado). Producción valida su configuración al arrancar y se niega a levantar si falta algo.

## Logging

- Logger `app`: consola (formato legible) + `logs/alza.log` (JSON por línea, rotación 5 MB x 5). Nivel por `LOG_LEVEL`.
- Cada registro lleva `request_id`, `method`, `path` y `remote_addr` (o `-` fuera de una petición).
- Los módulos usan `logging.getLogger(__name__)`; al estar bajo el paquete `app`, propagan al logger `app`.
- Las excepciones no controladas las registra Flask con traza (`exc_info`) antes de renderizar la página 500.

## Errores

Un único handler para `HTTPException` y otro para `CSRFError`. La respuesta es HTML (`templates/errors/error.html`) o JSON cuando la ruta empieza por `/api/` o el cliente acepta JSON y no HTML. Se conservan las cabeceras `Allow`, `Retry-After` y `WWW-Authenticate` de la excepción original.

## Seguridad (Fase 1)

- CSP restringida al origen (`'unsafe-eval'` en scripts por Alpine.js; `'unsafe-inline'` en estilos por los atributos `style` que ponen Alpine y Chart.js).
- Cookies `HttpOnly` + `SameSite=Lax`; `Secure` en producción. HSTS solo en producción.
- CSRF global con Flask-WTF. Rate limiting con Flask-Limiter (límites concretos por ruta; almacenamiento `memory://` en desarrollo, Redis recomendado con varios workers).
- Las rutas `/_debug/*` no existen fuera de desarrollo y testing.

## Internacionalización

Flask-Babel con `es` por defecto. Los textos de plantillas se marcan con `{{ _('...') }}` y los de Python con `lazy_gettext`. Selección: `?lang=` (se guarda en sesión) → sesión → `Accept-Language` → `es`. Los catálogos (inglés) se generan en una fase aparte con `pybabel` y `babel.cfg`.

## Estructura de carpetas

```
ai-routines-f5/
├── config.py, wsgi.py, .flaskenv, .env.example, babel.cfg
├── app/
│   ├── __init__.py, extensions.py, errors.py, logging_config.py, security.py, i18n.py
│   ├── blueprints/{main,debug,auth,dashboard,onboarding,nutrition,training,tracking,workouts,review}/  (Fase 12: account, api)
│   ├── templates/{base.html, main/, errors/, debug/}
│   ├── static/css/app.css                       (Fase 11: vendor/, img/, fonts/)
│   ├── engine/                                  (Fase 4-6)
│   ├── models/                                  (Fase 2)
│   ├── services/{auth,onboarding,plans,dashboard,tracking,workouts,adjustments}.py
│   └── seeds/                                   (Fase 3)
├── migrations/                                  (Fase 2)
├── tests/{conftest.py, test_smoke.py, integration/, unit/}
├── docs/{ENTORNO, DECISIONES, ARQUITECTURA, fases/}
├── instance/ (SQLite, ignorado)  logs/ (ignorado)
└── requirements*.in / requirements*.txt
```

## Convenciones

- Código, identificadores, comentarios y docstrings en inglés; UI, docs, informes y commits en español (decisión D-04).
- Un blueprint = un paquete `blueprints/<nombre>/` con `routes.py` (y `forms.py` cuando haga falta). Plantillas en `templates/<nombre>/`.
- Fechas en UTC con zona horaria (ruff `DTZ` lo vigila); se muestran en `Europe/Madrid`.
- Nada de `print()`, nada de `except Exception` a ciegas, nada de `except: pass` (ruff `T20`, `BLE`, `S110`).
