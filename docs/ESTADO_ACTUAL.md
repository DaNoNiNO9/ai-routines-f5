# Estado actual

Documento vivo: se actualiza **dentro** de cada fase, no solo al cerrarla. Para el detalle de lo ya cerrado, ver `docs/fases/FASE_XX_INFORME.md`; para el porqué de cada decisión, `docs/DECISIONES.md`.

Última actualización: 2026-09-09.

## Fase actual

**Fase 11 — Diseño visual.** En curso.

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

## Estado del repositorio

| Comprobación | Estado |
|---|---|
| Arranque de la app | OK |
| Suite | 542 tests en verde |
| Cobertura de `app/` | 98,5 % |
| Linter y formato | limpios |
| Migración aplicada | `976a93809ca2` (cabeza) |
| Rama | `main`, sin remoto todavía |

## Qué estoy haciendo ahora

Paleta y tipografía elegidas por el usuario: **A "Forja"** (naranja `#FF8A34` sobre carbón `#0E1013`) y **Barlow Condensed + Inter**.

Hecho: tipografías descargadas al proyecto (`app/static/fonts/`, OFL), sprite de iconos de Lucide con solo los 28 que se usan (`scripts/build_icons.py`), tokens de la paleta con borde reforzado para controles, escala tipográfica, cifras tabulares, estados vacíos con icono, micro-interacciones con `prefers-reduced-motion`, estado de carga en los botones, resalte de la serie recién guardada, cambio de tema oscuro/claro sin JavaScript y portada nueva.

Pendiente: revisión a 320, 768 y 1440 px, `docs/DISEÑO.md` con las referencias, créditos de las nuevas licencias e informe de fase.

## Siguiente paso

Fase 11 (diseño visual, §6 del prompt). Antes de tocar nada hay que **proponer 2-3 paletas con sus códigos hex y esperar el visto bueno**, igual que con la tipografía si hay duda. Lo que ya está encargado para esa fase:

- Revisión a 320, 768 y 1440 px y contraste WCAG AA verificado.
- Tipografías de Google Fonts descargadas a `app/static/fonts/` y un set de iconos único (Lucide, Phosphor o Tabler), con licencias en `docs/CREDITOS.md`.
- Estados de carga, vacío y error diseñados; micro-interacciones sin excesos.
- Detalle heredado de la Fase 10: el contador de series muestra "3/2" cuando se hacen más de las prescritas; se lee raro.

## Cómo se trabaja

- No se empieza una fase sin la anterior probada, testeada y validada.
- Cada fase termina con: app levantada y comprobada, suite en verde, linter limpio, README del módulo e informe en `docs/fases/`.
- Este documento se actualiza dentro de la fase, no solo al cerrarla; commit `wip:` cada vez que el repositorio queda consistente.
- Lo que no esté claro se pregunta por terminal en vez de asumirlo.

## Aviso permanente

La app es una herramienta orientativa y no sustituye a un profesional sanitario. Los límites de seguridad del motor (§3.5 del prompt) se verifican sobre las cifras finales de cada plan y no se pueden desactivar desde la interfaz.
