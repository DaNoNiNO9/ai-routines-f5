# Auditoría final

Fecha: 2026-09-09. Alcance: §7 del prompt maestro sobre el repositorio completo (fases 0-12 más el catálogo de traducciones).

Método: no se ha revisado el código leyéndolo y confiando en que está bien. Cada bloque se ha atacado desde fuera —barridos con datos de los bordes, peticiones desde otra cuenta, formularios manipulados, un servidor de verdad con 1000 cuentas y 100.000 series— y lo que ha aparecido está abajo, con su corrección y su test.

## Resumen

| Bloque | Qué se probó | Hallazgos |
|---|---|---|
| Motor | 1536 perfiles de nutrición, 640 rutinas y 3600 revisiones con valores extremos | 2 |
| Interfaz | Textos, avisos y códigos internos | 1 |
| Seguridad | IDOR, XSS, inyección, CSRF, cabeceras, cookies, límites, secretos, contraseñas | 0 |
| Seguridad del usuario (§3.5) | Los siete límites, desde el formulario y por petición directa | 0 |
| Robustez | Fallo a mitad de transacción, doble clic, cuentas vacías, borrado en cascada | 0 |
| Rendimiento | 1000 cuentas, 100.000 series, consultas por página | 3 |
| Calidad | Cobertura, código muerto, TODO, READMEs | 0 |
| Pruebas | Validez de la propia suite | 1 |

Siete hallazgos, todos corregidos y con test de regresión. Ninguno era una vulnerabilidad explotable; el más grave era de rendimiento (una página que dejaba de responder) y el más incómodo, de la propia suite de tests.

## Hallazgos

### H-01 · Días de rutina sin ningún ejercicio · Severidad media · Corregido

**Qué pasaba.** Con material de peso corporal en casa y las ocho lesiones declaradas como graves, el generador devolvía seis días de los cuales tres no tenían un solo ejercicio. La app ofrecía "Empuje A · 0 ejercicios · 8 minutos" y dejaba empezar una sesión vacía.

**Cómo apareció.** Barrido de 640 rutinas (todas las combinaciones de días × minutos × sitio × experiencia × lesiones × prioridades), comprobando invariantes en vez de números concretos.

**Por qué.** El generador ya se protegía del caso extremo (`if not any(day.items ...)` → bloqueo), pero no del intermedio: bastaba con que un día quedara lleno para que los demás pasaran vacíos.

**Corrección.** `build_routine()` descarta los días sin ejercicios, renumera la semana, ajusta `days_per_week` y añade el aviso `routine.days_dropped` diciendo cuántos y por qué. Con material normal no se cae ningún día.

**Test.** `tests/unit/engine/test_extreme_profiles.py::test_a_day_with_no_possible_exercise_is_dropped_not_left_empty` y el invariante general del barrido.

### H-02 · Una bajada de calorías podía cruzar el suelo de seguridad · Severidad media (defensiva) · Corregido

**Qué pasaba.** En modo mantenimiento, el recorte se calculaba y después se subía al suelo con un `max()`. Si el plan ya estaba por debajo del suelo, el resultado era **subir** las calorías mientras el aviso decía "Calorías bajadas 2000 kcal (400 %): de 500 a 2500 kcal". En superávit no se comprobaba el suelo en absoluto.

**Cómo apareció.** Barrido de 3600 revisiones, con un invariante que exige que el sentido del cambio coincida con lo que dice el aviso.

**Alcance real.** Hoy un plan generado siempre respeta el suelo, así que la rama es difícil de alcanzar en producción; llega ahí si el suelo sube (el metabolismo basal se recalcula al cambiar el cuestionario) por encima de las calorías del plan vigente.

**Corrección.** Las tres ramas (déficit, superávit, mantenimiento) bajan por el mismo sitio, `_reduce_or_steps()`: nunca por debajo del suelo y, si el suelo no deja sitio para recortar, la palanca son los pasos, con el aviso `adjust.floor_reached`.

**Test.** `test_a_cut_that_would_break_the_floor_moves_steps_instead` y los invariantes del barrido de ajuste.

### H-03 · Los avisos del motor enseñaban códigos internos · Severidad media · Corregido

