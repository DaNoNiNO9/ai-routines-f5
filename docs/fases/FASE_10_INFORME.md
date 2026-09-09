# Fase 10 — Registro de entrenos, peso e ingesta, y motor de ajuste conectado

Fecha: 2026-09-09. Estado: **cerrada**.

## Qué se ha hecho

- **Diario** (`/diario`): peso, ingesta (kcal, macros y adherencia) y actividad (pasos y cardio) por día, con el día elegible y nunca en el futuro; tabla de los últimos 14 días con los huecos a la vista; perímetros semanales en `/diario/perimetros` con su historial. Una fila por usuario y día: guardar otra vez reemplaza.
- **Sesión de entrenamiento** (`/entreno`): se empieza desde la página del día; una sola sesión abierta por usuario (T-77); una fila por serie con kg, repeticiones y RIR, prerrellenada con la carga sugerida por progresión doble (T-80); repetir el número de serie corrige en vez de duplicar y se admiten dos series de más (T-78); borrado de series; sustitución de un ejercicio solo para esa sesión y solo entre las alternativas viables (T-79); temporizador de descanso pegado abajo, con +30 s y vibración al acabar; cronómetro de la sesión; cierre con fatiga percibida y notas; resumen con series efectivas, repeticiones, kilos movidos, duración y marcas por 1RM estimado de Epley (T-81); historial y gráfica de progreso por ejercicio.
- **Revisión quincenal** (`/revision`): enseña qué ve el motor (pesajes, días con ingesta, adherencia, tendencia, gasto observado) y qué propone, sin escribir nada; el botón solo aparece cuando toca. Al aplicar guarda una de tres cosas: versión nueva del plan si cambian las calorías, objetivo de pasos nuevo, o solo la fila de auditoría (T-82, T-83).
- **Modelo**: columna `substitutions` en `workout_sessions` (migración `976a93809ca2`, aplicada).
- **Servicios** `tracking.py`, `workouts.py` y `adjustments.py`; `plans.persist_plan()` acepta ahora el motivo, la explicación y los datos de una revisión, y guarda el objetivo de pasos con el plan.
- **Correcciones del motor** encontradas al conectarlo con datos reales (ver más abajo).
- Documentación: `docs/ESTADO_ACTUAL.md` (nuevo, se actualiza dentro de la fase), `app/README.md`, `app/services/README.md`, `docs/ARQUITECTURA.md`, `docs/MODELO_DATOS.md`, `docs/DECISIONES.md` T-77 a T-87.

## Qué se ha probado

| Prueba | Cómo | Resultado |
|---|---|---|
| Diario (servicio) | `tests/unit/services/test_tracking_service.py` | 7 tests, 100 % de `tracking.py` |
| Sesiones (servicio) | `tests/unit/services/test_workouts_service.py` (series, índices fuera de rango, sesión cerrada, sustituciones válidas e inválidas, progresión doble, calentamientos que no cuentan, marcas, historial, progreso, sesiones ajenas) | 14 tests, 96,6 % de `workouts.py` |
| Revisión (servicio) | `tests/unit/services/test_adjustments_service.py` (esperar antes de tiempo, recorte con tope del 5 %, suelo calórico que fuerza pasos, pérdida demasiado rápida, en objetivo, adherencia baja, gasto observado, próxima revisión) | 11 tests, 96,1 % de `adjustments.py` |
| Diario (web) | `tests/integration/test_tracking_pages.py` | 8 tests, 100 % de rutas y formularios |
| Sesión completa (web) | `tests/integration/test_workout_flow.py` (empezar, series, temporizador, sustitución, borrado, cierre, resumen, historial, progreso, sesión ajena → 404) | 10 tests |
| Revisión (web) | `tests/integration/test_review_page.py` | 5 tests |
| Casos límite | `tests/integration/test_logging_edge_cases.py` (revisión insegura, día futuro, sesión cerrada, fatiga imposible, sustitución malformada) | 5 tests |
| Suite completa | `pytest --cov` | 511 passed; cobertura de `app/` 98,5 % |
| Linter y formato | `ruff check .`, `ruff format --check .` | limpios |
| Migraciones | `flask db upgrade` sobre `instance/forja.db`; `test_migrations.py` | cabeza `976a93809ca2`; migración = modelos; downgrade limpio |
| Servidor real | `flask run --no-reload` + `curl.exe`: cuestionario completo → sesión del día 2 con 5 series en 2 ejercicios → contadores 3/2 y 2/2 → cierre → resumen (5 series, 48 repeticiones, 2640 kg, 2 marcas) → historial → progreso → diario (83,6 kg, 2100 kcal, 9200 pasos, LISS 30 min) → perímetros → revisión | OK, sin errores nuevos en `logs/forja.log` ni trazas en consola |
| Acentos de punta a punta | POST real con `urllib` (no `curl.exe`, que en Git-Bash convierte los argumentos a la página de códigos de Windows): "Ácida" y "Sesión de prueba, ñandú" | Guardados y leídos exactos |
| Móvil | Capturas a 390 px de la sesión en vivo y del diario, revisadas a mano | Temporizador contando (2:43), cronómetro de sesión, series hechas en verde, formularios de una línea por serie |

