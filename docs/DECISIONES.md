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

## 2026-09-09 — Fase 1 (arquitectura)

| ID | Tema | Decisión | Motivo |
|---|---|---|---|
| T-12 | CSP | `script-src 'self' 'unsafe-eval'` y `style-src 'self' 'unsafe-inline'`; todo lo demás restringido al origen | Alpine.js estándar compila expresiones con `new Function`; Alpine y Chart.js escriben atributos `style`. Revisable si se adopta la build CSP de Alpine |
| T-13 | Errores | Un handler para `HTTPException` (incluye el 500 que Flask genera al envolver excepciones) y otro para `CSRFError`; sin handler genérico de `Exception` | Así en desarrollo el depurador de Werkzeug sigue funcionando y en tests las excepciones se propagan, mientras producción muestra la página 500 y Flask registra la traza |
| T-14 | Rutas de diagnóstico | Blueprint `debug` bajo `/_debug` solo con `ENABLE_DEBUG_ROUTES`; producción no arranca si está activo | Poder provocar 500, CSRF y 429 a mano y en tests sin dejar puertas abiertas |
| T-15 | Id de petición | Cabecera `X-Request-ID` (se respeta la entrante, truncada a 64, o se generan 12 hex); aparece en logs, respuestas y páginas de error | Correlacionar lo que ve el usuario con la línea del log |
| T-16 | Textos | Los mensajes de error viven en Python con `lazy_gettext` y tildes correctas; el resto de textos en plantillas con `_()` | Preparado para pybabel desde el principio (D-05) |

## 2026-09-09 — Fase 2 (modelo de datos)

| ID | Tema | Decisión | Motivo |
|---|---|---|---|
| T-17 | Estilo ORM | SQLAlchemy 2.0 con `Mapped[...]` y `mapped_column`, `Base` declarativa con convención de nombres para todos los constraints | Alembic en modo batch (SQLite) exige nombres deterministas; PostgreSQL agradece nombres únicos |
| T-18 | Enums | VARCHAR(32) + CHECK con los valores de `app/engine/enums.py` (`StrEnum`), sin tipos nativos de PostgreSQL | Portable entre SQLite y PostgreSQL; el vocabulario vive en un módulo sin Flask que comparten motor, modelos y formularios |
| T-19 | Fechas | `UTCDateTime`: solo fechas-hora *aware*, normalizadas a UTC; `date` para registros diarios | SQLite pierde el offset; así ningún dato ambiguo llega a la base |
| T-20 | Decimales | `Float` en pesos, medidas y macros | SQLite no tiene decimal nativo (SQLAlchemy avisa en cada consulta); la precisión de float sobra para kg y gramos |
| T-21 | JSON | Columnas JSON (JSONB en PostgreSQL) para listas y estructuras que no se filtran por SQL: prioridades, aversiones, contraindicaciones, instantáneas del motor | Evita tablas satélite sin valor de consulta; la validación la hace el código |
| T-22 | Borrado | Físico en cascada desde `users` (GDPR); lógico en `plans`, `routines`, `workout_sessions` y `users`; `RESTRICT` en ejercicios referenciados | Derecho al olvido completo y posibilidad de deshacer en el día a día |
| T-23 | Registro de ingesta | Tabla `intake_logs` (kcal, macros, adherencia 0-100) y `activity_logs` (pasos, cardio), una fila por día | Alimentan el TDEE observado del motor de ajuste (D-07) |
| T-24 | Migraciones | Flask-Migrate con `render_as_batch=True` y `render_item` propio: los ficheros de migración usan solo tipos estándar; test que compara migración y modelos | Migraciones independientes del código de la app y sin deriva silenciosa |

## 2026-09-09 — Fase 3 (catálogo de ejercicios)

| ID | Tema | Decisión | Motivo |
|---|---|---|---|
| T-25 | Vídeos | `video_url` apunta a una búsqueda de YouTube con el nombre del ejercicio; la columna admite enlaces concretos cuando se curen | No hay forma de verificar 190 ids de vídeo y sus licencias; una búsqueda es siempre válida y no embebe contenido de terceros |
| T-26 | Imágenes | Dos ilustraciones por ejercicio (inicio y fin) del dataset, recodificadas a 560 px y calidad JPEG 75, en `app/static/img/exercises/` | Assets locales (§6) con un tamaño total contenido (< 15 MB); dominio público |
| T-27 | Contraindicaciones | Lista JSON `{area, min_severity}` por ejercicio: se excluye cuando el usuario declara esa zona con severidad igual o mayor. Curadas a mano por patrón y ejercicio | Regla simple de aplicar en el generador y de explicar al usuario; la fuente no trae este dato |
| T-28 | Alternativas | Calculadas al generar el catálogo: mismo patrón y músculo primario, hasta 4, priorizando otro material y misma mecánica | Cobertura del 90 %+ sin curar 190 listas a mano; revisables en el JSON |
| T-29 | Selección | 190 ejercicios de los 876 del dataset, con nombre en español propio; instrucciones en inglés del dataset (`instructions_es` vacío) | Limitación conocida: traducir 190 instrucciones se deja para una fase posterior o para hacer a mano |
| T-30 | Presets de material | `app/engine/equipment_presets.py` define el material asumido por lugar (gimnasio completo, básico, casa con material, casa sin material) y lo comparten cuestionario, generador y tests de cobertura | Un solo sitio para la regla; el test exige todos los patrones en cada preset (salvo tracción vertical sin material) |

## 2026-09-09 — Fase 4 (motor nutricional)