**Qué pasaba.** "Split upper_lower de 4 días", "Volumen extra (+27 %) para glutes, shoulders", "El patrón horizontal_push se omite por las lesiones". El motor guarda códigos estables en los parámetros de cada aviso y nadie los traducía. Además, la sugerencia de material ("añadir una barra de dominadas") era texto castellano dentro de un parámetro, así que ni siquiera llegaba al catálogo.

**Corrección.** Un segundo enchufe en el motor, `params_translator`, que la factory sustituye por `labels.note_params()`: cambia los códigos por su etiqueta dentro de la petición y los deja intactos fuera (en los logs el código es lo que sirve para buscar). La sugerencia sale ahora de `app/labels.py`.

**Test.** `tests/unit/test_labels_and_forms.py::test_note_params_turn_internal_codes_into_words` y `::test_rendered_notes_never_show_an_internal_code`.

### H-04 · El historial de entrenos dejaba de responder · Severidad alta · Corregido

**Qué pasaba.** Con 400 sesiones registradas, `/entreno/historial` tardaba **7,2 segundos** y lanzaba **255 consultas**. Cada casilla del historial preguntaba "¿cuál era mi marca en este ejercicio antes de esta sesión?" por su cuenta, y esa consulta cargaba en memoria **todas** las series del ejercicio para quedarse con el máximo.

**Corrección.** `workouts.previous_bests()`: una consulta agrupada que calcula el 1RM de Epley en SQL y devuelve la mejor marca previa de cada par (sesión, ejercicio); el historial la calcula una vez y la reparte. **96 ms y 6 consultas.**

### H-05 · El progreso por ejercicio pedía las series sesión a sesión · Severidad media · Corregido

355 consultas: una por sesión para leer sus series. Ahora es una sola consulta que trae las series del ejercicio con la fecha de su sesión y elige la mejor en Python. **2 consultas.**

### H-06 · Consultas de más al pintar la rutina · Severidad baja · Corregido

`/entrenamiento/dia/N` lanzaba 78 consultas (las alternativas de cada ejercicio, sus fichas y el material de cada una, una a una) y `/entrenamiento` 34 (los días y sus ejercicios). Con una precarga en la página del día y los días ya cargados en `plans.active_routine()`: **13 y 7**.

### H-07 · La suite de tests se creía cosas · Severidad alta (validez de las pruebas) · Corregido

**Qué pasaba.** El fixture de base de datos mantiene abierto un contexto de aplicación durante todo el test y las peticiones lo reutilizan; en producción cada petición trae el suyo. Flask-Login y Flask-Babel cachean en `g`, así que **la segunda petición de un test se servía con el usuario y el idioma de la primera**. Un test escrito como "esta cuenta no puede ver lo de la otra" podía pasar sin comprobar nada, porque las dos peticiones eran la misma persona.

**Cómo apareció.** Escribiendo el test de IDOR con dos clientes: la segunda alta devolvía 302 pero no creaba usuario, y `/_auth/whoami` seguía diciendo el primero.

**Corrección.** El cliente de pruebas (`tests/conftest.py`, `FreshClient`) olvida esos dos cachés antes de cada petición. Al arreglarlo apareció un test que se apoyaba en el fallo (`test_profile_changes_are_saved_and_validated` esperaba castellano después de cambiar la cuenta a inglés); ahora comprueba lo correcto.

## Comprobado y sin hallazgos

**Seguridad.** IDOR probado ruta por ruta: otra cuenta recibe 404 en las siete rutas de entrenamiento y la sesión de la dueña queda intacta. Ninguna página privada se abre sin sesión (barrido del mapa de rutas). El texto libre vuelve escapado en las cinco páginas que lo pintan; no hay `|safe` en ninguna plantilla y el único `tojson` va dentro de `<script type="application/json">`. Las cargas de inyección se guardan como texto y las tablas siguen ahí. Un formulario sin token da 400 y no escribe. Las contraseñas se guardan con argon2. Cabeceras (CSP, X-Frame-Options, Referrer-Policy, Permissions-Policy, HSTS opcional), cookies (`HttpOnly`, `SameSite=Lax`, `Secure` en producción) y límites de peticiones ya tenían sus tests desde la Fase 7. Ni `.env` ni la base local están en el repositorio, y `.gitignore` los cubre.

