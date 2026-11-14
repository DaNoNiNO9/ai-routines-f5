# Auditoría de formularios y endpoints POST

Fecha: 14 de noviembre de 2026. Pruebas: `tests/integration/test_audit_forms.py`
(373 casos: 341 pasan y 32 son `xfail(strict=True)`, uno por cada caso de un bug abierto).

Por cada formulario o POST se ha probado: envío vacío y cada campo obligatorio ausente,
texto en campos numéricos, negativos, cero, números enormes, `nan`/`inf`, coma decimal,
espacios alrededor, límites exactos (aceptados) y justo fuera (rechazados), textos de
10 000 caracteres, HTML y cadenas con pinta de inyección SQL, opciones que no están en
la lista (también en otra capitalización), fechas imposibles, futuras y muy antiguas,
identificadores ajenos, inexistentes, no enteros y enormes, falta de token CSRF, doble
envío y GET contra rutas que solo admiten POST. En cada caso se comprueba que no hay
excepción (en pruebas se propagan, así que un 500 hace fallar el test), que se le
explica el error a la persona y que no se escribe nada si la entrada no era válida.

Cuando se arregle un bug, su test pasará a XPASS y fallará por `strict=True`: basta con
quitar la marca `xfail`.

## Cobertura

| Blueprint | Endpoint | Formulario / entrada | Qué se prueba | Resultado |
|---|---|---|---|---|
| todos | todas las rutas POST | — | GET → 405 en las 31 rutas solo-POST (46 rutas con POST en total) | correcto |
| todos | todas las rutas POST salvo el webhook | token CSRF | sin token → 400, con y sin sesión; no se escribe nada | correcto |
| auth | `POST /registro` | `RegisterForm` | vacío, cada campo ausente, email malo/largo, nombre de 1, solo espacios, 10 000, contraseñas distintas, 129 caracteres, débil; límites (nombre 80, contraseña 128); email repetido en mayúsculas; doble envío | correcto salvo BUG-5 |
| auth | `POST /entrar` | `LoginForm` | vacío, campos ausentes, 10 000 caracteres, contraseña errónea; `next` hacia fuera | correcto |
| auth | `POST /recuperar` | `ForgotPasswordForm` | vacío, email malo, 10 000 | correcto |
| auth | `POST /restablecer/<token>` | `ResetPasswordForm` | token falso o manipulado, contraseñas distintas, reutilizar el enlace | correcto |
| auth | `POST /salir` | — | GET → 405 | correcto |
| account | `POST /cuenta/perfil` | `ProfileForm` | nombre vacío/1/10 000, idioma fuera de lista o en mayúsculas, zona horaria inexistente/10 000/inyección; límites | correcto salvo BUG-5 |
| account | `POST /cuenta/correo` | `EmailForm` | vacío, email malo/largo, contraseña mala/10 000; el propio email en mayúsculas | correcto |
| account | `POST /cuenta/contrasena` | `PasswordForm` | vacío, actual mala, no coinciden, 129, débil | correcto |
| account | `POST /cuenta/borrar` | `DeleteAccountForm` | vacío, «borrar» en minúsculas, errata, contraseña mala o ausente | correcto |
| onboarding | `POST /cuestionario/paso/1..6` | `BodyForm` … `NutritionForm` | 66 entradas malas (rangos, opciones, fechas, NaN, inf, unidades, reglas cruzadas); límites, coma y espacios; 18 años exactos; fecha objetivo de mañana; pasos 0, 8, enorme y saltados | correcto salvo BUG-12 |
| onboarding | `POST /cuestionario/rapido` | `QuickForm` | vacíos, menor, NaN, días y lugar fuera de lista | correcto |
| onboarding | `POST /cuestionario/revisar` | — | doble envío | BUG-10 |
| tracking | `POST /diario/peso` | `WeightForm` | día vacío/imposible/formato español/texto/futuro; peso vacío, texto, fuera de rango, negativo, cero, NaN, inf, «1.234,5»; nota de 201; límites y coma; doble envío | correcto salvo BUG-6 y BUG-7 |
| tracking | `POST /diario/ingesta` | `IntakeForm` | kcal vacías, texto, decimales, negativas, enormes; macros fuera de rango y NaN; adherencia 101; límites; doble envío | correcto salvo BUG-6 |
| tracking | `POST /diario/actividad` | `ActivityForm` | pasos negativos/enormes/«8.000»; cardio fuera de lista o en mayúsculas; minutos sin tipo y tipo sin minutos; límites | correcto salvo BUG-6 |
| tracking | `POST /diario/perimetros` | `MeasurementForm` | sin medidas, día vacío/imposible, cada medida fuera de rango, NaN, inf, grasa sin método, método fuera de lista, nota 201; doble envío; notas con HTML | correcto salvo BUG-6 |
| tracking | `POST /diario/alimentos` | `request.form` | gramos vacíos, texto, 0, negativos, >5000, NaN, inf, 1e400; origen inventado, alimento inexistente, código con HTML o inyección; límites; fecha mala o futura | correcto |
| tracking | `POST /diario/alimentos/<id>/borrar` | id en URL | inexistente, 0, enorme (el ajeno ya lo cubre `test_food.py`) | BUG-1 |
| tracking | `POST /diario/alimentos/copiar` | `request.form` | ayer vacío, fecha basura, doble envío | BUG-3 |
| nutrition | `POST /nutricion/menu/apuntar` | `request.form` | comida vacía, texto, 0, 99, negativa, enorme, decimal; doble envío | BUG-4 |
| workouts | `POST /entreno/empezar/<día>` | id en URL | día 0 y 99 | correcto |
| workouts | `POST /entreno/<id>/serie` | `SetForm` | 24 entradas malas (ids, índice, peso, reps, RIR, tipo); límites; serie más allá de lo prescrito; ejercicio de otro día, 0, negativo, inexistente; doble envío | correcto salvo BUG-1 y BUG-2 |
| workouts | `POST /entreno/<id>/sustituir` | `SubstituteForm` | id texto, decimal, ausente; ejercicio que no es alternativa; ejercicio inexistente; ids enormes | BUG-1, BUG-2, BUG-11 |
| workouts | `POST /entreno/<id>/estado` | `request.form` | respuesta vacía, en mayúsculas, inventada, HTML | correcto (400) |
| workouts | `POST /entreno/<id>/terminar` | `FinishForm` | fatiga 0, 6, texto, decimal; notas 501; límites y notas con HTML | correcto |
| workouts | `GET/POST /entreno/<id>/…` | id en URL | id enorme en las siete rutas | BUG-1 |
| training | `POST /entrenamiento/dia/<n>/cambiar` | `request.form` | id vacío, texto, 0, de otro día, enorme, decimal; día inexistente | correcto (404) |
| training | `POST /entrenamiento/permitir` | `request.form` | slug vacío, inexistente, HTML, inyección, 10 000 | correcto |
| main | `POST /tema`, `POST /idioma` | `request.form` | idioma vacío, inventado, en mayúsculas, `en-GB`, HTML, 10 000; `next` externo, `//`, `javascript:`, sin barra, con barra invertida, tabulador o salto de línea | correcto |
| privacy | `POST /consentimiento` | `request.form` | casilla vacía, «n», «Y», «on», «yes» | correcto |
| privacy | `POST /cuenta/consentimiento/retirar` | `request.form` | contraseña vacía, mala, 10 000 | correcto |
| imports | `POST /cuenta/importar/hevy` | fichero | sin fichero, vacío, binario, otro CSV, solo cabecera; nombres con HTML; valores raros (peso negativo o texto, 500 reps, RPE 15); NaN e inf | correcto salvo BUG-8 |
| imports | `POST /cuenta/importar/hevy/confirmar` | `request.form` | token vacío, con `../`, largo, corto; doble confirmación; valores fuera de las CHECK | correcto salvo BUG-9 |
| billing | `POST /suscripcion/empezar` | `request.form` | plan vacío, inventado, en mayúsculas, HTML, 10 000 | correcto |
| billing | `POST /suscripcion/cancelar`, `reanudar`, `desistir`, `gestionar` | — | sin suscripción | correcto |
| billing | `POST /suscripcion/webhook` | cuerpo | vacío, basura, JSON sin firma válida | correcto (400) |
| billing | `POST /suscripcion/simulada/pago/<token>` | token en URL | tokens falsificados | correcto |
| review | `POST /revision/aplicar` | — | sin plan, con campos de más | correcto |