| ID | Tema | Decisión | Motivo |
|---|---|---|---|
| T-31 | Selección de BMR | Katch-McArdle siempre que exista un % graso (declarado por cualquier método o estimado por Navy); Mifflin-St Jeor en caso contrario; Harris-Benedict revisada solo para el rango | Es lo que pide §3.3; la confianza se muestra aparte según el método |
| T-32 | NEAT | Pasos × 0,75 m × 0,5 kcal/kg/km (ACSM) + extra ocupacional fijo (0/100/250/500 kcal) y pasos estimados por trabajo (4000/7000/9000/12000, Tudor-Locke) | Modelo por componentes con constantes citadas; el motor de ajuste corregirá el TDEE con datos reales |
| T-33 | TEF | 10 % de la ingesta resuelto por punto fijo sobre el objetivo; el déficit porcentual se define sobre el gasto real a esa ingesta | Literal de §3.4 |
| T-34 | Déficit y superávit | Déficit 10-25 % escalado linealmente entre 12-30 % de grasa (hombres) y 20-38 % (mujeres), ±5 puntos por agresividad; superávit 5 % principiantes, 7,5 % intermedios, 10 % avanzados, ±2,5 puntos; recomposición 5 % de déficit solo si principiante/retomando o grasa alta | §3.5 con la lectura literal de "principiantes con superávits pequeños" |
| T-35 | Suelo de carbohidratos | 1,0 / 1,5 / 2,0 g/kg según días de entreno (≤2, 3-4, ≥5), mínimo 100 g; primero baja la grasa al mínimo (0,6 g/kg y 20 %), después sube calorías reduciendo el déficit | §3.6: nunca carbohidratos a cero |
| T-36 | Modificador de estilo de vida | −1,5 % (sueño < 7 h) o −3 % (< 6 h) y −2 % (estrés ≥ 4) sobre NEAT + EAT, explicado en una nota | Pequeño y conservador, como pide §3.4 |
| T-37 | Notas | El motor emite `Note(code, level, params)`; el texto en español vive en `messages.py` y la UI podrá traducirlo | Motor sin texto de interfaz; explicaciones reproducibles y testeables |
| T-38 | Puerta de seguridad | `evaluate_eligibility` al principio (bloqueos por persona) y `verify_plan` al final (límites sobre los números); una violación final lanza `SafetyError` en vez de devolver el plan | Garantía verificada con Hypothesis; `targets.py` reutiliza las mismas constantes para producir planes válidos a la primera |
| T-39 | Perfil | Nuevas columnas `training_time` y `wants_carb_cycling` (migración `021183cac637` con `server_default` para bases con filas) | El reparto por comidas necesita saber cuándo se entrena |

## 2026-09-09 — Fase 5 (motor de rutinas)

| ID | Tema | Decisión | Motivo |
|---|---|---|---|
| T-40 | Splits | 2 días full body; 3 días full body (avanzados PPL); 4 upper/lower; 5 upper/lower + PPL (Arnold con más de 5 años); 6 PPL ×2; 7 se recorta a 6; 1 día full body A | Literal de §3.7 con una lectura concreta del "según experiencia" |
| T-41 | Plantillas | Cada día es una lista de slots (patrón, rol main/secondary/accessory/isolation, músculo objetivo, unilateral opcional) definidas a mano en `splits.py` | Garantiza compuestos al principio, cobertura de patrones y variedad A/B sin aleatoriedad |
| T-42 | Selección | Determinista: filtros duros (material, contraindicaciones por severidad, aversiones, nivel técnico con una relajación anotada) y puntuación (preferidos, staples del entrenador, músculo objetivo, mecánica, material cargable sobre bandas y peso corporal, unilateral, penalización por repetir en la semana); desempate por CRC32 del slug | Reproducible en tests y explicable al usuario |
| T-43 | Volumen | Series efectivas semanales (primario 1, secundario 0,5) contra 8-12 / 12-18 / 16-22 por experiencia; prioridades +27,5 % con compensación del resto; objetivos escalados al tiempo disponible (2,5 min por serie de media) | §3.7; sin el escalado casi cualquier sesión de 60 min quedaba "baja" en todos los grupos |
| T-44 | Equilibrio empuje/tracción | Tracción ≥ empuje (≥ 1,3 con historial de hombro): primero más series de tracción, luego un accesorio de tracción, y si el material no da más, menos series de empuje | Sin material de tracción (casa sin nada) el ratio solo puede equilibrarse quitando empuje |
| T-45 | Tiempo | Estimación por serie (reps máximas × 3 s + descanso, unilateral ×1,8) más 8 min de calentamiento y 1 min de transición; recorte en orden aislamiento → accesorio → secundario → principal, mínimo 3 ejercicios por día; si aun así no cabe, aviso | Sesiones honestas: nunca se promete una rutina que no entra en el tiempo |
| T-46 | Prescripción | Reps 6-10 principales (3-6 con objetivo rendimiento y experiencia), 10-15 accesorios, 12-20 aislamiento, 10-15 core; RIR 3→1 (aislamiento hasta 0); descansos 180/150/90/60 s (90/90/60/45 con peso corporal); tempo 2-0-1-0 / 3-1-1-0; incremento por material y sexo; mesociclo 6/5/4 semanas y descarga cada 8/6/4 según experiencia, acortados con fatiga alta | §3.7 y bibliografía citada en `prescription.py` |
| T-47 | Cardio | Pasos objetivo (+2000 en pérdida de grasa, 8-12k) y LISS/HIIT solo para el déficit que la dieta no cubre; máximo 3 LISS + 1 HIIT (HIIT solo con experiencia y sin lesión inferior); si sobra déficit, se alarga el plazo; nota fija de "nunca como castigo" | §3.7 |

## 2026-09-09 — Fase 6 (motor de ajuste)

