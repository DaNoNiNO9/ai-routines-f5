# Estado actual

Documento vivo: se actualiza **dentro** de cada fase, no solo al cerrarla. Para el detalle de lo ya cerrado, ver `docs/fases/FASE_XX_INFORME.md`; para el porqué de cada decisión, `docs/DECISIONES.md`.

Última actualización: 2026-09-09.

## Fase actual

**Fase 12 — Exportación, cuenta y borrado RGPD.** En curso.

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

## Estado del repositorio

| Comprobación | Estado |
|---|---|
| Arranque de la app | OK |
| Suite | 562 tests en verde |
| Cobertura de `app/` | 98,5 % |
| Linter y formato | limpios |
| Migración aplicada | `976a93809ca2` (cabeza) |
| Rama | `main`, sin remoto todavía |

## Qué estoy haciendo ahora

Librería de PDF elegida por el usuario: **ReportLab** (BSD, Python puro, sin librerías del sistema).

Hecho: `services/exports.py` con el PDF del plan (nutrición, cómo se ha calculado, rutina día a día y el aviso en cada página) y el ZIP con un CSV por tipo de dato; blueprint `account` (`/cuenta`) con datos de la cuenta, cambio de correo y contraseña con la contraseña actual por delante, las dos descargas y el borrado con doble confirmación; borrado real en cascada, no una marca.

Pendiente: verificación con el servidor levantado abriendo el PDF de verdad, `docs/DECISIONES.md`, READMEs e informe de fase.

## Detalles menores heredados

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