**Seguridad del usuario (§3.5).** Reverificados uno a uno desde el formulario y por petición directa: menores de 18 (el paso 1 no pasa), embarazo o lactancia y antecedentes de TCA (no se genera plan de nutrición **ni rutina**, y la página explica por qué), IMC por debajo de 18,5 (sin plan de déficit), pesos y alturas imposibles (el formulario los rechaza antes del motor), campos colados en el POST (`calorie_target=800` se ignora: el motor calcula), suelo calórico y ritmo máximo de pérdida comprobados sobre el plan generado. El aviso de herramienta orientativa está en las nueve pantallas que enseñan plan y en todas las páginas del PDF.

**Robustez.** Un fallo a mitad de la generación del plan no deja media cosa escrita (ni perfil, ni plan, ni pesaje). El doble clic no duplica: empezar dos veces la misma sesión continúa la primera, empezar otro día avisa en vez de abrir una segunda, borrar dos veces la misma serie y terminar dos veces la misma sesión no son errores, y aplicar dos veces la revisión solo cambia el plan una vez. Una cuenta recién creada abre todas las páginas sin datos. Borrar la cuenta se lleva sesiones, planes y perfiles.

**Motor con datos de los bordes.** 1536 perfiles (25-350 kg, 100-250 cm, 10-110 años, 4 % y 60 % de grasa, 0 y 7 días de entrenamiento, 1 y 8 comidas, 0 y 60.000 pasos, los cinco objetivos, las tres agresividades) y 3600 revisiones (series de peso vacías, planas, con ruido de ±2,5 kg, saltadas, con un hueco de un año, ingestas de 0 y de 20.000 kcal, adherencia nula o ausente): ninguna excepción, ningún macro negativo, ningún plan por debajo del suelo, ninguna pérdida por encima del 1 % semanal, ninguna nota sin plantilla. Fuera de rango, el motor levanta `InputError` en vez de inventar.

**Calidad.** Cobertura: **98,4 %** de `app/` y **98,9 %** de `app/engine/` (objetivos: 85 % y 95 %). Linter y formateador limpios con la configuración del proyecto (que incluye ERA para código comentado y ARG para argumentos sin usar). Ni un `TODO`, `FIXME` o `HACK` en todo el repositorio; dos `# pragma: no cover`, los dos con su motivo escrito al lado. Los READMEs de módulo se han repasado contra el código de esta fase.

## Limitaciones conocidas (no son fallos, son decisiones)

- **Los textos guardados en la base no se traducen.** El nombre de la rutina ("Torso / pierna · 4 días"), los de los días ("Torso A"), los de las comidas ("Desayuno") y la explicación congelada de cada versión del plan se escriben al generar y se muestran igual en los dos idiomas. Los avisos del motor sí se vuelven a pintar traducidos, porque se guardan como código + parámetros. Arreglarlo del todo es guardar también esos como códigos.
- **La exportación se genera en la petición.** Con años de datos habrá que hacerla en segundo plano; hoy el ZIP tarda 0,3 s con 100.000 series.
- **SQLite en desarrollo.** Las medidas de rendimiento son con SQLite en un portátil; en Postgres las consultas cuentan igual pero cada una cuesta una ida y vuelta más, que es justo por lo que se han contado.
- **No hay bloqueo optimista.** Dos pestañas de la misma persona pueden pisarse el diario del mismo día (gana la última). La restricción única evita duplicados, no carreras.

## Qué mirar si algo se tuerce

| Síntoma | Dónde mirar |
|---|---|
| Una página tarda | `tests/integration/test_audit_performance.py`: sube los datos y cuenta consultas |
| Un aviso sale raro o con un código dentro | `app/labels.py`, `note_params()` y `NOTE_PARAM_LABELS` |
| El plan propone algo inseguro | `app/engine/safety.py` (límites) y `adjustment/rules.py` (`_reduce_or_steps`) |
| Un test de aislamiento pasa sospechosamente rápido | `tests/conftest.py`, `FreshClient`: sin él, las peticiones comparten `g` |