| ID | Tema | Decisión | Motivo |
|---|---|---|---|
| T-48 | Suavizado | Media móvil de 7 días (ventana de calendario, mínimo 3 pesajes) y tendencia por mínimos cuadrados sobre la serie suavizada, en kg/semana; se exigen ≥ 8 pesajes en ≥ 10 días para opinar | §3.8: nunca comparar días sueltos; la regresión tolera huecos |
| T-49 | TDEE observado | `ingesta media + (−Δpeso × 7700) / días`, solo con ≥ 70 % de días de ingesta registrados; acotado a ±25 % del teórico; mezcla lineal con el teórico según días de datos (confianza total a los 28 días, mitad si la tendencia es de baja confianza) | Es la idea de MacroFactor: sustituir el cálculo por la observación a medida que hay datos, sin dejarse arrastrar por registros incompletos |
| T-50 | Cadencia | Revisión cada 14 días desde el inicio del plan o el último ajuste; antes de la fecha, "esperar"; sin datos suficientes, nueva revisión en 7 días | §3.8 |
| T-51 | Reglas de déficit | Pérdida < 50 % de la esperada → primero adherencia (< 85 % no se recorta), después recorte ≤ 5 % (nunca bajo el suelo ni por encima del tope del 1 %); si ya está en el suelo, +1000 pasos (hasta 12k). Pérdida > 1 %/semana → subir calorías hasta el tope (≤ 10 %). Estancamiento (< 0,1 kg/semana): refeed con ≥ 4 semanas y un estancamiento previo, descanso de dieta de 2 semanas a mantenimiento con ≥ 8 semanas | §3.8 literal, con los mismos límites de `safety.py` |
| T-52 | Superávit y mantenimiento | Superávit: ganancia < 50 % de la esperada → +5 % (con adherencia); > 0,5 % del peso/semana → −5 %. Mantenimiento: deriva > 0,25 kg/semana → ±3 % | Simetría con el déficit y pasos pequeños |
| T-53 | Salida | `AdjustmentDecision` con acción, motivo (`AdjustmentReason`), calorías y pasos nuevos, tendencia, TDEE estimado, adherencia, próxima revisión y notas; los servicios (Fase 8+) la convierten en un plan nuevo y una fila de `plan_adjustments` | Motor puro y auditable |

## 2026-09-09 — Fase 7 (autenticación)

| ID | Tema | Decisión | Motivo |
|---|---|---|---|
| T-54 | Contraseñas | argon2id con los parámetros por defecto de `argon2-cffi`, rehash transparente al iniciar sesión si cambian los parámetros; política mínima de 10 caracteres, distinta del correo y fuera de una lista corta de contraseñas comunes; verificación ficticia cuando el correo no existe para no revelar cuentas por tiempo de respuesta | Recomendación OWASP; sin reglas absurdas de mayúsculas y símbolos |
| T-55 | Recuperación | Token firmado y caducable (`itsdangerous`, 1 hora) que incluye un fragmento del hash actual: cambiar la contraseña invalida todos los tokens anteriores; el formulario de recuperación responde igual exista o no el correo | Sin tabla de tokens ni estado adicional, sin enumeración de usuarios |
| T-56 | Email | Módulo propio `app/email.py` con dos backends: `log` (desarrollo y tests; los mensajes quedan en `app.extensions["outbox"]`) y `smtp` (`smtplib` + STARTTLS); producción no arranca sin `MAIL_BACKEND=smtp`, `MAIL_SERVER` y `MAIL_FROM` | Flask-Mail no aporta nada que justifique otra dependencia; la recuperación de contraseña sin correo sería una función rota |
| T-57 | Límites | Login 5/min y 30/h; registro 10/h; recuperación 5/h; restablecer 10/h; todos por IP y solo en POST | §7: rate limiting en login; el resto evita abuso del correo |
| T-58 | Rutas | URLs en español (`/registro`, `/entrar`, `/salir`, `/recuperar`, `/restablecer/<token>`, `/panel`), endpoints en inglés (`auth.register`...); cierre de sesión solo por POST con CSRF | La URL es interfaz (D-04); un enlace GET no puede cerrar sesiones ajenas |
| T-59 | Sesión | Flask-Login con `session_protection="basic"` (el modo `strong` cierra la sesión al cambiar de IP, algo constante en móvil, y añade una cookie de borrado en cada página anónima), cookie `remember_token` solo si el usuario lo pide (14 días), redirección `next` limitada a rutas relativas del propio sitio | Sin open redirect ni sesiones eternas por defecto; pensado para usarse desde el móvil en el gimnasio |
| T-60 | Email en desarrollo | El backend `log` escribe el cuerpo completo del correo en el log (no solo destinatario y asunto), de modo que el enlace de recuperación se puede seguir en desarrollo | En la verificación manual el enlace no aparecía en ningún sitio; producción no arranca con este backend, así que no se filtran enlaces reales |

## 2026-09-09 — Fase 8 (cuestionario)

| ID | Tema | Decisión | Motivo |
|---|---|---|---|
| T-61 | Borradores | Tabla `questionnaire_drafts` (una fila por usuario, JSON plano con las respuestas y el último paso completado) en vez de guardar el progreso en la cookie de sesión | La cookie firmada tiene un límite de 4 KB y se pierde al cambiar de dispositivo; el borrador en base de datos permite empezar en el ordenador y seguir en el móvil |
| T-62 | Pasos | Siete pasos (sobre ti, actividad, entrenamiento, material y lesiones, objetivo, nutrición, salud) más una revisión; el material va en un paso propio, después del lugar de entrenamiento, para pre-marcar el preset sin JavaScript | Sin build ni JS obligatorio (D-05): el servidor pre-marca el preset del lugar elegido y lo reinicia si el lugar cambia |
| T-63 | Validación | Cada paso es un `FlaskForm` con los mismos rangos que el motor y los CHECK; comprobaciones cruzadas a nivel de formulario (cadera en mujeres con cintura y cuello, intensidad si hay otro deporte, máximo dos músculos, fecha objetivo futura); menores de 18 rechazados en el paso 1 aunque el motor lo repita | Decir "no" en la primera pantalla, no tras siete pasos; el motor sigue siendo la última defensa |
| T-64 | Perfil | Completar el cuestionario crea siempre una versión nueva de `profiles` (la anterior queda `superseded_at`), sustituye el material del usuario, registra el peso de hoy en `weight_logs` y borra el borrador, todo en una transacción | El historial de versiones es la base del motor de ajuste y de la exportación; el peso del cuestionario es el primer pesaje |
| T-65 | Planes | `Plan` y `Routine` se guardan como versiones `active` que marcan la anterior como `superseded`; `details` guarda la salida completa del motor más los mensajes ya renderizados; cada plan nuevo deja una fila en `plan_adjustments` (`initial` o `profile_change`) | Reproducibilidad y auditoría (§3 del prompt); las plantillas no necesitan importar el motor para mostrar avisos |
| T-66 | Bloqueos | Nutrición bloqueada por seguridad (menor, embarazo, TCA, déficit con bajo peso) → se guarda el perfil pero ningún plan ni rutina, y la página de resultado explica los motivos recalculándolos; rutina imposible con el material → se guarda solo la nutrición | Una persona embarazada no debe recibir tampoco una rutina generada automáticamente; los motivos no se almacenan porque el motor es determinista |
| T-67 | Preferencias | Ejercicios que evitar o preferir se escriben por nombre con un `datalist` y se resuelven a slugs en el servidor (nombre español, inglés o slug, sin mayúsculas); un nombre desconocido es un error de validación | Un `select` de 190 ejercicios no es usable en móvil; sin JS obligatorio |
| T-68 | Fechas | `User.today()` calcula la fecha en la zona horaria del usuario (`tzdata` añadido para Windows) y la usan formularios, cuestionario y planes | Un pesaje o un plan fechado en UTC cambia de día a las dos de la madrugada en Madrid |
| T-69 | Suelo de carbohidratos | Tras redondear proteína (arriba), grasa y calorías (a 5 kcal), el motor sube las calorías en pasos de 5 kcal hasta que los carbohidratos enteros alcanzan el suelo entero | Hypothesis encontró un caso (100 cm, 121 kg) con 180 g frente a un suelo de 182 g: el redondeo podía dejar el suelo 2 g por debajo |

