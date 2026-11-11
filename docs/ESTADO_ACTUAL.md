# Estado actual

Documento vivo: se actualiza **dentro** de cada fase, no solo al cerrarla. Para el detalle de lo ya cerrado, ver `docs/fases/FASE_XX_INFORME.md`; para el porqué de cada decisión, `docs/DECISIONES.md`.

Última actualización: 2026-11-11.

## Fase actual

**Fases 0-13 cerradas.** Ahora se cambian cosas a partir de usar la app: ver `docs/DECISIONES.md`, bloque «Uso real».

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
| Suite | 633 tests en verde |
| Cobertura de `app/` | 98,6 % (motor 99,2 %) |
| Linter y formato | limpios |
| Migración aplicada | `976a93809ca2` (cabeza) |
| Rama | `main`, con remoto `origin` en GitHub (https://github.com/DaNoNiNO9/ai-routines-f5) |

## Qué estoy haciendo ahora

**Pausa el 2026-11-11 por la noche, a mitad del barrido de coherencia.** Encargo: arreglar los fallos de la auditoría de producto, que no quede ninguna incoherencia ni jerga, y cambiar la marca a **Alza** (dominio `alza.fit`). Después vendrán las funcionalidades nuevas (ver la auditoría en el artifact «Rumbo de Forja»).

Hecho y con commit:

- Los seis fallos de la auditoría: contraste de «Crear cuenta», preguntas que no se usaban (fuera aversiones, alergias, presupuesto, cocina, cafeína y la nota de salud; la dieta vegana sube la proteína y el alcohol sale como aviso), peso sugerido desde la primera serie y ajuste entre series (`app/engine/routines/loads.py`), revisión sin fecha repetida, «Katch-McArdle».
- `app/formatting.py`: filtros `num`, `signed`, `kg`, `duration`, `fdate`, `tempo` y `days_from_now`; fechas en la zona horaria de la persona.
- Barrido de lenguaje en todas las plantillas, los avisos del motor y el PDF (reserva en vez de RIR, intervalos en vez de HIIT, bloques en vez de mesociclo, «Inicio» en vez de «Panel»…).
- Historial del plan reconstruido desde los códigos guardados (`adjustments.describe`).
- Barra de navegación inferior con nombres en el móvil.
- `tests/integration/test_coherence.py` vigila fechas ISO, códigos internos, `None` y decimales con punto en todas las pantallas.

Pendiente, en este orden:

1. **Catálogo inglés**: extraer, traducir los textos nuevos y compilar. Hasta entonces fallan 3 tests de `tests/integration/test_i18n.py`, y es lo esperado (ya esperan el inglés nuevo: «You eat 20 % less than you burn.», «Worth knowing», «How to progress»).
2. **Marca Alza**: `APP_NAME`, logo en la cabecera, favicon, PDF, LEEME del ZIP, nombre de los ficheros exportados, «Forja es solo para mayores de 18 años» en `onboarding/forms.py`, portada y docs.
3. **Pasada real**: cuenta nueva y capturas a 390 y 1440 px de todas las pantallas (sobre todo la barra inferior y la sesión), y suite completa en verde.
4. Decisiones nuevas en `docs/DECISIONES.md` (T-112 en adelante) y subir a GitHub.

## Siguiente paso

Puesta en producción, cuando toque (`docs/ESTADO_FINAL.md`, "Lo que falta"):

1. Postgres: el código está preparado, pero solo se ha ejecutado sobre SQLite.
2. Correo real y verificación de la dirección al cambiarla.
3. Exportaciones en segundo plano si las cuentas acumulan años de datos.
4. Instrucciones de los ejercicios en castellano y traducción de los nombres generados y guardados.

## Detalles menores heredados

- Los nombres generados y guardados en la base (rutina «Torso / pierna · 4 días», días «Torso A», comidas «Desayuno») se muestran tal cual en los dos idiomas: son datos, no interfaz.
- El paso 4 pliega el material con Alpine: sin JavaScript no se puede ajustar (se envía el preset del sitio) ni declarar lesiones.
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
