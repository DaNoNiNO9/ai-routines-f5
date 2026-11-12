# Estado actual

Documento vivo: se actualiza **dentro** de cada fase, no solo al cerrarla. Para el detalle de lo ya cerrado, ver `docs/fases/FASE_XX_INFORME.md`; para el porqué de cada decisión, `docs/DECISIONES.md`.

Última actualización: 2026-11-12.

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
| 11 | Diseño visual: paleta naranja sobre carbón, tipografías e iconos vendorizados, tema claro, estados y micro-interacciones | `FASE_11` |
| 12 | Exportación del plan en PDF y de los datos en CSV, ajustes de cuenta y borrado RGPD | `FASE_12` |
| — | Catálogo inglés completo (809 mensajes): interfaz, avisos del motor, PDF, LEEME del ZIP y nombres del catálogo | `FASE_TRADUCCIONES` |
| 13 | Auditoría final: motor con datos de los bordes, seguridad, robustez, límites de §3.5, rendimiento y calidad | `FASE_13` |

## Estado del repositorio

| Comprobación | Estado |
|---|---|
| Arranque de la app | OK |
| Suite | 818 tests en verde |
| Cobertura de `app/` | 98,3 % |
| Linter y formato | limpios |
| Migración aplicada | `1784f54561b7` (cabeza) |
| Rama | `main`, con remoto `origin` en GitHub (https://github.com/DaNoNiNO9/ai-routines-f5) |

## Qué estoy haciendo ahora

**Primer bloque de funcionalidades para vender, terminado el 2026-11-12.** Decisiones T-120 a T-130 en `docs/DECISIONES.md`.

Hecho (cada una probada en el navegador, además de con tests):

- **Ficha de ejercicio tipo Hevy**: vídeo de wger en 32 ejercicios, animación con las dos fotos en el resto, músculos, material, pasos en castellano para los 190 e historial propio (mejor serie, máximo estimado, con cuánto empezar). Se abre encima de la sesión sin perderla.
- **Tu fecha de llegada** en el inicio, con banda de confianza, camino recorrido y lo previsto frente a lo real.
- **Tu plan en un minuto**: una pantalla y plan al instante; el cuestionario completo sigue disponible.
- **App instalable** que funciona sin cobertura: la sesión abre sin red, las series quedan en cola y se envían solas, y la pantalla no se apaga durante la sesión.
- **Marcas celebradas en el momento** y **racha semanal** con un día de margen.
- Antes, el mismo día: marca Alza, catálogo inglés al 100 % y barrido de jerga, coma decimal y cifras.

Después, el mismo día (T-131 a T-139):

- **Alza Pro con pagos**: precios, prueba gratis de 7 días, tu suscripción y muro de pago. La pasarela es **simulada** hasta que el dueño del producto dé su cuenta de Stripe; la real está escrita y probada contra respuestas con la forma de Stripe. Para activarla: `BILLING_BACKEND=stripe` y las variables `STRIPE_*` (ver `.env.example`).
- **Apuntar comida en segundos**: tabla básica, Open Food Facts, código de barras, habituales y copiar ayer.
- **Menú de la semana** con platos que cuadran con el plan, lista de la compra y «apuntar» con un toque.

Después de la revisión del dueño del producto (T-140 a T-149): información precontractual en precios, cancelar y reanudar en un clic, desistimiento de 14 días con reembolso, eventos de Stripe desordenados, guía de Stripe en modo test en el README, página «Acerca de» con atribuciones, código de barras pensado para iPhone, avisos de salud y **plato y barra conectados** (día suave según sueño, comida y fatiga; objetivo de día de entreno o de descanso).

Después (T-150 a T-157): **escáner en iPhone** con ZXing como plan B y **RGPD**: consentimiento explícito y aparte para datos de salud, retirable desde Cuenta (borra todos los datos de salud), borrador de política de privacidad en `/privacidad` para el abogado, auditoría de lo que sale de la app (ningún dato de salud a terceros) y notas para producción en `docs/PRIVACIDAD.md`. **Historias de usuario** con criterios de aceptación en `docs/HISTORIAS_DE_USUARIO.md`.

RGPD cerrado en el código el 2026-11-12 (T-158: borrados que se vuelven a aplicar al restaurar una copia). Lo que queda es de fuera: abogado y alojamiento.

**Para la sesión del 2026-11-13** (pedido por el dueño del producto; traerá más cosas):

1. **Ayuda dentro de la app**: modales de ayuda donde haga falta (revisar pantalla a pantalla dónde se atasca alguien nuevo: el día suave, la reserva RIR, la revisión quincenal, la fecha de llegada, el material, los macros…). Que no estorben a quien ya sabe: se abren a demanda.
2. **Cambiador de idioma visible** (hoy el idioma solo se cambia en Cuenta o por el navegador): en la cabecera o el pie, también para quien no ha entrado.
3. **Revisar las traducciones** al inglés pantalla a pantalla, con capturas, no solo el catálogo al 100 %.
4. Lo que diga el dueño mañana.

Pendiente sin fecha:

1. **Foto de la comida con IA**: pendiente de que el dueño elija proveedor; exige revisar el consentimiento (RGPD art. 9).
2. Activar Stripe real con sus claves de test (README › Pagos con Stripe).
3. Abogado: política de privacidad, condiciones y EIPD; elegir alojamiento en la UE.

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