## 2026-09-09 — Fase 9 (panel y visualización)

| ID | Tema | Decisión | Motivo |
|---|---|---|---|
| T-70 | Librerías | Alpine.js 3.17.2 (`dist/cdn.min.js`) y Chart.js 4.5.1 (`dist/chart.umd.js`) descargadas de jsDelivr a `app/static/vendor/` con sus licencias MIT; Chart.js solo se incluye en las páginas con gráficas | D-05 (sin build, vendorizado); 208 KB de Chart.js no hacen falta en el cuestionario ni en las cuentas |
| T-71 | Gráficas sin scripts inline | Los datos van en `<script type="application/json" id="…-data">` y `static/js/forja.js` construye cada `<canvas data-chart data-kind>`; colores leídos de las variables CSS del tema | La CSP no permite scripts inline (T-06); las gráficas siguen al tema oscuro/claro sin duplicar paletas |
| T-72 | Sin JavaScript | Todas las páginas funcionan sin JS: las gráficas desaparecen (queda la tabla), las instrucciones y alternativas usan `<details>` nativo; Alpine solo alterna la ilustración inicial/final (la segunda imagen lleva `hidden` de serie) | Mobile-first y accesibilidad (§6): el contenido no depende de que el script cargue |
| T-73 | Próxima sesión | El día siguiente a la última sesión *completada* de la rutina vigente, cíclico; sin sesiones, el día 1 | Sin calendario fijo: la gente entrena cuando puede; las sesiones abandonadas no avanzan el ciclo |
| T-74 | Alternativas | En la página del día se listan las alternativas del catálogo filtradas con el mismo criterio del generador (material, contraindicaciones, nivel, aversiones); todavía no se sustituyen | La sustitución cambia la rutina guardada y pertenece al registro de entrenos (Fase 10) |
| T-75 | Móvil | Verificación a 390 px con Edge headless dentro de un `iframe` de 390 px (el navegador clampa la ventana a 492 px) y a 1440 px; capturas revisadas a mano | El criterio de la fase pide "probado en móvil" y no hay dispositivo físico; los puntos de rotura 320/768/1440 se revisan en la Fase 11 |
| T-76 | Historial y revisión | La página de nutrición muestra todas las versiones del plan con el ajuste que las creó y la fecha de la próxima revisión (último ajuste + 14 días) | Transparencia del motor de ajuste (§3.8) antes de que exista el registro de datos |

## 2026-09-09 — Fase 10 (registro y ajuste conectado)

| ID | Tema | Decisión | Motivo |
|---|---|---|---|
| T-77 | Sesión única | Un usuario solo puede tener una sesión en marcha; empezar otra devuelve la abierta con un aviso | En el gimnasio se abre la sesión y se olvida; dos sesiones abiertas repartirían las series entre ambas |
| T-78 | Series | Una fila por sesión, ejercicio y número de serie: repetir el número corrige en vez de duplicar; se admiten 2 series por encima de lo prescrito | Corregir un peso mal tecleado es lo normal; hacer una serie de más también |
| T-79 | Sustituciones | El ejercicio sustituto se guarda en `workout_sessions.substitutions` (JSON `{prescripción: ejercicio}`), solo para esa sesión, y solo entre las alternativas viables; se bloquea si ya hay series registradas | La rutina generada no se toca por una máquina ocupada un martes; cambiar el ejercicio después de registrar series dejaría las series colgando del ejercicio equivocado |
| T-80 | Progresión | La sesión sugiere la carga de la última vez y solo sube el incremento cuando todas las series llegaron al tope de repeticiones (progresión doble) | Es la regla que ya prescribe el motor de rutinas; la app la aplica sola en vez de pedirla de memoria |
| T-81 | Marcas | El progreso usa el 1RM estimado de Epley (`kg × (1 + reps/30)`) sobre la mejor serie efectiva de cada sesión | Permite comparar sesiones con repeticiones distintas; las series de calentamiento no cuentan |
| T-82 | Revisión manual | La revisión quincenal nunca se aplica sola: `/revision` enseña qué haría el motor y con qué datos, y solo cambia algo al pulsar | Cambiar las calorías de alguien sin avisar es lo contrario de lo que pide §3.8; además obliga a mirar la adherencia antes |
| T-83 | Qué escribe una revisión | Con cambio de calorías se crea una versión nueva del plan (la anterior queda `superseded`, con la misma rutina); sin cambio se guarda solo la fila de auditoría con la decisión completa en `data` | El historial de planes queda íntegro y la próxima revisión se ancla en la última, no en el alta del plan |
| T-84 | URL del diario | El diario vive en `/diario`: `/registro` ya era el alta de cuenta | Flask registra las dos reglas y gana la primera, así que el diario quedaba inalcanzable. Hay un test que falla si dos endpoints comparten regla y método |
| T-85 | Media móvil | Solo se promedian los días con la ventana de 7 completa (antes bastaban 3 pesajes) | Las ventanas parciales del principio de la serie tienen el centro de masa a media velocidad: la pendiente salía más plana y el motor **infravaloraba la velocidad de pérdida**, la única dirección en la que el tope de seguridad no puede fallar |
| T-86 | Redondeo de los escalones | Los recortes redondean hacia arriba y las subidas hacia abajo, en vez de al múltiplo de 5 más cercano | Redondear al más cercano dejaba recortes del 5,1 % cuando el tope documentado es el 5 % |
| T-87 | Orden de los scripts | `forja.js` se carga antes que Alpine | Alpine arranca en un microtask nada más ejecutarse: si sus componentes se registran después, `alpine:init` ya ha pasado y `x-data="restTimer(...)"` no resuelve, así que el temporizador desaparecía en vez de contar |

