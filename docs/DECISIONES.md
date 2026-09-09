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
