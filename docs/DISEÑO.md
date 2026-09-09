# Diseño de Forja

Qué se ha decidido, por qué, y de dónde sale. Los tokens viven en `app/static/css/app.css` y los contrastes los comprueba `tests/unit/test_design_tokens.py`: si alguien oscurece un color por debajo de AA, la suite falla.

## Punto de partida: para quién y dónde

Se usa **de pie, en el gimnasio, con el móvil en una mano y poca luz**, y en casa para mirar el plan con calma. De ahí salen tres reglas que mandan sobre lo demás:

1. Tema oscuro por defecto, claro disponible desde la cabecera.
2. Registrar una serie no puede costar más de un vistazo y un toque: campos grandes, valores pre-rellenados con lo de la última vez y un solo botón por serie.
3. Los números se leen antes que las palabras: cifras grandes, tabulares, y el texto explicativo debajo.

## Referencias

Qué se ha mirado y qué se ha cogido de cada una. Lo que no aparece aquí es propio.

| Referencia | Qué hace bien | Qué se ha adoptado en Forja |
|---|---|---|
| **MacroFactor** | Gasto energético estimado a partir de datos reales, con la confianza a la vista | La gráfica de peso con los pesajes en gris y la media móvil encima en color, y enseñar el gasto observado junto al teórico en la revisión |
| **Hevy** | La pantalla de registro de series, la mejor del sector | La fila por serie (kg, reps, RIR, botón de confirmar) y el "Última vez: 80 kg × 8, 8" encima de los campos |
| **Strong** | El temporizador de descanso que aparece solo al cerrar una serie | La barra pegada abajo con el tiempo restante, +30 s y "Listo", que además avisa con vibración al llegar a cero |
| **Fitbod** | Tarjetas de ejercicio con ilustración y alternativas a mano | La página del día: ilustración de inicio y final, prescripción en cuadrícula y las alternativas viables plegadas |
| **Cronometer** | Densidad de datos sin ruido | Tablas compactas con cifras tabulares para comidas, macros y volumen |
| **Whoop** | Interfaz oscura con un solo acento y una cifra protagonista por tarjeta | La paleta oscura con el naranja como único acento y el patrón "una cifra grande + una línea de contexto" en cada tarjeta del panel |
| **RP Hypertrophy** | Volumen semanal por músculo contra su rango recomendado | La tabla de volumen con el estado (en rango / por debajo / por encima) y la marca de músculo prioritario |
| **Caliber** | Explica el porqué de cada número en vez de soltarlo | La sección "Cómo lo calculamos" de la página de nutrición y las notas del motor en cada plan |

De ninguna se ha copiado la interfaz: se han adoptado patrones que ya son convenciones del sector, porque una persona que viene de Hevy o de MacroFactor no debería tener que aprender de nuevo dónde se toca.

## Paleta

Elegida entre tres propuestas (naranja sobre carbón, cian sobre pizarra, lima sobre negro). La elegida es **A "Forja"**: encaja con el nombre (hierro y fuego) y se separa del azul con el que se parecen entre sí casi todas las apps de fitness.

| Token | Oscuro | Claro | Para qué |
|---|---|---|---|
| `--bg` | `#0E1013` | `#F6F6F8` | Fondo de la página |
| `--bg-elevated` | `#171A20` | `#FFFFFF` | Tarjetas y cabecera |
| `--border` | `#2B313D` | `#D7DAE2` | Separadores (decorativos) |
| `--border-strong` | `#626B7D` | `#7B818E` | Borde de campos y botones |
| `--text` | `#E9ECF2` | `#15171C` | Texto |
| `--text-muted` | `#A3ADC0` | `#5A6170` | Texto secundario |
| `--accent` | `#FF8A34` | `#B34B00` | Acción principal, cifras destacadas |
| `--accent-contrast` | `#14100A` | `#FFFFFF` | Texto sobre el acento |
| `--success` | `#4DD39B` | `#0F7A4D` | En rango, marca personal |
| `--warning` | `#F7CF5C` | `#8A5A00` | Avisos del motor |
| `--danger` | `#FF7080` | `#B3242F` | Errores y bloqueos |
| `--focus` | `#8CC9FF` | `#1A5FC0` | Anillo de foco |

Reglas de uso:

- **Un solo acento.** El naranja es para lo que se toca y para la cifra protagonista. Si todo destaca, no destaca nada.
- **El color nunca lleva la información solo.** El estado del volumen dice "en rango" además de ir en verde; los avisos llevan icono además de color.
- **Contraste comprobado.** Ningún par de texto baja de 4.5:1 y los bordes de los controles llegan a 3:1 (WCAG 2.1, criterio 1.4.11), en los dos temas.

El tema se guarda en la sesión y se cambia con un formulario, sin JavaScript: así no hay parpadeo al cargar ni depende de que un script llegue.

## Tipografía