## 2026-09-09 — Fase 11 (diseño visual)

| ID | Tema | Decisión | Motivo |
|---|---|---|---|
| T-88 | Paleta | Paleta "Forja": naranja `#FF8A34` sobre carbón `#0E1013`, elegida por el usuario entre tres propuestas (naranja, cian y lima). Un solo acento; el color nunca lleva la información solo | Encaja con el nombre y se separa del azul con el que se parecen todas las apps del sector; ver `docs/DISEÑO.md` |
| T-89 | Contraste | Token `--border-strong` para bordes de campos y botones, además del `--border` decorativo, y un test que lee los tokens del CSS y comprueba cada par | WCAG 2.1 (1.4.11) pide 3:1 en los controles, y el borde anterior se quedaba en 1,5:1. El test evita que un retoque de color rompa la accesibilidad sin que nadie se entere |
| T-90 | Tipografías | Barlow Condensed (titulares) e Inter (cuerpo), descargadas al repositorio con sus licencias OFL en vez de enlazar Google Fonts | Sin peticiones a terceros en caliente y sin depender de que un CDN responda; la condensada deja "Día 3 · Torso B" en una línea a 320 px |
| T-91 | Iconos | Lucide, un único set, solo los 28 iconos usados, en un sprite **incrustado** en la página en vez de enlazado | Un `<use href="fichero.svg#id">` que falle deja los botones vacíos, y el fichero externo además no cruza orígenes. El trazo va en la clase `.icon` porque un `<symbol>` hereda la presentación de quien lo instancia, no del sprite |
| T-92 | Tema claro | El tema se guarda en la sesión y se cambia con un formulario POST, sin JavaScript ni `localStorage` | Sin parpadeo al cargar (el servidor ya sabe qué tema pintar) y funciona con el script desactivado; no hace falta migración ni columna nueva |
| T-93 | Movimiento | Las animaciones de entrada solo mueven, nunca cambian la opacidad, y todo se apaga con `prefers-reduced-motion` | Una animación que no llegue a ejecutarse (bfcache, motor sin animaciones) no puede dejar contenido invisible. Se detectó en las capturas: las tarjetas de estadísticas salían en blanco |
| T-94 | Navegación en móvil | Por debajo de 34 rem la navegación se queda en iconos y el texto pasa a ser accesible pero invisible | Seis destinos no caben con texto en 320 px: se partían en tres líneas encima de la marca |
| T-95 | Fotografía | No se añade fotografía de stock; la portada usa las ilustraciones del catálogo (dominio público) y composición tipográfica | Unsplash y Pexels necesitan clave de API para atribuir como piden sus licencias, y no se mete nada cuya licencia no se pueda documentar en `docs/CREDITOS.md` |

## 2026-09-09 — Fase 12 (exportación, cuenta y RGPD)

| ID | Tema | Decisión | Motivo |
|---|---|---|---|
| T-96 | PDF | ReportLab, elegida por el usuario entre ReportLab, fpdf2 y una página para imprimir | Rueda de Python pura con licencia BSD y sin librerías del sistema: instala igual en Windows y en el VPS. Descartada WeasyPrint por necesitar GTK en Windows |
| T-97 | Tipografía del PDF | Helvetica, la incrustada de serie, en vez de Barlow e Inter | Las de la app están en woff2 y ReportLab necesita TTF: serían 500 KB más y un paso de conversión, a cambio de que un documento que se imprime se parezca algo más a la app |
| T-98 | Contenido del PDF | Objetivo, comidas, ciclado, cómo se ha calculado (con las fórmulas nombradas) y la rutina día a día; el aviso de herramienta orientativa en **todas** las páginas, no solo en la primera | Es el documento que alguien le enseña a su médico o a su dietista: tiene que explicarse solo y no puede parecer una prescripción |
| T-99 | PDF sin plan | Si la seguridad bloqueó el plan, el PDF se genera igual y lista los motivos | Es justo lo que conviene llevarle a un profesional |
| T-100 | Exportación de datos | Un ZIP con un CSV por tipo de dato (once) más un LEEME que explica las columnas; UTF-8 con BOM y fechas ISO | Cumple el derecho de portabilidad (RGPD, artículo 20) en un formato que abre cualquier hoja de cálculo sin pelearse con los acentos |
| T-101 | Nombre del fichero | El nombre de la persona se pasa a ASCII para el `Content-Disposition` | Un nombre con acentos o en otro alfabeto rompe la cabecera; se detectó con "Ana Ríos" |
| T-102 | Credenciales | Cambiar el correo o la contraseña exige la contraseña actual; el borrado exige contraseña **y** escribir BORRAR | Quien se deja la sesión abierta no debería perder la cuenta por un despiste ajeno |
| T-103 | Borrado RGPD | Borrado real en cascada (`db.session.delete(user)`), no una marca de borrado | El artículo 17 es supresión, no ocultación. Los `SoftDeleteMixin` siguen sirviendo para deshacer cosas dentro de la app, pero no para esto |

