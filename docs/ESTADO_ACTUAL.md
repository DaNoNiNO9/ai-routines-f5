# Estado actual

Documento vivo: se actualiza **dentro** de cada fase, no solo al cerrarla. Para el detalle de lo ya cerrado, ver `docs/fases/FASE_XX_INFORME.md`; para el porqué de cada decisión, `docs/DECISIONES.md`.

Última actualización: 2026-09-09.

## Fase actual

**Fase 13 (auditoría final) en curso.** Hecho: motor, seguridad, robustez, límites de §3.5 y rendimiento. Pendiente: calidad (código muerto, READMEs) y los dos documentos de cierre.

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
| — | Catálogo inglés completo (802 mensajes): interfaz, avisos del motor, PDF, LEEME del ZIP y nombres del catálogo | `FASE_TRADUCCIONES` |

## Estado del repositorio

| Comprobación | Estado |
|---|---|
| Arranque de la app | OK |
| Suite | 619 tests en verde |
| Cobertura de `app/` | 98,4 % |
| Linter y formato | limpios |
| Migración aplicada | `976a93809ca2` (cabeza) |
| Rama | `main`, sin remoto todavía |

## Qué estoy haciendo ahora

**Fase 13**, cinco bloques cerrados:

- **Motor**: 1536 perfiles de nutrición, 640 rutinas y 3600 revisiones con datos de los bordes. Tres arreglos (días vacíos, bajadas por debajo del suelo, códigos internos en los avisos).
- **Seguridad**: IDOR probado ruta por ruta, XSS, inyección, CSRF, argon2, secretos fuera del repositorio.
- **Robustez**: fallo a mitad de la generación, doble clic en todo lo que escribe, cuentas sin datos, borrado en cascada.
- **Límites de §3.5**: menores, embarazo, TCA, IMC bajo, números imposibles y campos colados, probados desde el formulario.
- **Rendimiento**: 1000 cuentas y 100.000 series. El historial pasó de 7,2 s y 255 consultas a 96 ms y 6.

Falta el bloque de calidad y escribir `docs/AUDITORIA_FINAL.md` y `docs/ESTADO_FINAL.md`.

## Siguiente paso

**Fase 13: auditoría final (§7 del prompt).** Es la fase más larga y no añade funcionalidad: revisa lo que hay. Contenido:

- Robustez: excepciones sin controlar, divisiones por cero, `None` inesperados, transacciones a medias, condiciones de carrera.
- Casos extremos del motor con perfiles sintéticos: 40 y 200 kg, 140 y 210 cm, 16 y 85 años, 4 % y 60 % de grasa, todas las lesiones a la vez, sin material, objetivos incoherentes, campos con emojis y cadenas de 10.000 caracteres.
- Seguridad: inyección, XSS, CSRF, IDOR probado explícitamente, cabeceras, cookies, límites de peticiones, secretos fuera de git.
- Seguridad del usuario: reverificar uno por uno los límites de §3.5 intentando romperlos desde el formulario y por petición directa.
- Rendimiento: N+1, índices, tiempos con 1000 usuarios y 100.000 series generadas.
- Calidad: cobertura, código muerto, READMEs coherentes.
- Cierre: `docs/AUDITORIA_FINAL.md` con hallazgos, severidad y corrección, y `docs/ESTADO_FINAL.md`.

Después: cuando pases la URL, el remoto de GitHub.

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
