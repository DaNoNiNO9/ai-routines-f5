# Fase 9 — Panel y visualización del plan

Fecha: 2026-09-09. Estado: **cerrada**.

## Qué se ha hecho

- Librerías vendorizadas: Alpine.js 3.17.2 y Chart.js 4.5.1 en `app/static/vendor/` con sus licencias (T-70; `docs/CREDITOS.md`). `static/js/forja.js` construye las gráficas desde bloques JSON (T-71); no hay scripts inline.
- `app/services/dashboard.py`: serie de peso de 90 días con la media móvil de 7 días del motor (`WeightSeries`), próxima sesión (T-73), próxima revisión, historial de versiones con su ajuste, objetivos de hoy (con ciclado: día de entreno y de descanso), alternativas viables por ejercicio (T-74) e ilustraciones.
- `services/plans.py`: `exercise_info()` extraído para reutilizar la conversión fila → `ExerciseInfo`. `labels.py`: fórmulas de BMR, momentos de comida y estados de volumen.
- Panel (`/panel`): hoy (kcal y macros, o ambos tipos de día con ciclado; agua y fibra), próxima sesión con foco y duración, peso con último pesaje, media de 7 días y gráfica (a partir de dos pesajes), próxima revisión; estados vacíos honestos (sin plan, sin rutina, sin pesajes).
- Nutrición (`/nutricion`): objetivo diario (kcal, mantenimiento, balance, cambio esperado, modo y porcentaje), macros con gráfica de anillo y tabla (g, g/kg, kcal), comidas con momento, ciclado, "cómo lo calculamos" (composición corporal, tabla de fórmulas de BMR con la usada, gráfica de componentes del gasto, pasos, modificador, contraste clásico, base de proteína, suelo de carbohidratos), avisos del motor, protocolo de ajuste con la próxima revisión, historial de versiones (T-76). Sin plan: motivos del bloqueo.
- Entrenamiento (`/entrenamiento`): split, mesociclo, descarga, RIR por semana, próxima sesión destacada, tarjeta por día con ejercicios, volumen semanal por músculo con estado y prioridad, empuje/tracción, cardio y pasos, explicaciones del motor. Día (`/entrenamiento/dia/<n>`): tarjeta por ejercicio con las dos ilustraciones (Alpine alterna, la segunda va `hidden` de serie), patrón y músculo, series, reps, RIR, descanso, tempo, progresión, nota de unilateral, instrucciones (`<details>`, en inglés cuando no hay español), alternativas viables, enlace de vídeo; navegación entre días; 404 para índices inexistentes.
- Navegación con la página actual marcada (`aria-current`), Chart.js solo donde hay gráficas, CSS de tarjetas, rejillas, chips, tablas, prescripción y ajustes para pantallas de 30 rem.
- Documentación: `app/README.md`, `app/services/README.md`, `docs/ARQUITECTURA.md`, `docs/CREDITOS.md`, `docs/DECISIONES.md` T-70 a T-76, README raíz.

## Qué se ha probado

| Prueba | Cómo | Resultado |
|---|---|---|
| Servicio | `tests/unit/services/test_dashboard_service.py` (intervalo de revisión igual al del motor, serie de peso con ventana y media móvil, serie vacía, próxima sesión con sesiones completadas/abandonadas y vuelta al día 1, próxima revisión tras un ajuste, historial emparejado, objetivos de hoy con y sin ciclado, alternativas filtradas por material, aversiones y lesiones, ilustraciones) | 9 tests, 100 % de `dashboard.py` |
| Páginas | `tests/integration/test_plan_pages.py` (redirección sin perfil, panel con hoy/próxima sesión/peso/revisión y gráfica solo con dos pesajes, nutrición con todas las secciones y bloques JSON, rutina y día con imágenes, alternativas y 404, estados vacíos con plan bloqueado y con material imposible) | 6 tests, 100 % de las tres vistas |
| Suite completa | `pytest --cov` | 449 passed; cobertura de `app/` 98,9 % |
| Linter y formato | `ruff check .`, `ruff format --check .` | limpios |
| Servidor real | `flask run --no-reload` + `curl.exe`: registro → cuestionario completo (gimnasio completo, ciclado, rodilla leve) → `/panel` (2011 / 1527 kcal por tipo de día, próxima sesión, revisión), `/nutricion` (bloques `macros-data` y `tdee-data`, Katch-McArdle marcada, ciclado, historial), `/entrenamiento` (Torso / pierna · 4 días, RIR 3-2-2-1-1, prioridad), `/entrenamiento/dia/1` y `/dia/2` (6 ejercicios, 12 imágenes, 2-4 alternativas cada uno); estáticos 200 (Alpine 55 KB, Chart.js 208 KB, `forja.js`, CSS, una ilustración `image/jpeg`) | OK, sin errores nuevos en el log ni trazas |
| Móvil y escritorio | Capturas con Edge headless (T-75): panel, nutrición, rutina y día a 390 px (iframe) y a 1440 px, revisadas a mano | Sin desbordamiento horizontal; tarjetas apiladas; gráficas de anillo y barras renderizadas con los colores del tema; ilustraciones y rejilla de prescripción correctas |

## Errores aparecidos y cómo se corrigieron

1. **Capturas "móviles" engañosas**: Edge headless clampa la ventana a 492 px, así que las primeras capturas a 390 px eran un diseño de 492 px recortado (parecía un desbordamiento). Se comprobó con una página sonda (`innerWidth=492`) y se capturó dentro de un `iframe` de 390 px.
2. **Insignias de momento de comida partidas en dos líneas** dentro de la tabla: `white-space: nowrap` en `.badge`.
3. **Rejilla de tarjetas con una columna vacía** a 1440 px (mínimo 18 rem daba tres columnas para dos tarjetas): mínimo 22 rem.
4. **Unidad huérfana** ("g" en línea aparte) en el panel con ciclado: se quita la unidad de la fila de macros.
5. **Tabla de volumen apretada a 390 px**: menos relleno y fuente de 0,9 rem por debajo de 30 rem; "Objetivo" → "Rango".
6. **Tests de la Fase 8** que buscaban los textos antiguos del panel ("Ver mi plan"): actualizados.
7. **Variable sin usar** detectada por ruff en un test: renombrada.

## Limitaciones conocidas

- La gráfica de peso necesita al menos dos pesajes; hasta la Fase 10 el único es el del cuestionario.
- Las alternativas se listan pero no se pueden aplicar todavía (T-74).
- Las instrucciones de los ejercicios están en inglés (`instructions_es` vacío desde la Fase 3); la interfaz lo indica.
- "Probado en móvil" se ha hecho con emulación de 390 px, no con un dispositivo físico; los puntos de rotura 320/768/1440 y el contraste AA se revisan en la Fase 11.

## Pendiente

- Fase 10: registro de entrenos (series, temporizador de descanso), pesajes e ingesta, historial y gráficas de progreso; motor de ajuste conectado a los datos reales con `plan_adjustments`.

## Criterio de cierre

Renderizado correcto con datos reales (servidor en marcha, plan generado por el cuestionario) y probado en móvil (capturas a 390 px). Cumplido.