## 2026-09-09 — Uso real (cambios a partir de probar la app)

| ID | Tema | Decisión | Motivo |
|---|---|---|---|
| T-104 | Paso de material | El paso llega resuelto: el material del sitio ya marcado, con un resumen («Gimnasio básico · 19 marcados») y la lista de 34 casillas plegada tras «Ajustar lo que tengo»; el material que no se reconoce por el nombre lleva una línea de ayuda («Contractora (pec deck): sentado, juntas los brazos por delante del pecho») | Era un muro de scroll con vocabulario de gimnasio. Quien entrena donde siempre no tiene que tocar nada, y quien ajusta ya sabe qué está marcando |
| T-105 | Lesiones | Una casilla, «Tengo alguna molestia o lesión»; las ocho zonas y su gravedad solo aparecen si se marca | Ocho desplegables en «Sin molestias» ocupaban media pantalla para no decir nada en el 90 % de los casos |
| T-106 | Ejercicios que gustan y no gustan | Fuera del cuestionario. Se marcan desde la rutina, con el botón «No me gusta: cámbialo» de cada ejercicio, que lo aparta para siempre y lo cambia por su mejor alternativa; se deshace desde «Ejercicios apartados» | Pedirlos en el cuestionario era pedir que alguien escribiera de memoria nombres exactos de un catálogo de 190, antes de haber visto ninguno. Con la ficha delante la decisión es informada |
| T-107 | Descanso entre series | Nunca menos de dos minutos (`MIN_REST_SECONDS = 120`), 3 min en los básicos. También en aislamiento y en peso corporal | Un minuto parece que cunde y no cunde: la serie siguiente pierde repeticiones y la sesión acaba con menos volumen efectivo del que dice el plan. Si no cabe el tiempo, se recortan ejercicios de aislamiento, nunca el descanso |
| T-108 | Estimación del tiempo por serie | `AVERAGE_SET_MINUTES` se calcula de la tabla de descansos en vez de ser un 2,5 fijo | Con el suelo nuevo, el número viejo mentía: el motor planificaba de más y luego recortaba. Ahora el reparto de volumen ya nace realista y el aviso dice la verdad |
| T-109 | Cardio | La prescripción dice **con qué** se hace, según el material marcado y las articulaciones declaradas: máquinas si hay máquina de cardio, opciones sin impacto si hay rodilla, tobillo, cadera o lumbar tocados, y al aire libre en el resto | «2 sesiones LISS de 30 min» dejaba a la persona adivinando, y la casilla «Máquina de cardio» no la miraba nadie: estaba de adorno |
| T-110 | Frecuencia de pesaje | Pesarse a diario deja de ser un requisito: con tres pesajes repartidos en tres semanas el motor estima la tendencia sobre los pesajes tal cual (sin media móvil), la marca como confianza baja, espacia la revisión a 28 días, parte el escalón a la mitad y no se mueve por diferencias menores de 0,2 kg/semana. Los límites de seguridad no se relajan | Con una vez al mes la app no revisaba **nunca** y encima pedía "sigue registrando el peso a diario": exigía de facto tres pesajes por semana. Pero dos puntos sueltos en catorce días son ruido de agua y sal, así que la salida no es ajustar igual, sino mirar más lejos y tocar menos |
| T-111 | Tono del día a día | El panel, el diario y la revisión hablan a la persona, no de nuestro cálculo. Explicar la fórmula sigue estando bien, pero en su sitio: la sección "Cómo lo calculamos" de la página de nutrición | "Con al menos tres pesajes por semana calculamos la media de 7 días, que es la que cuenta" estaba dicho dos veces en la misma tarjeta y sonaba a manual de estadística |

## 2026-11-11 y 12 — Coherencia y marca Alza

| ID | Tema | Decisión | Motivo |
|---|---|---|---|
| T-112 | Preguntas que no se usaban | Fuera del cuestionario aversiones, alergias, presupuesto, tiempo de cocina, cafeína y la nota de salud. El patrón de dieta y el alcohol se quedan porque ahora cuentan: la dieta vegana sube la proteína 0,2 g/kg y el alcohol sale como aviso con sus kcal | Preguntar algo que luego no cambia nada es pedir tiempo a cambio de nada, y la persona lo nota |
| T-113 | Peso sugerido | Desde la primera serie (`engine/routines/loads.py`): una estimación prudente para empezar, y cada serie ajusta la siguiente según la reserva apuntada | «Primera vez: elige tú» dejaba sola a quien más ayuda necesita |
| T-114 | Formato de cifras y fechas | Filtros `num`, `signed`, `kg`, `duration`, `fdate`, `tempo` y `days_from_now` (`app/formatting.py`), en el idioma y la zona horaria de quien lee. En castellano, las cifras de cuatro dígitos no se separan («1995 kcal», «8000 pasos»; RAE) y desde 10.000 sí; en inglés, coma de miles siempre | Babel separaba «1.995» al lado de los «1823» de las plantillas: dos normas en la misma pantalla |
| T-115 | Lenguaje | Sin jerga en ninguna pantalla: reserva (no RIR), intervalos (no HIIT), bloques y semana suave (no mesociclo y descarga), «Medidas» (no perímetros), «lo que gastas en reposo» (no metabolismo basal), «Empujar al frente» (no empuje horizontal). Los nombres de las fórmulas solo aparecen en «Cómo lo calculamos». `test_coherence` mantiene la lista de palabras prohibidas | La app se va a vender a gente que no ha leído un manual de entrenamiento; cada palabra que hay que buscar es un abandono |
| T-116 | Decimales en formularios | Campo propio (`app/fields.py`) que acepta coma o punto y devuelve la cifra en el formato de quien lee | En España se escribe «63,9», y el campo de WTForms lo rechazaba con un error en inglés |
| T-117 | Navegación en el móvil | Barra inferior fija con icono y nombre de las cinco secciones | Los iconos solos en la cabecera no se entendían y quedaban lejos del pulgar |
| T-118 | Marca | **Alza** (dominio `alza.fit`) sustituye al nombre de trabajo Forja. Marca: una A en forma de flecha hacia arriba sobre el naranja de la paleta, con una sola geometría para la cabecera, el PDF y los iconos (`scripts/build_brand.py`) | Elegido por el dueño del producto el 2026-11-11; la flecha dice «subir» sin necesidad de texto y la A se lee incluso a 16 px |
| T-119 | Nombres internos | `ALZA_ENV`, `alza.db`, `alza.log`, `alza.js`, sin compatibilidad con los antiguos | No hay ningún despliegue ni `.env` que dependa de ellos, y mantener dos nombres es justo la incoherencia que se quiere quitar. La base local se copió a `instance/alza.db`; `instance/forja.db` queda como copia y se puede borrar |

