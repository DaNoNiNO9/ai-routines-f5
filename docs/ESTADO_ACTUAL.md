# Estado actual

Documento vivo: se actualiza **dentro** de cada fase, no solo al cerrarla. Para el detalle de lo ya cerrado, ver `docs/fases/FASE_XX_INFORME.md`; para el porqué de cada decisión, `docs/DECISIONES.md`.

Última actualización: 2026-09-09.

## Fase actual

**Fase 13 cerrada.** Con ella se cierran las trece fases del prompt maestro. Ver `docs/ESTADO_FINAL.md` y `docs/AUDITORIA_FINAL.md`.

## Terminado

| Fase | Contenido | Informe |
|---|---|---|
| 0-1 | Entorno, factory, configuración por entorno, logging, errores, seguridad, i18n | `FASE_00`, `FASE_01` |
| 2 | Modelos y migraciones Alembic | `FASE_02` |
| 3 | Catálogo de 190 ejercicios con imágenes locales | `FASE_03` |
| 4-6 | Motor: nutrición, rutinas y ajuste, como funciones puras | `FASE_04`, `FASE_05`, `FASE_06` |
| 7 | Autenticación, recuperación por correo, CSRF, rate limiting | `FASE_07` |
| 8 | Cuestionario multipaso que genera y guarda plan y rutina | `FASE_08` |
| 9 | Panel, nutrición y entrenamiento con gráficas e ilustraciones | `FASE_09` |
| 10 | Diario (peso, ingesta, actividad, perímetros), sesiones de entrenamiento con temporizador y revisión quincenal aplicable | `FASE_10` |
| 11 | Diseño visual: paleta Forja, tipografías e iconos vendorizados, tema claro, estados y micro-interacciones | `FASE_11` |
| 12 | Exportación del plan en PDF y de los datos en CSV, ajustes de cuenta y borrado RGPD | `FASE_12` |
| — | Catálogo inglés completo (809 mensajes): interfaz, avisos del motor, PDF, LEEME del ZIP y nombres del catálogo | `FASE_TRADUCCIONES` |
| 13 | Auditoría final: motor con datos de los bordes, seguridad, robustez, límites de §3.5, rendimiento y calidad | `FASE_13` |

## Estado del repositorio

| Comprobación | Estado |
|---|---|
| Arranque de la app | OK |
| Suite | 622 tests en verde |
| Cobertura de `app/` | 98,6 % (motor 99,2 %) |
| Linter y formato | limpios |
| Migración aplicada | `976a93809ca2` (cabeza) |
| Rama | `main`, sin remoto todavía |

## Qué estoy haciendo ahora

Nada en curso. Las trece fases están cerradas y la auditoría final, hecha: siete hallazgos, todos corregidos y con su test.

## Siguiente paso

Puesta en producción, cuando toque (`docs/ESTADO_FINAL.md`, "Lo que falta"):

1. El remoto de GitHub, cuando pases la URL.
2. Postgres: el código está preparado, pero solo se ha ejecutado sobre SQLite.
3. Correo real y verificación de la dirección al cambiarla.
4. Exportaciones en segundo plano si las cuentas acumulan años de datos.
5. Instrucciones de los ejercicios en castellano y traducción de los nombres generados y guardados.

## Detalles menores heredados

- Los nombres generados y guardados en la base (rutina «Torso / pierna · 4 días», días «Torso A», comidas «Desayuno») se muestran tal cual en los dos idiomas: son datos, no interfaz.
- El contador de series muestra "3/2" cuando se hacen más de las prescritas; es correcto pero se lee raro.
- `instructions_es` sigue vacío: las instrucciones salen en inglés, marcadas como tales.
- No hay fotografía de stock por no poder documentar su licencia (T-95).

## Cómo se trabaja

- No se empieza una fase sin la anterior probada, testeada y validada.
- Cada fase termina con: app levantada y comprobada, suite en verde, linter limpio, README del módulo e informe en `docs/fases/`.
- Este documento se actualiza dentro de la fase, no solo al cerrarla; commit `wip:` cada vez que el repositorio queda consistente.
- Lo que no esté claro se pregunta por terminal en vez de asumirlo.

## Aviso permanente

La app es una herramienta orientativa y no sustituye a un profesional sanitario. Los límites de seguridad del motor (§3.5 del prompt) se verifican sobre las cifras finales de cada plan y no se pueden desactivar desde la interfaz.
