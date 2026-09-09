# Estado actual

Documento vivo: se actualiza **dentro** de cada fase, no solo al cerrarla. Para el detalle de lo ya cerrado, ver `docs/fases/FASE_XX_INFORME.md`; para el porqué de cada decisión, `docs/DECISIONES.md`.

Última actualización: 2026-09-09.

## Fase actual

**Fase 10 — Registro de entrenos, peso e ingesta, y motor de ajuste conectado.** En curso.

## Terminado (fases 0 a 9, commiteadas)

| Fase | Contenido | Informe |
|---|---|---|
| 0-1 | Entorno, factory, configuración por entorno, logging, errores, seguridad, i18n | `FASE_00`, `FASE_01` |
| 2 | Modelos y migraciones Alembic | `FASE_02` |
| 3 | Catálogo de 190 ejercicios con imágenes locales | `FASE_03` |
| 4-6 | Motor: nutrición, rutinas y ajuste, como funciones puras | `FASE_04`, `FASE_05`, `FASE_06` |
| 7 | Autenticación, recuperación por correo, CSRF, rate limiting | `FASE_07` |
| 8 | Cuestionario multipaso que genera y guarda plan y rutina | `FASE_08` |
| 9 | Panel, nutrición y entrenamiento con gráficas e ilustraciones | `FASE_09` |

Último commit de fase cerrada: `e941497` (cierre de la Fase 9). En ese punto: 449 tests en verde, cobertura de `app/` 98,9 %, linter limpio.

## Qué estoy haciendo ahora (Fase 10)

Estado del repo: **consistente**. La app arranca, la migración está aplicada (`976a93809ca2`, cabeza), el linter está limpio y la suite pasa con 481 tests (los servicios de la Fase 10 ya están cubiertos; faltan los de integración).

Escrito:

- `app/services/tracking.py` — diario (peso, ingesta, actividad) y perímetros, con altas idempotentes por día.
- `app/services/workouts.py` — sesiones, series, sustituciones por sesión, cierre, resumen con marcas, historial y progreso por ejercicio (1RM estimado de Epley).
- `app/services/adjustments.py` — revisión quincenal: construye las entradas del motor con los registros reales, `preview()` no escribe y `apply()` guarda versión nueva del plan, cambio de pasos o revisión sin cambios.
- Blueprints `tracking` (`/diario`), `workouts` (`/entreno`) y `review` (`/revision`) con sus plantillas.
- Temporizador de descanso y gráfica de progreso en `static/js/forja.js`; CSS de la sesión en vivo.
- Blueprint `tracking` con sus formularios (peso, ingesta, actividad, perímetros), rangos espejo de los CHECK.
- Migración `976a93809ca2`: columna `substitutions` en `workout_sessions`. **Aplicada.**

## Siguiente paso

1. Tests de integración de la Fase 10: diario, flujo completo de una sesión y página de revisión.
2. Verificación con el servidor levantado: registrar una sesión entera, pesajes e ingestas, y aplicar una revisión.
3. Informe `docs/fases/FASE_10_INFORME.md` y cierre.

## Incidencias de esta fase

- **Resuelta**: el blueprint del diario colisionaba con `auth.register` en `/registro` (alta de cuenta). El diario vive ahora en `/diario`. Pendiente: test de regresión que detecte dos endpoints con la misma regla y método.
- **Resuelta (motor, Fase 6)**: la media móvil aceptaba ventanas parciales al principio de la serie. El centro de masa de esas ventanas avanza a media velocidad, así que la pendiente salía más plana que la real y el motor **infravaloraba la velocidad de pérdida**, justo la dirección en la que el tope de seguridad no puede equivocarse. Ahora solo promedia días con la ventana de 7 completa.
- **Resuelta (motor, Fase 6)**: los escalones de calorías se redondeaban al múltiplo de 5 más cercano, así que un recorte podía quedar en el 5,1 % en vez del 5 % tope. Ahora los recortes redondean hacia arriba y las subidas hacia abajo: ningún escalón supera su límite documentado.

## Aviso permanente

La app es una herramienta orientativa y no sustituye a un profesional sanitario. Los límites de seguridad del motor (§3.5 del prompt) se verifican sobre las cifras finales de cada plan y no se pueden desactivar desde la interfaz.