## Bugs

### BUG-1 — Un id enorme en la URL da un 500

- **Endpoints:** todas las rutas `/entreno/<session_id>…` (GET de la sesión y del resumen, y los POST
  `serie`, `estado`, `sustituir`, `terminar`, `abandonar`) y `POST /diario/alimentos/<entry_id>/borrar`.
- **Entrada:** `/entreno/99999999999999999999` (cualquier entero que no quepa en el INTEGER de la base).
- **Ahora:** el conversor `<int:>` de Flask acepta el número, la consulta lo pasa a SQLite y salta
  `OverflowError: Python int too large to convert to SQLite INTEGER` → 500. En PostgreSQL el umbral es
  mucho más bajo (cualquier id > 2 147 483 647 en columnas `INTEGER`) y el error sería `DataError`.
- **Debería:** 404, igual que un id inexistente.
- **Severidad:** media (no expone datos, pero cualquiera con sesión provoca 500 a voluntad y llena el
  registro de errores).
- **Dónde:** `app/services/workouts.py:172` (`get_session`, llamado desde
  `app/blueprints/workouts/routes.py:39`) y `app/services/food.py:335` (`remove`, desde
  `app/blueprints/tracking/routes.py:305`). Arreglo natural: un conversor de URL con tope o una
  comprobación de rango antes de consultar.

