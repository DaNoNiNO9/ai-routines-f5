# Créditos y licencias de recursos

Todo recurso externo incluido en el proyecto se lista aquí con su origen y licencia. Nada se carga en caliente desde terceros: los ficheros viven en el repositorio.

## Datos y imágenes de ejercicios

| Recurso | Origen | Licencia | Uso en Forja |
|---|---|---|---|
| Dataset de ejercicios (nombres en inglés, instrucciones, músculos, mecánica, nivel) | [free-exercise-db](https://github.com/yuhonas/free-exercise-db) de yuhonas (a su vez derivado de `wrkout/exercises.json`) | [The Unlicense](https://unlicense.org/) (dominio público) | Base de `app/seeds/exercises.json`. La selección, los nombres en español, el patrón de movimiento, el equipamiento con nuestros códigos, las contraindicaciones y las alternativas son elaboración propia (`scripts/exercise_catalogue.py`). |
| Ilustraciones de ejercicios (2 por ejercicio, posición inicial y final) | Mismo repositorio, carpeta `exercises/<id>/` | The Unlicense | Descargadas por `scripts/build_exercises.py`, reducidas a 560 px de ancho (calidad JPEG 75) y guardadas en `app/static/img/exercises/<slug>/0.jpg` y `1.jpg`. |

Los enlaces de vídeo (`video_url`) son búsquedas en YouTube con el nombre del ejercicio (decisión T-25); no se embebe ni se descarga contenido de terceros.

## Librerías JavaScript vendorizadas

| Recurso | Origen | Licencia | Uso en Forja |
|---|---|---|---|
| Alpine.js 3.17.2 (`app/static/vendor/alpine-3.17.2.min.js`) | [alpinejs/alpine](https://github.com/alpinejs/alpine), build `dist/cdn.min.js` del paquete npm `alpinejs@3.17.2` | MIT (`app/static/vendor/LICENSE-alpinejs.txt`) | Interacciones pequeñas sin build: alternar la ilustración inicial/final de cada ejercicio. Requiere `'unsafe-eval'` en la CSP (T-06). |
| Chart.js 4.5.1 (`app/static/vendor/chart-4.5.1.umd.js`) | [chartjs/Chart.js](https://github.com/chartjs/Chart.js), build `dist/chart.umd.js` del paquete npm `chart.js@4.5.1` | MIT (`app/static/vendor/LICENSE-chartjs.txt`) | Gráficas del panel y del plan (peso con media móvil, reparto de macros, componentes del gasto). Se carga solo en las páginas que la usan. |

Ambas se descargaron de jsDelivr el 2026-09-09 y se sirven desde el propio servidor (`/static/vendor/`); nada se carga de terceros en caliente.

## Pendiente de añadir en fases posteriores

- Tipografías de Google Fonts (Fase 11): licencia OFL, ficheros descargados a `app/static/fonts/`.
- Set de iconos (Fase 11): Lucide, Phosphor o Tabler, licencia MIT/ISC, vendorizado.
- Fotografía de landing y estados vacíos (Fase 11): Unsplash o Pexels, con autor y licencia por imagen.