- **Barlow Condensed** (600 y 700) para titulares, cifras grandes y el temporizador. Condensada: en un móvil de 320 px "Día 3 · Torso B" cabe en una línea.
- **Inter** (variable 400-700) para el cuerpo, los formularios y las tablas. Es la más legible a tamaño pequeño y trae cifras tabulares.
- Escala fluida con `clamp()`: los titulares crecen con la ventana sin saltos.
- `font-variant-numeric: tabular-nums` en tablas, estadísticas y campos numéricos, para que las columnas de números no bailen.
- Las dos son de Google Fonts con licencia OFL y **están descargadas al repositorio** (`app/static/fonts/`, 216 KB en total, subconjuntos latin y latin-ext). No se pide nada a `fonts.googleapis.com` en caliente: es una dependencia menos y un rastreador menos.

## Iconografía

**Lucide** (licencia ISC), un único set, sin mezclar. Solo los 28 iconos que se usan, en un sprite generado por `scripts/build_icons.py` e incrustado en la página por `base.html`.

- Se incrusta en vez de enlazarse porque un `<use href="fichero.svg#id">` que falle deja el botón vacío, y porque ahorra una petición.
- El trazo (`fill: none; stroke: currentColor`) va en la clase `.icon`: al instanciar un `<symbol>`, los atributos de presentación se heredan del `<svg>` que lo referencia, no del sprite.
- Los iconos son **decorativos por defecto** (`aria-hidden`), porque el texto de al lado ya lo dice. Solo llevan nombre accesible los que van solos: el cambio de tema, el guardar y el borrar una serie.
- En pantallas de menos de 34 rem la navegación se queda con los iconos y el texto pasa a ser accesible pero invisible: seis destinos caben en una fila de 320 px.

## Imágenes

- **Ilustraciones de ejercicios**: las 380 del catálogo (`free-exercise-db`, dominio público), dos por ejercicio, posición inicial y final, que se alternan al tocar.
- **Portada**: una tira de tres de esas mismas ilustraciones, en blanco y negro y bajadas de opacidad, como textura.
- **No se ha añadido fotografía de stock.** Unsplash y Pexels necesitan una clave de API para elegir y atribuir bien una foto, y no la hay; meter una imagen sin poder documentar su licencia va en contra de `docs/CREDITOS.md`. Si quieres fotografía en la portada, pásame las imágenes o una clave y se añade con su atribución.

## Movimiento

Corto, con motivo y desactivable:

| Interacción | Qué hace | Duración |
|---|---|---|
| Botón pulsado | Se hunde 1 px y, al enviar, muestra un aro girando y deja de aceptar toques | 140 ms |
| Serie guardada | La fila recién registrada se enciende en naranja y se apaga | 900 ms |
| Tarjetas de resumen | Entran desplazándose 7 px, escalonadas | 260 ms |
| Temporizador de descanso | Aparece al guardar una serie; el número cambia cada segundo y se pone verde al acabar | — |

Dos reglas: **la animación nunca decide si algo se ve** (solo anima posición, jamás opacidad, para que un motor sin animaciones no esconda contenido) y todo se apaga con `prefers-reduced-motion: reduce`.

## Estados

- **Vacío**: icono, una frase que explica qué falta y el botón que lo resuelve. Nunca una pantalla en blanco.
- **Carga**: el botón pulsado gira y se bloquea; al volver atrás, el navegador restaura la página y el botón se desbloquea.
- **Error**: los de campo salen bajo el campo; los que no tienen campo (un día manipulado, una sesión cerrada) salen como aviso arriba, con icono.
- **Bloqueo por seguridad**: no es un error, es una explicación. La página dice qué respuesta lo impide y qué hacer.

## Puntos de rotura

| Ancho | Qué cambia |
|---|---|
| < 26 rem (416 px) | Los campos de serie se aprietan; las flechas de los números desaparecen |
| < 30 rem (480 px) | Tablas con menos relleno y letra algo menor |
| < 34 rem (544 px) | La navegación se queda en iconos; el texto sigue ahí para lectores de pantalla |
| < 40 rem (640 px) | Las rejillas de dos y tres columnas pasan a una; la tarjeta de ejercicio apila imagen y datos |
| ≥ 52 rem (832 px) | La portada pasa a dos columnas |
| ≥ 64 rem (1024 px) | El contenido deja de crecer y se centra |

Revisado a 320, 768 y 1440 px con capturas reales de la app, no con la herramienta de desarrollo.

## Accesibilidad

- Contraste AA en los dos temas, verificado por tests.
- Foco visible en todo lo que se puede enfocar (`outline` de 2 px con desplazamiento).
- Enlace de salto al contenido, `aria-current` en la navegación, `aria-label` en los iconos que van solos, `alt` en las ilustraciones y `role="status"` en los avisos.
- Objetivos táctiles de al menos 44 px de alto en botones y campos.
- Todo funciona sin JavaScript salvo las gráficas, el temporizador y el cronómetro; el registro de series, el cambio de tema y el cuestionario van con formularios normales.