## 2026-11-12 — Funcionalidades para vender

| ID | Tema | Decisión | Motivo |
|---|---|---|---|
| T-120 | Ficha de ejercicio | Al tocar un ejercicio (día, rutina, sesión, alternativas) se abre una hoja encima con vídeo o animación, músculos, material, pasos y tu historial con él; sin JavaScript es una página. Sustituye a «Buscar vídeo» (una búsqueda en YouTube) | Es lo que la gente espera de Hevy: ver cómo se hace sin salir de la sesión. Mostrar tu mejor serie y con cuánto empezar convierte la ficha en algo tuyo, no en una enciclopedia |
| T-121 | Fuente de los vídeos | wger (CC-BY-SA 4.0), emparejado a mano y revisado fotograma a fotograma: 32 ejercicios. Convertidos a H.264 640x360 sin sonido (unos 700 KB) con la autoría debajo del vídeo | wger solo tiene 46 ejercicios con vídeo y en HEVC hasta 4K, que Chrome y Firefox en Windows no reproducen. Un emparejamiento automático por nombre confundía ejercicios distintos; un vídeo equivocado es peor que ninguno |
| T-122 | Ejercicios sin vídeo | Sus dos fotos alternándose en bucle (con «reducir movimiento», una al lado de la otra) | Da a los 190 algo parecido a un vídeo sin depender de contenido que no existe con licencia abierta |
| T-123 | Pasos en castellano | Escritos para la app (3-5 pasos breves) a partir de las instrucciones de free-exercise-db, y no tomados de wger | Así coinciden exactamente con las fotos de cada ejercicio; las de wger son de otros ejercicios parecidos y en muchos casos no están en castellano |
| T-124 | Fecha de llegada | Función pura del motor (`adjustment/projection.py`): la tendencia de la revisión sobre cuatro semanas y una banda del 80 % con el error estándar de la pendiente sobre los pesajes tal cual. Sin tendencia, la fecha sale del plan y lo dice; estable, al revés o a más de dos años, lo dice en vez de inventar una fecha | La media móvil está autocorrelada y daría una banda falsamente estrecha. Una fecha falsa desmotiva más que ninguna |
| T-125 | Plan en un minuto | Una pantalla con cuerpo, objetivo, días, minutos, sitio, experiencia y las dos preguntas de salud que bloquean el plan; el resto con `QUICK_DEFAULTS` prudentes. Mismos campos y validaciones que el cuestionario completo, que sigue disponible. Con molestias, al paso de lesiones | Cada paso pierde gente antes de ver el valor. Lo que no se pregunta toma el valor que no puede hacer daño: «sedentario» no sobrestima el gasto, y la revisión corrige con los datos reales |
| T-126 | App instalable | Manifiesto e iconos, service worker desde la raíz: páginas de uso diario primero de la red y, sin red, la última copia; estáticos de caché; vídeos nunca. La versión de la app en la URL del worker limpia las cachés viejas | Un gimnasio sin cobertura no puede dejar la sesión en blanco |
| T-127 | Series sin cobertura | Cola en el móvil (localStorage) que se repinta sobre la copia guardada y se envía sola al volver la red; el servidor sobrescribe la misma serie, así que reenviar no duplica. Al cerrar sesión se borran cola y páginas guardadas | localStorage basta para unas pocas series y funciona en todos los navegadores; la idempotencia ya existía en `log_set`. Nada de otra persona debe quedarse en un móvil compartido |
| T-128 | Pantalla encendida | Wake Lock durante la sesión, reactivado al volver a la pestaña | Desbloquear el móvil entre series es la queja más repetida de las apps de entreno |
| T-129 | Marcas | Se celebran al guardar la serie que supera el mejor máximo estimado de sesiones anteriores; la primera vez no cuenta y repetir la misma serie tampoco | Celebrar algo que no lo es (la primera vez) quita valor a las marcas de verdad |
| T-130 | Racha | Semanal, con un día de margen (días del plan menos uno), y la semana en curso nunca la rompe | Una racha diaria castiga el descanso, que es parte del plan. Perder la racha por un imprevisto hace abandonar |

## 2026-11-12 — Pagos, comida y menú