### BUG-2 — Un id enorme en un campo oculto da un 500

- **Endpoints:** `POST /entreno/<id>/serie` y `POST /entreno/<id>/sustituir`.
- **Entrada:** `routine_exercise_id=99999999999999999999` o `exercise_id=99999999999999999999`.
- **Ahora:** `IntegerField` sin `NumberRange` lo acepta y `db.session.get(...)` desborda → 500.
- **Debería:** formulario inválido («Petición no válida») o 404, sin escribir nada.
- **Severidad:** media.
- **Dónde:** `app/blueprints/workouts/forms.py:25`, `:42` y `:43` (falta `NumberRange(min=1, max=2**31-1)`);
  la consulta que explota está en `app/blueprints/workouts/routes.py:51` y `:193`.

### BUG-3 — «Copiar ayer» enviado dos veces duplica la comida

- **Endpoint:** `POST /diario/alimentos/copiar`.
- **Entrada:** dos envíos seguidos (doble clic o reenviar el formulario) con alimentos apuntados ayer.
- **Ahora:** cada envío copia otra vez todo lo de ayer; las kcal del día se duplican y la revisión
  quincenal trabaja con una ingesta falsa.
- **Debería:** no copiar si el día de destino ya tiene alimentos (la pantalla solo ofrece el botón
  cuando hoy está vacío, pero el servidor no lo comprueba).
- **Severidad:** media.
- **Dónde:** `app/blueprints/tracking/routes.py:318` y `app/services/food.py:345` (`copy_day`).

### BUG-4 — Apuntar dos veces la misma comida del menú la duplica

- **Endpoint:** `POST /nutricion/menu/apuntar`.
- **Entrada:** `comida=1` enviado dos veces.
- **Ahora:** se añaden otra vez todos los alimentos del plato (4 → 8 filas en la prueba).
- **Debería:** no duplicar un plato del menú ya apuntado ese día (o avisar).
- **Severidad:** baja. Puede discutirse como decisión de diseño (alguien podría repetir plato), pero
  un doble clic es mucho más probable y no hay aviso.
- **Dónde:** `app/blueprints/nutrition/routes.py:138` y `app/services/menu.py:126` (`log_plate`).

### BUG-5 — El nombre se valida antes de recortar los espacios

- **Endpoints:** `POST /registro` y `POST /cuenta/perfil`.
- **Entrada:** `display_name="  B  "`.
- **Ahora:** `Length(min=2)` ve 5 caracteres y lo da por bueno; después se guarda `"B"` (1 carácter),
  por debajo del mínimo que el propio formulario exige.
