# Fase 13 — Auditoría final

Fecha: 2026-09-09. Estado: **cerrada**.

Esta fase no añade funcionalidad: revisa lo que hay. El detalle de cada hallazgo, con su severidad y su corrección, está en `docs/AUDITORIA_FINAL.md`; la foto del proyecto, en `docs/ESTADO_FINAL.md`. Aquí queda lo que se hizo, cómo se probó y qué se aprendió.

## Qué se ha hecho

- **Barridos del motor con datos de los bordes** en vez de casos escogidos: 1536 perfiles de nutrición, 640 rutinas y 3600 revisiones de ajuste, comprobando invariantes (los macros cuadran con las calorías, nada por debajo del suelo, nada más rápido del 1 % semanal, ningún día vacío, ningún ejercicio con material que no se tiene ni contraindicado, ninguna nota que se imprima como su código). Los barridos quedan como test: `tests/unit/engine/test_extreme_profiles.py`.
- **Auditoría de seguridad desde fuera**: IDOR ruta por ruta con dos cuentas, XSS con carga real en los cinco sitios donde se pinta texto libre, inyección en formularios y parámetros, CSRF, contraseñas, secretos y puertas cerradas (`tests/integration/test_audit_security.py`).
- **Reverificación de los límites de §3.5** manipulando el formulario y mandando peticiones directas: menores, embarazo o lactancia, antecedentes de TCA, IMC bajo, números imposibles y campos colados. Más el aviso de herramienta orientativa en las nueve pantallas que enseñan plan (`tests/integration/test_audit_safety.py`).
- **Robustez**: fallo a mitad de la generación del plan, doble clic en todo lo que escribe, cuentas sin datos, borrado en cascada (`tests/integration/test_audit_robustness.py`).
- **Rendimiento con datos de verdad**: 1000 cuentas, 4000 sesiones y 100.000 series en una base real, midiendo tiempo y consultas por página, más un test que vigila que las consultas no crezcan con las filas (`tests/integration/test_audit_performance.py`).
- **Calidad**: cobertura (98,6 % de `app/`, 99,2 % del motor), código muerto, argumentos sin usar, código comentado, TODO y READMEs de módulo.

## Qué se ha probado

| Prueba | Cómo | Resultado |
|---|---|---|
| Perfiles extremos | 1536 nutriciones, 640 rutinas, 3600 revisiones | 2 hallazgos, corregidos |
| Seguridad | 9 tests: IDOR, XSS, inyección, CSRF, argon2, secretos, rutas privadas | sin hallazgos |
| Límites de §3.5 | 8 tests desde el formulario y por petición directa | sin hallazgos |
| Robustez | 7 tests | sin hallazgos |
| Rendimiento | Servidor real con 100.000 series | 3 hallazgos, corregidos |
| Validez de la suite | Dos cuentas en el mismo test | 1 hallazgo, corregido |
| Suite completa | `pytest --cov` | **622 passed**, `app/` 98,6 %, `engine/` 99,2 % |
| Linter y formato | `ruff check .`, `ruff format --check .` | limpios |
| Migraciones | `flask db current` / `heads` | `976a93809ca2`, cabeza única |
| Servidor real, castellano | Alta → cuestionario → diario → sesión con series → resumen → historial → progreso → revisión → PDF | 11 páginas correctas, ningún código interno a la vista |
| Servidor real, inglés | El mismo paseo con `?lang=en` | interfaz, avisos, PDF y LEEME en inglés |
| **Capturas revisadas a ojo** | 14 páginas a 1440 px y 5 a 390 px con Edge headless | correctas |

## Errores aparecidos y cómo se corrigieron

Siete hallazgos; el detalle está en `docs/AUDITORIA_FINAL.md`. En corto:

1. **Días de rutina vacíos** con peso corporal y todas las lesiones graves: ahora se caen, la semana se renumera y se avisa.
2. **Una bajada de calorías podía cruzar el suelo** en mantenimiento y superávit, y el aviso llegaba a decir "bajadas" mientras subían: las tres ramas comparten ahora la misma salida, con los pasos como palanca cuando el suelo no deja sitio.
3. **Códigos internos en los avisos** (`upper_lower`, `glutes`, `horizontal_push`): segundo enchufe de traducción para los parámetros.
4. **El historial tardaba 7,2 segundos** con 400 sesiones y lanzaba 255 consultas: una consulta agrupada, 96 ms y 6 consultas.
5. **El progreso por ejercicio** pedía las series sesión a sesión (355 consultas): ahora 2.
6. **La página de un día** traía alternativas y material uno a uno (78 consultas): ahora 13; la rutina, de 34 a 7.
7. **La suite de tests compartía usuario e idioma entre peticiones**, así que un test de aislamiento entre cuentas podía pasar sin comprobar nada. El cliente de pruebas los olvida ahora antes de cada petición; al arreglarlo apareció un test que se apoyaba en el fallo.

## Lo que enseña esta fase

- **Los barridos encuentran lo que los casos escogidos no.** Los dos fallos del motor estaban en combinaciones que a nadie se le ocurre escribir a mano: peso corporal con ocho lesiones graves, un plan por debajo de su propio suelo.
- **Contar consultas es mejor termómetro que medir milisegundos.** 7,2 segundos en un portátil son un aviso; 255 consultas para pintar 50 filas son un diagnóstico.
- **Un test verde puede no estar probando nada.** El hallazgo más incómodo no estaba en la app sino en el andamiaje: dos cuentas que en realidad eran la misma. Merece la pena desconfiar de un test que pasa a la primera cuando se escribe para demostrar que algo falla.

## Pendiente

Lo que queda no es deuda de esta fase sino trabajo de puesta en producción, listado en `docs/ESTADO_FINAL.md`: remoto de git, Postgres, correo real, exportaciones en segundo plano, instrucciones en castellano y traducción del contenido guardado.

## Criterio de cierre

Auditoría completa con sus hallazgos corregidos y sus tests, suite en verde, linter limpio, app paseada en los dos idiomas contra un servidor real y capturas revisadas a ojo. `docs/AUDITORIA_FINAL.md` y `docs/ESTADO_FINAL.md` escritos. Cumplido.