| ID | Tema | Decisión | Motivo |
|---|---|---|---|
| T-131 | Pasarela de pago | Dos implementaciones con el mismo contrato: `fake` (simula Stripe de punta a punta y emite los mismos eventos) y `stripe` (API por HTTPS sin SDK y webhooks firmados). La suscripción solo cambia aplicando eventos con la forma de Stripe, guardados en `billing_events` para no aplicarlos dos veces | El dueño del producto pidió simularlo hasta tener su cuenta: así pasar a la real es configuración, no código. Sin SDK hay una dependencia menos y cuatro llamadas no lo justifican |
| T-132 | Producción y pagos | No arranca con la pasarela simulada y el muro de pago activo, ni con Stripe sin sus cuatro claves | La simulada regala Pro a quien la pulse |
| T-133 | Qué es Pro | Fecha de llegada, buscador de alimentos y código de barras, habituales, copiar ayer, menú y lista de la compra. Siempre gratis: plan, rutina, sesiones, fichas, revisión quincenal, límites de seguridad, total de comida a mano y exportación | La revisión sube calorías cuando se pierde peso demasiado rápido: una protección de seguridad no puede cobrarse. El total a mano mantiene la revisión funcionando sin pagar |
| T-134 | Precio | 7,99 € al mes o 49,99 € al año, 7 días de prueba (una sola vez) | Lo propuesto en la auditoría, entre Fitia y MacroFactor |
| T-135 | Borrar la cuenta con suscripción | Se cancela en la pasarela antes de borrar; si falla, no se borra nada | Una cuenta borrada no puede seguir pagando |
| T-136 | Alimentos | Tabla propia de 80 alimentos comunes (sin red, al instante) y después Open Food Facts filtrado por España; código de barras escrito o con la cámara (BarcodeDetector). Los valores se copian al apuntar y se vuelven a leer del origen, nunca del navegador; productos sin alguno de los cuatro valores, fuera | Open Food Facts es abierto y tiene los productos del súper español, pero lo escriben voluntarios: mejor no enseñar que inventar ceros |
| T-137 | Total del día con alimentos | Sale de los alimentos (y el formulario a mano solo guarda el % de cumplimiento) | Dos fuentes para el mismo número acaban contradiciéndose |
| T-138 | Cámara | `Permissions-Policy: camera=(self)` | Escanear códigos; micrófono, ubicación y pagos siguen cerrados |
| T-139 | Menú | Platos con proteína, hidrato y grasa principales cuyos gramos salen de resolver las tres ecuaciones de cada comida con límites, redondeo a 5 g y huevos enteros; las legumbres van como hidrato; los platos de soja solo en dieta vegana. Siete días deterministas por persona y variante | Así «apuntar» registra exactamente lo que se ve, y el menú cuadra con el plan en vez de ser una lista de recetas genérica |

## 2026-11-12 — Revisión del dueño del producto y plato y barra conectados

| ID | Tema | Decisión | Motivo |
|---|---|---|---|
| T-140 | Revisión quincenal | Gratis, confirmado por el dueño del producto | Es la que protege cuando se pierde peso demasiado rápido |
| T-141 | Información precontractual | En precios y en el pago: IVA incluido, renovación automática, cómo cancelar y derecho de desistimiento de 14 días con la prueba gratis dentro del plazo | Directiva 2011/83/UE y TRLGDCU; conviene que lo revise un abogado antes de cobrar |
| T-142 | Cancelar | Un clic desde Tu suscripción (cancela al final del periodo) y otro para reanudar, sin pasar por el portal | Darse de baja tiene que ser igual de fácil que darse de alta |
| T-143 | Desistimiento | Dentro de los 14 días: termina al momento y, en Stripe, se reembolsa íntegra la última factura pagada | Más sencillo y más favorable que prorratear; no hay que pedir consentimiento para empezar a prestar el servicio |
| T-144 | Orden de los eventos de Stripe | `last_event_at` por suscripción: un evento anterior al último aplicado se descarta | Stripe no garantiza el orden de entrega |
| T-145 | Atribución | Página «Acerca de» con todas las fuentes y licencias, y la mención de Open Food Facts (ODbL) visible en el buscador | La ODbL exige atribución visible |
| T-146 | Código de barras | El botón de escanear solo aparece si el navegador lee EAN/UPC; si no (iPhone, escritorio), entrada a mano con etiqueta visible y explicación | Safari no trae BarcodeDetector; Edge en Windows lo trae sin formatos |
| T-147 | Aviso de salud | Breve, en el plan de calorías, el resultado y la revisión, además del pie | Es donde se deciden o cambian las calorías |
| T-148 | Cómo llegas hoy | Sueño (una pregunta al empezar), lo comido ayer frente al objetivo, la fatiga de la última sesión y las semanas de déficit suman puntos: 2-3 día suave (−5 % de carga en la primera serie, +1 de reserva), 4 o más más suave (−10 %). Sin datos no suma; se puede elegir entrenar normal | Une el plato y la barra con datos que la app ya tiene, sin pedir más registros. Solo toca la primera serie: las siguientes ya se ajustan solas |
| T-149 | Día de entreno o de descanso | Con más hidratos los días de entreno, el objetivo del día es el de entreno si ese día se empezó una sesión, y el de descanso si no | Las rutinas no tienen días de la semana fijos; la sesión real es la señal fiable |

## 2026-11-12 — iPhone y RGPD

| ID | Tema | Decisión | Motivo |
|---|---|---|---|
| T-150 | Escáner en iPhone | Si el navegador no lee EAN/UPC con BarcodeDetector, se carga ZXing (servido desde el propio servidor, MIT) y se lee con `getUserMedia`; `?lector=zxing` lo fuerza para probar | Safari no trae BarcodeDetector; la entrada a mano queda siempre visible |
| T-151 | Consentimiento de salud | Casilla propia en el registro, sin premarcar, con fecha y versión del texto guardadas; las cuentas anteriores lo dan al volver a entrar | Art. 9.2.a RGPD: explícito, aparte de las condiciones y demostrable |
| T-152 | Sin consentimiento | Solo cuenta, exportación, borrado, suscripción y páginas públicas; lo demás redirige a darlo | Sin consentimiento no se puede guardar ni mostrar un dato de salud, pero sí llevarse los datos o borrar la cuenta |
| T-153 | Retirar el consentimiento | Borra en el momento todos los datos de salud y deja la cuenta y la suscripción; pide la contraseña | Retirarlo tiene que ser tan fácil como darlo y no obliga a perder la cuenta |
| T-154 | Tipo de dieta | Dentro del mismo consentimiento, nombrado expresamente (halal y kosher pueden revelar creencias) | Una casilla más complica el registro; queda anotado para el abogado |
| T-155 | Registros | Ruta sin la parte de búsqueda, rotación diaria y 30 días | La búsqueda de alimentos dice qué come la persona |
| T-156 | Datos en el móvil | `Clear-Site-Data: "cache", "storage"` al retirar el consentimiento y al borrar la cuenta | La copia para usar la app sin red también tiene datos de salud |
| T-157 | Alojamiento y copias | En la UE, copias cifradas que caducan a los 30 días y borrados reaplicados al restaurar (`docs/PRIVACIDAD.md`) | Así el borrado llega también a las copias en un plazo que se puede prometer |