- **Debería:** recortar antes de validar (filtro `strip` en el campo) y rechazar.
- **Severidad:** baja.
- **Dónde:** `app/blueprints/auth/forms.py:22` y `app/blueprints/account/forms.py:36` (sin
  `filters=[str.strip]`); el recorte tardío está en `app/services/auth.py:124` y
  `app/blueprints/account/routes.py:67`.

### BUG-6 — El diario acepta días de hace más de un siglo

- **Endpoints:** `POST /diario/peso`, `/diario/ingesta`, `/diario/actividad`, `/diario/perimetros`.
- **Entrada:** `day=1900-01-01`.
- **Ahora:** se guarda sin rechistar (solo se comprueba que no sea futuro).
- **Debería:** rechazar días anteriores a una fecha razonable (la fecha de nacimiento, la de alta o,
  como mínimo, un tope fijo).
- **Severidad:** baja (solo con una petición manipulada: el día va en un campo oculto o en un
  selector de fecha), pero ensucia historial, gráficas y exportaciones.
- **Dónde:** `app/blueprints/tracking/forms.py:32` y `:122` (`validate_day`).

### BUG-7 — Los números aceptan la sintaxis de Python

- **Endpoints:** todos los que usan `app.fields.DecimalField` (diario, cuestionario, series).
- **Entrada:** `weight_kg=6_4` o `1_00`.
- **Ahora:** `float()` acepta los guiones bajos y se guarda 64 o 100.
- **Debería:** «Escribe un número, por ejemplo 63,5.»
- **Severidad:** baja (nadie lo teclea a propósito, pero un error de dedo se guarda como otro número).
  También se aceptan `1e2` (=100), que el rango acota.
- **Dónde:** `app/fields.py:30`.

### BUG-8 — NaN o infinito en el CSV de Hevy da un 500 al subirlo

- **Endpoint:** `POST /cuenta/importar/hevy`.
- **Entrada:** una fila con `reps` o `rpe` igual a `nan` o `inf`.
- **Ahora:** `_number` devuelve `float('nan')`/`inf`, que pasan los filtros (`not reps` y `reps < 1`
  son falsos con NaN) y `int(reps)` o `round(10 - rpe)` lanzan `ValueError`/`OverflowError` → 500.
- **Debería:** tratar la fila como no válida (o el fichero como corrupto) con un mensaje.
- **Severidad:** media (un fichero editado o corrupto tumba la petición; una exportación real de Hevy
  no debería traerlo).
- **Dónde:** `app/services/hevy.py:291` (`_number` no descarta NaN ni infinitos) y las líneas `:345`,
  `:361` y `:362`.

### BUG-9 — Valores del CSV fuera de las restricciones de la base dan un 500 al confirmar

- **Endpoint:** `POST /cuenta/importar/hevy/confirmar`.
- **Entrada:** peso de 5000 kg, peso `nan`, `set_index` negativo, o una hora de fin anterior a la de inicio.
- **Ahora:** la vista previa sale bien, pero al confirmar `import_history` choca con las CHECK
  (`weight_range`, `set_index_positive`, `finish_after`, `NOT NULL`) → `IntegrityError` → 500.
- **Debería:** acotar o descartar esas series (como ya hace con las reps > 100 y los pesos negativos)
  y explicarlo en el resumen.
- **Severidad:** media (la hora de fin anterior al inicio es posible en exportaciones reales, por
  ejemplo con cambios de hora o entrenos editados).
- **Dónde:** `app/services/hevy.py:341` (fin sin comprobar), `:348`/`:360` (peso sin tope ni NaN),
  `:356` (índice sin mínimo); el fallo salta en el `commit` de `:453`.

### BUG-10 — Pulsar dos veces «Generar plan» crea otra versión de perfil y de plan

- **Endpoint:** `POST /cuestionario/revisar`.
- **Entrada:** dos envíos seguidos al terminar el cuestionario.
- **Ahora:** el primero genera el perfil v1 y borra el borrador; el segundo crea un borrador nuevo
  ya rellenado desde el perfil (`start_draft`), lo da por completo y genera el perfil v2 y otra vez
  plan y rutina, idénticos.
- **Debería:** el segundo envío no debería regenerar nada (redirigir al resultado).
- **Severidad:** media (versiones duplicadas en el historial del plan; la prueba comprueba el
  perfil duplicado).
