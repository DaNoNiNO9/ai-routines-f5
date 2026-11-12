# Estado final

Fecha: 2026-09-09. Fases 0-13 cerradas más el catálogo de traducciones. Este documento es la foto de lo que hay; para el detalle de cada fase, `docs/fases/`; para el porqué de cada decisión, `docs/DECISIONES.md`; para lo que se buscó y lo que apareció al final, `docs/AUDITORIA_FINAL.md`.

## Qué es Alza

Una aplicación web que calcula un plan de nutrición y una rutina de gimnasio a partir de un cuestionario, y los va corrigiendo cada dos semanas con lo que la persona registra de verdad: peso, comida, pasos y series. Cada número sale de una fórmula publicada y citada en el código, no de una regla del pulgar. Los límites de seguridad no se pueden desactivar desde la interfaz.

Es una herramienta orientativa. No sustituye a un médico ni a un dietista-nutricionista, y lo dice en todas las pantallas que enseñan un plan y en todas las páginas del PDF.

## El repositorio hoy

| Comprobación | Estado |
|---|---|
| Suite | **622 tests en verde** |
| Cobertura de `app/` | **98,6 %** (objetivo 85 %) |
| Cobertura de `app/engine/` | **99,2 %** (objetivo 95 %) |
| `ruff check .` y `ruff format --check .` | limpios |
| Migraciones | `976a93809ca2`, cabeza única, con su código |
| Arranque | `waitress-serve` en desarrollo y producción, `/health` responde |
| Rama | `main`, 79 commits temáticos, sin remoto todavía |
| Idiomas | castellano (referencia) e inglés, 809 mensajes traducidos |

Tamaño: 12.700 líneas de Python en `app/`, 1.700 de plantillas, 8.500 de tests. 190 ejercicios con 380 ilustraciones de dominio público.

## Qué hace, por fases

| Fase | Qué quedó hecho |
|---|---|
| 0-1 | Entorno reproducible, factory con configuración por entorno, logging con id de petición, páginas de error, cabeceras de seguridad, i18n cableado desde el principio |
| 2 | 20 tablas SQLAlchemy 2.0 con migraciones Alembic en modo batch |
| 3 | Catálogo de 190 ejercicios con material, patrones, contraindicaciones e imágenes locales |
| 4 | Motor de nutrición: composición corporal, metabolismo basal, gasto por componentes, objetivo calórico, macros, comidas y ciclado |
| 5 | Motor de rutinas: split por días y experiencia, volumen por músculo, selección por material y lesiones, prescripción con progresión doble, cardio y pasos |
| 6 | Motor de ajuste: media móvil de 7 días, tendencia por mínimos cuadrados, gasto observado por balance energético y reglas quincenales |
| 7 | Cuentas: alta, acceso, recuperación por correo, CSRF, límites de peticiones, argon2 |
| 8 | Cuestionario de 7 pasos con borrador por paso, versionado y generación del plan |
| 9 | Panel, nutrición y entrenamiento con gráficas e ilustraciones |
| 10 | Diario (peso, ingesta, actividad, perímetros), sesiones con temporizador y revisión quincenal aplicable |
| 11 | Diseño: paleta propia, tipografías e iconos vendorizados, tema claro y oscuro, estados y micro-interacciones, AA comprobado por test |
| 12 | Exportación del plan en PDF y de todos los datos en CSV, ajustes de cuenta y borrado RGPD real |
| — | Traducciones: catálogo inglés completo (interfaz, motor, PDF y LEEME) |
| 13 | Auditoría final: siete hallazgos corregidos con sus tests (ver `docs/AUDITORIA_FINAL.md`) |

## Cómo está montado

```
 Navegador (Jinja2 + Alpine.js + Chart.js vendorizados)
        │ HTTP
 ┌──────▼───────────────────────────────────────────────┐
 │ Flask: create_app() · 10 blueprints · WTForms ·      │
 │ errores · logging · seguridad · i18n                 │
 └──────┬───────────────────────────────────────────────┘
        │
 ┌──────▼───────┐          ┌────────────────────────────┐
 │ services/    │ ───────► │ engine/ (funciones puras,  │
 │ (transacción)│          │  sin Flask ni base de datos)│
 └──────┬───────┘          └────────────────────────────┘
        │
 ┌──────▼───────┐
 │ models/ +    │
 │ Alembic      │
 └──────────────┘
```

La regla que sostiene todo: **el motor no sabe que existe la web**. Recibe dataclasses, devuelve dataclasses y avisos con código estable, y no toca la base de datos ni el idioma. Por eso se puede barrer con 5.500 perfiles imposibles en un segundo y por eso sus tests no necesitan servidor.

## Rendimiento medido

Con 1000 cuentas, 4000 sesiones y 100.000 series (SQLite, portátil):

| Página | ms | consultas |
|---|---|---|
| `/panel` | 49 | 11 |
| `/nutricion` | 28 | 6 |
| `/entrenamiento` | 22 | 7 |
| `/entrenamiento/dia/1` | 56 | 13 |
| `/diario` | 25 | 8 |
| `/revision` | 17 | 8 |
| `/entreno/historial` | 96 | 6 |
| `/entreno/progreso` | 42 | 2 |
| `/cuenta/plan.pdf` | 21 | 7 |
| `/cuenta/datos.zip` | 335 | 15 |

`tests/integration/test_audit_performance.py` vigila que el número de consultas no crezca con los datos.

## Lo que falta para ponerlo en producción

1. ~~**Remoto de git.**~~ Hecho el 2026-11-11: `origin` → https://github.com/DaNoNiNO9/ai-routines-f5, rama `main` con seguimiento.
2. **Base de datos de verdad.** El código está preparado para Postgres (`DATABASE_URL`, migraciones en modo batch), pero solo se ha ejecutado sobre SQLite.
3. **Correo real.** El backend `smtp` está escrito y probado con un doble; falta un proveedor y verificar la dirección al cambiarla.
4. **Exportaciones en segundo plano** si las cuentas acumulan años de datos.
5. **Instrucciones en castellano** de los ejercicios (`instructions_es` está vacío; hoy salen en inglés, marcadas como tales).
6. **Contenido del catálogo traducido**: los nombres de ejercicio y material ya salen en inglés; los nombres generados y guardados (rutina, días, comidas) no.

## Cómo se ha trabajado

Trece fases, cada una cerrada con la app levantada y paseada a mano, la suite en verde, el linter limpio, el README del módulo al día y un informe en `docs/fases/`. Nada se ha dado por bueno por tener los tests en verde: el PDF se ha rasterizado y mirado página a página, las pantallas se han capturado a 320, 390, 768 y 1440 px, y el rendimiento se ha medido con datos, no estimado. Commits temáticos y pequeños; `docs/ESTADO_ACTUAL.md` actualizado dentro de cada fase, no solo al cerrarla.