## Errores aparecidos y cómo se corrigieron

1. **La app no arrancaba.** La sesión anterior se cortó con `app/__init__.py` registrando el blueprint `tracking` sin que existieran sus `routes.py` ni `forms.py`. 162 fallos de la suite venían todos del mismo `ModuleNotFoundError`. Escritos los dos ficheros que faltaban.
2. **Colisión de URL**: el diario se registró bajo `/registro`, que ya era el alta de cuenta. Flask guarda las dos reglas y gana la primera, así que el diario era inalcanzable. El diario pasó a `/diario` y hay un test que falla si dos endpoints comparten regla y método (T-84).
3. **La media móvil infravaloraba la velocidad de pérdida** (motor, Fase 6). Aceptaba ventanas parciales al principio de la serie; el centro de masa de esas ventanas avanza a la mitad de velocidad, así que la pendiente salía más plana. Con una pérdida real de 0,70 kg/semana el motor leía 0,62 y **no disparaba el tope de seguridad** (0,625 para 62,5 kg). Ahora solo promedia días con la ventana de 7 completa (T-85).
4. **Un recorte podía superar el 5 %** documentado: se redondeaba al múltiplo de 5 más cercano (1665 → 1580, un 5,1 %). Ahora los recortes redondean hacia arriba y las subidas hacia abajo (T-86). El test de la Fase 6 que toleraba `+1 kcal` ya no lo necesita.
5. **El temporizador de descanso no existía.** Alpine arranca en un microtask nada más ejecutarse, y `forja.js` se cargaba después: `alpine:init` ya había pasado, `x-data="restTimer(...)"` no resolvía y `x-show="visible"` sobre una variable inexistente ocultaba el aviso. `forja.js` va ahora antes que Alpine, con un test que comprueba el orden (T-87). Lo detectaron las capturas, no la suite.
6. **El texto de ayuda se solapaba con el botón anterior** en el diario: `.help` tenía un margen superior negativo pensado para ir pegado a un campo. Ahora solo lo tiene cuando sigue a un campo (`.field + .help`).
7. **Un día inválido se rechazaba en silencio**: viaja en un campo oculto y `hidden_tag()` no pinta sus errores, así que la página volvía igual sin explicar nada. La ruta saca el motivo como aviso.
8. **Un cardio con tipo pero sin minutos se guardaba igual**: `Optional()` corta la cadena de validación cuando el campo está vacío, así que el validador cruzado nunca llegaba a ejecutarse (el mismo tropiezo que con la cadera en la Fase 8). La comprobación pasó al nivel del formulario.
9. **La próxima revisión se anclaba en el alta del plan**, no en la última revisión, porque `next_review_on()` miraba cualquier fila de auditoría. Ahora ignora las de creación (`initial`, `profile_change`).
10. Artefactos de mis propias pruebas, no de la app: marcas de tiempo futuras que violaban el CHECK `finished_at >= started_at`, una extracción de ids con `grep` que devolvía cadenas vacías, y acentos mutilados por la conversión de argumentos de Git-Bash a `curl.exe`.

## Limitaciones conocidas

- El temporizador de descanso vive en la página: si se cierra el navegador, se pierde la cuenta (no hay notificación del sistema ni Service Worker).
- La sustitución de un ejercicio vale para la sesión en curso; no aprende ni propone cambiar la rutina si se repite.
- El contador de series muestra "3/2" cuando se hacen más de las prescritas. Es correcto, pero se lee raro; se revisa en la Fase 11.
- El diario no tiene base de alimentos: las calorías y macros se teclean (decisión D-07).
- La revisión usa la ingesta registrada; sin ella el motor se queda con la tendencia de peso y el TDEE teórico.

## Pendiente

- Fase 11: diseño visual completo (paleta, tipografía, iconos, imágenes, estados de carga, animaciones, revisión a 320/768/1440 px y contraste AA).
- Fase 12: exportación PDF y CSV, ajustes de cuenta y borrado RGPD.

## Criterio de cierre

Flujo completo de una sesión registrada y persistida, comprobado en el servidor real y en capturas de móvil. Cumplido.