- **Dónde:** `app/blueprints/onboarding/routes.py:333` junto con `app/services/onboarding.py:120`
  (borrador prerrellenado con `step=LAST_STEP`).

### BUG-11 — Un ejercicio inexistente en la sustitución se toma como «restaurar el original»

- **Endpoint:** `POST /entreno/<id>/sustituir`.
- **Entrada:** `exercise_id=999999` (no existe) con una sustitución ya hecha.
- **Ahora:** `db.session.get` devuelve `None`, que el servicio interpreta como «quitar la
  sustitución»: se borra la que había y se muestra «Ejercicio original restaurado.» como éxito.
- **Debería:** «Ese ejercicio no es una alternativa válida para ti.» y no tocar nada. Solo un campo
  vacío debería restaurar.
- **Severidad:** baja (requiere manipular la petición).
- **Dónde:** `app/blueprints/workouts/routes.py:193`.

### BUG-12 — Una gravedad de lesión no válida se rechaza sin decir por qué

- **Endpoint:** `POST /cuestionario/paso/4`.
- **Entrada:** `injury_knee=extrema` (fuera de las opciones).
- **Ahora:** el formulario no valida, no se guarda nada (bien), pero la página vuelve sin ningún
  mensaje: los desplegables de lesiones no pintan sus errores.
- **Debería:** mostrar el error junto a la zona afectada.
- **Severidad:** baja (solo con una petición manipulada).
- **Dónde:** `app/templates/onboarding/step_equipment.html:82-93` (no hay bucle de
  `errors` para los campos `injury_*`).

## Observaciones que no son bugs (decisiones de diseño)

- `POST /diario/alimentos` y `/diario/alimentos/copiar` llevan a hoy una `fecha` mala o futura en vez
  de rechazarla (`_requested_day`). Nunca escribe en el futuro; queda documentado en un test que pasa.
- `POST /diario/alimentos/<id>/borrar` con un id inexistente o ajeno y `POST /entrenamiento/permitir`
  con un slug desconocido vuelven sin mensaje. No escriben nada; sería mejor avisar, pero no es un fallo.
- `IntakeForm.notes` y `ActivityForm.notes` existen pero el diario no los pinta: un error en ellos
  (por ejemplo, 10 000 caracteres) se rechaza sin explicación, pero no se puede provocar desde la
  interfaz. No se cuenta como bug; si algún día se muestran, habrá que pintar sus errores.
- Un email con espacios alrededor se rechaza como inválido en vez de recortarse; el navegador ya los
  quita en los campos `type=email`.
- Con varios valores en un campo de opción única, WTForms se queda con el primero; los `BooleanField`
  dan por marcada cualquier cadena salvo `""` y `"false"` (semántica estándar de HTML).
- `/entreno/<id>/estado`, `/nutricion/menu/apuntar` y `/entrenamiento/dia/<n>/cambiar` responden con
  la página genérica de 400/404 ante entradas manipuladas: no tienen formulario que se pueda rellenar
  mal desde la interfaz.
- Las redirecciones con `next` resisten `//`, esquemas, barra invertida (Werkzeug la codifica como
  `%5C`) y tabuladores o saltos de línea (`urlsplit` los quita y se usa la ruta por defecto).

## Lo que no se ha podido probar

- **PostgreSQL de producción.** Las pruebas usan SQLite en memoria. Allí BUG-1/BUG-2 saltan con ids
  mucho menores (> 2³¹−1) y un carácter NUL (`\x00`) en cualquier texto provocaría `DataError` en
  psycopg; en SQLite se guarda sin problema, así que no se puede reproducir aquí.
- **Webhook con firma real de Stripe:** el backend de pruebas es el simulado y rechaza cualquier
  webhook; la verificación de firma está en `test_stripe_gateway.py`.
- **Portal simulado con acciones inválidas** con una suscripción activa: ya lo cubre `test_billing.py`.
- **Límites de frecuencia** (`limiter`): están desactivados en pruebas.
- **Ficheros de más de 8 MB en la importación:** no se han generado para no alargar la suite;
  el corte está en `app/services/hevy.py:313`.
- **Rutas `/_debug/*`:** solo existen en desarrollo y pruebas.
