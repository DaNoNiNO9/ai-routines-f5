# Fase 7 — Autenticación

Fecha: 2026-09-09. Estado: **cerrada**.

## Qué se ha hecho

- `app/services/auth.py`: registro (consentimiento registrado en el momento, carrera de correos duplicados capturada por la restricción única), autenticación con argon2id y verificación ficticia para correos desconocidos (tiempo de respuesta constante), rehash transparente si cambian los parámetros, política de contraseñas por códigos estables (`min_length:N`, `equals_email`, `too_common`), cargador de usuario para Flask-Login que excluye cuentas desactivadas o borradas, tokens de recuperación firmados y caducables (`itsdangerous`, 1 hora) ligados a un fragmento del hash actual.
- `app/email.py`: `send_email()` con backend `log` (desarrollo y tests; buzón en `app.extensions["outbox"]` y cuerpo completo en el log) y `smtp` (STARTTLS, tiempo de espera de 10 s); cualquier fallo se registra con traza y se eleva como `EmailDeliveryError`.
- Blueprint `auth`: `/registro`, `/entrar` (con `?next=` limitado a rutas relativas y casilla "recuérdame"), `/salir` (solo POST), `/recuperar`, `/restablecer/<token>` y la sonda `/_auth/whoami` (solo con rutas de depuración). Blueprint `dashboard`: `/panel` con `@login_required` (placeholder hasta la Fase 9).
- Formularios WTForms con validación de servidor, macros `field`/`checkbox` accesibles (etiqueta, ayuda, `aria-invalid`, errores en línea), plantillas `auth/*.html` y `dashboard/index.html`, navegación con estado de sesión en `base.html`, estilos de tarjeta y formulario en `app.css`.
- Configuración: `MAIL_*`, `PASSWORD_MIN_LENGTH`, `PASSWORD_RESET_MAX_AGE`; producción exige `MAIL_BACKEND=smtp`, `MAIL_SERVER` y `MAIL_FROM`. Límites por IP: login 5/min y 30/h, registro 10/h, recuperación 5/h, restablecer 10/h.
- Documentación: `app/README.md` (autenticación y correo), README raíz (variables `MAIL_*`, estado), `docs/ARQUITECTURA.md`, `docs/DECISIONES.md` T-54 a T-60.

## Qué se ha probado

| Prueba | Cómo | Resultado |
|---|---|---|
| Servicio | `tests/unit/services/test_auth_service.py` (hash/verify, política, registro y carrera, credenciales, rehash, cuentas inactivas, `load_user`, tokens válidos/caducados/reutilizados/manipulados) | 15 tests, 100 % de `services/auth.py` |
| Correo | `tests/unit/test_email.py` (buzón y cuerpo en el log, SMTP con doble falso, fallo envuelto, backend desconocido) | 4 tests, 100 % de `email.py` |
| Web | `tests/integration/test_auth.py` (registro → panel, errores de validación, contraseñas comunes o iguales al correo, login/logout, cuenta desactivada, redirección a `/entrar?next=`, `next` externo o protocolo-relativo rechazado, cookie `remember_token`, recuperación completa y enlace reutilizado, fallo de envío, límite 429, CSRF obligatorio, `whoami` oculto) | 13 tests, 100 % de `blueprints/auth/routes.py` |
| Producción | `test_production_requires_smtp_mail` | no arranca con `MAIL_BACKEND=log` |
| Suite completa | `pytest --cov` | 388 passed; cobertura de `app/` 98,7 % |
| Linter y formato | `ruff check .`, `ruff format --check .` | limpios |
| Servidor real | `flask run --no-reload` en segundo plano + `curl.exe` con tarro de cookies y token CSRF | registro 302 → `/panel` ("Hola, Smoke"); `/registro` con sesión → 302; `/salir` GET 405, POST 302; `/panel` anónimo → 302 `/entrar?next=%2Fpanel`; contraseña incorrecta → "Correo o contraseña incorrectos"; login correcto con "recuérdame" → 302 y `remember_token` en el tarro; `/recuperar` → 302 y enlace en `logs/forja.log`; `/restablecer/<token>` GET 200, POST 302; enlace reutilizado → `/recuperar`; contraseña antigua rechazada, nueva aceptada; POST sin CSRF → 400; sexta entrada errónea en un minuto → 429 |
| Log | `logs/forja.log` tras la sesión manual | sin errores nuevos (los dos `ERROR` son los del `/_debug/boom` de la Fase 1) |

## Errores aparecidos y cómo se corrigieron

1. **La suite de producción fallaba** al añadir la validación del correo: los tests que construyen una app de producción ahora pasan `PRODUCTION_MAIL` (SMTP configurado).
2. **`session_protection="strong"`** cerraba la sesión al cambiar la IP y añadía una cookie de borrado de `remember_token` en cada respuesta anónima (rompió el test de cookies): modo `basic` (T-59) y los tests leen todas las cabeceras `Set-Cookie`.
3. **`PasswordHasher.check_needs_rehash` no se puede parchear** (atributo de solo lectura): el test sustituye el objeto hasher por una subclase que siempre pide rehash.
4. **Test de caducidad parcheaba la clase equivocada**: se parchea el firmante (`TimestampSigner`) con `functools.partial` para retroceder el reloj.
5. **Test de la carrera de registro** comparaba un `Result` con un entero y dejaba la tabla bloqueada (SQLite) hasta el teardown: consulta escalar con `scalar_one()`.
6. **El backend `log` no escribía el cuerpo del correo**: en la verificación manual el enlace de recuperación no aparecía en ningún sitio. Ahora se registra completo (T-60) y un test lo fija con `caplog`.
7. Lint: excepciones renombradas con sufijo `Error` (N818) y lambdas en bucle sustituidas por búsqueda y llamada (B023).

## Limitaciones conocidas

- Sin verificación de correo al registrarse: cualquiera puede registrar una dirección que no controla (no recibe nada más que el correo de recuperación). Queda para la Fase 12 (cuenta) si se considera necesario.
- Los límites de peticiones viven en memoria (`memory://`): con varios procesos en producción cada uno cuenta por su cuenta; para un VPS con un solo worker es suficiente, y `RATELIMIT_STORAGE_URI` permite pasar a Redis.
- La sonda `/_auth/whoami` existe solo con `ENABLE_DEBUG_ROUTES`.

## Pendiente

- Fase 8: cuestionario multipaso que rellena `profiles` y genera plan y rutina con los servicios.
- Fase 12: página de cuenta (cambio de contraseña y correo, exportación, borrado RGPD).

## Criterio de cierre

Registro, inicio de sesión, cierre de sesión y recuperación funcionan en el servidor real; las rutas protegidas redirigen; CSRF y rate limiting verificados con `curl`. Cumplido.
