# Créditos y licencias de recursos

Todo recurso externo incluido en el proyecto se lista aquí con su origen y licencia. Nada se carga en caliente desde terceros: los ficheros viven en el repositorio.

## Datos y imágenes de ejercicios

| Recurso | Origen | Licencia | Uso en Alza |
|---|---|---|---|
| Dataset de ejercicios (nombres en inglés, instrucciones, músculos, mecánica, nivel) | [free-exercise-db](https://github.com/yuhonas/free-exercise-db) de yuhonas (a su vez derivado de `wrkout/exercises.json`) | [The Unlicense](https://unlicense.org/) (dominio público) | Base de `app/seeds/exercises.json`. La selección, los nombres en español, el patrón de movimiento, el equipamiento con nuestros códigos, las contraindicaciones y las alternativas son elaboración propia (`scripts/exercise_catalogue.py`). |
| Ilustraciones de ejercicios (2 por ejercicio, posición inicial y final) | Mismo repositorio, carpeta `exercises/<id>/` | The Unlicense | Descargadas por `scripts/build_exercises.py`, reducidas a 560 px de ancho (calidad JPEG 75) y guardadas en `app/static/img/exercises/<slug>/0.jpg` y `1.jpg`. |

| Pasos en castellano de los 190 ejercicios | Elaboración propia a partir de las instrucciones de free-exercise-db | The Unlicense (el original); los pasos son nuestros | `scripts/exercise_instructions_es.json`, copiados a `exercises.json` por `scripts/build_exercises.py`. |
| Vídeos de 32 ejercicios | [wger](https://wger.de), grabados por Goulart | [CC-BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | Descargados y convertidos a H.264 640x360 sin sonido por `scripts/build_videos.py` (obra derivada, misma licencia). Autoría, licencia y enlace al original en `app/static/video/exercises/CREDITS.json` y debajo de cada vídeo en la ficha del ejercicio. |

Los ejercicios sin vídeo se muestran con sus dos fotos alternándose.

## Alimentos

| Recurso | Origen | Licencia | Uso en Alza |
|---|---|---|---|
| Productos con sus valores nutricionales | [Open Food Facts](https://world.openfoodfacts.org), consultado en caliente (`search.openfoodfacts.org` y la API de productos) | Base de datos: [ODbL](https://opendatacommons.org/licenses/odbl/1-0/); contenidos: [DbCL](https://opendatacommons.org/licenses/dbcl/1-0/) | Buscador y código de barras del diario. Solo se envía lo buscado o el código; se guarda una copia de los valores del producto que la persona apunta. La página de resultados lo atribuye. |
| Tabla básica de 80 alimentos | Elaboración propia con valores medios de referencia (BEDCA, USDA FoodData Central) | Propia | `app/seeds/basic_foods.json`: buscador sin red y menú de la semana. Un test comprueba que las kcal cuadran con proteína, hidratos y grasa. | El emparejamiento con wger es a mano: solo cuando el vídeo es exactamente nuestro ejercicio.

## Librerías JavaScript vendorizadas

| Recurso | Origen | Licencia | Uso en Alza |
|---|---|---|---|
| Alpine.js 3.17.2 (`app/static/vendor/alpine-3.17.2.min.js`) | [alpinejs/alpine](https://github.com/alpinejs/alpine), build `dist/cdn.min.js` del paquete npm `alpinejs@3.17.2` | MIT (`app/static/vendor/LICENSE-alpinejs.txt`) | Interacciones pequeñas sin build: alternar la ilustración inicial/final de cada ejercicio. Requiere `'unsafe-eval'` en la CSP (T-06). |
| Chart.js 4.5.1 (`app/static/vendor/chart-4.5.1.umd.js`) | [chartjs/Chart.js](https://github.com/chartjs/Chart.js), build `dist/chart.umd.js` del paquete npm `chart.js@4.5.1` | MIT (`app/static/vendor/LICENSE-chartjs.txt`) | Gráficas del panel y del plan (peso con media móvil, reparto de macros, componentes del gasto). Se carga solo en las páginas que la usan. |

| ZXing para navegador 0.2.1 (`app/static/vendor/zxing-browser-0.2.1.min.js`) | [zxing-js/browser](https://github.com/zxing-js/browser), build `umd/zxing-browser.min.js` del paquete npm `@zxing/browser@0.2.1` (incluye `@zxing/library`) | MIT (`app/static/vendor/LICENSE-zxing-browser.txt`) | Leer códigos de barras con la cámara donde el navegador no trae lector propio (Safari en iPhone, escritorio). Se descarga solo al pulsar «Escanear». Descargada el 2026-11-12. |

Alpine y Chart.js se descargaron de jsDelivr el 2026-09-09 y se sirven desde el propio servidor (`/static/vendor/`); nada se carga de terceros en caliente.

## Tipografías

| Recurso | Origen | Licencia | Uso en Alza |
|---|---|---|---|
| Barlow Condensed 600 y 700 | [Barlow](https://github.com/jpt/barlow) de Jeremy Tribby, vía Google Fonts | SIL Open Font License 1.1 (`app/static/fonts/LICENSE-barlow.txt`) | Titulares, cifras grandes y temporizador. Subconjuntos latin y latin-ext en woff2. |
| Inter variable 400-700 | [Inter](https://github.com/rsms/inter) de Rasmus Andersson, vía Google Fonts | SIL Open Font License 1.1 (`app/static/fonts/LICENSE-inter.txt`) | Cuerpo, formularios y tablas. Subconjuntos latin y latin-ext en woff2. |

Descargadas el 2026-09-09 desde `fonts.googleapis.com` y servidas desde `app/static/fonts/` con reglas `@font-face` propias (`app/static/css/fonts.css`). En caliente no se pide nada a Google.

## Iconos

| Recurso | Origen | Licencia | Uso en Alza |
|---|---|---|---|
| Lucide 1.43.0, 29 iconos | [lucide-icons/lucide](https://github.com/lucide-icons/lucide), paquete `lucide-static` | ISC (`app/static/img/LICENSE-lucide.txt`) | Navegación, títulos de tarjeta, estados vacíos, avisos y acciones de la sesión. Sprite generado por `scripts/build_icons.py` e incrustado por `base.html`. |

Es el único set de iconos del proyecto: no se mezcla con otros.

## Fotografía

No se ha añadido fotografía de stock. Elegir una foto de Unsplash o Pexels y atribuirla como piden sus licencias exige una clave de API que este proyecto no tiene, y no se incluye ninguna imagen cuya licencia no se pueda documentar aquí. La portada y los estados vacíos usan las ilustraciones del catálogo (dominio público) y composición tipográfica.

## Pendiente de añadir en fases posteriores

- Nada por ahora.
