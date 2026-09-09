# Fase 11 — Diseño visual

Fecha: 2026-09-09. Estado: **cerrada**.

## Qué se ha hecho

- **Paleta y tipografía elegidas por el usuario** entre tres propuestas cada una, presentadas con componentes reales de la app y con los contrastes ya calculados: paleta "Forja" (naranja `#FF8A34` sobre carbón `#0E1013`) y Barlow Condensed + Inter (T-88, T-90).
- **Tipografías descargadas al repositorio** (`app/static/fonts/`, 216 KB, subconjuntos latin y latin-ext) con reglas `@font-face` propias. No se pide nada a `fonts.googleapis.com` en caliente.
- **Iconos de Lucide**, un único set, solo los 28 que se usan, en un sprite generado por `scripts/build_icons.py` e incrustado en la página (T-91). Macro `icon()` decorativa por defecto y con nombre accesible cuando el icono va solo.
- **Tokens de color** para los dos temas, con `--border-strong` para los bordes de campos y botones, que WCAG 2.1 pide a 3:1 por ser controles interactivos (T-89).
- **Tema claro** desde la cabecera, guardado en la sesión, sin JavaScript y sin parpadeo (T-92).
- **Escala tipográfica** fluida, titulares condensados y cifras tabulares en todo lo que va en columna.
- **Estados vacíos** con icono, frase y salida; **estado de carga** en el botón pulsado; errores de campo bajo el campo y los demás como aviso.
- **Micro-interacciones**: hundido del botón, resalte de la serie recién guardada, entrada escalonada de las tarjetas de resumen y aparición del temporizador. Solo mueven, nunca cambian la opacidad (T-93), y se apagan con `prefers-reduced-motion`.
- **Navegación de móvil** en iconos por debajo de 34 rem, con el texto accesible pero invisible (T-94).
- **Portada nueva** con la propuesta, tres tarjetas de qué hace y el aviso de límites.
- Documentación: `docs/DISEÑO.md` (referencias, paleta, tipografía, iconos, movimiento, estados, puntos de rotura y accesibilidad), `docs/CREDITOS.md` (fuentes e iconos con sus licencias), `docs/DECISIONES.md` T-88 a T-95, `app/README.md` y README raíz.

## Qué se ha probado

| Prueba | Cómo | Resultado |
|---|---|---|
| Contraste | `tests/unit/test_design_tokens.py` lee los tokens del CSS y calcula el contraste WCAG de 13 pares en los dos temas | 26 comprobaciones; ninguna baja de 4.5:1 en texto ni de 3:1 en controles |
| Tipografías | Test que comprueba que no hay ninguna `url()` remota, que las dos familias están y que cada fichero existe | OK |
| Iconos | Test que compara los iconos usados en las plantillas con los del sprite, y el sprite con su copia incrustada | OK |
| Tema | `tests/integration/test_plan_pages.py`: empieza oscuro, cambia a claro y vuelve; el `next` no admite destinos externos | 2 tests |
| Suite completa | `pytest --cov` | 543 passed |
| Linter y formato | `ruff check .`, `ruff format --check .` | limpios |
| Servidor real | Cuenta nueva, cuestionario, sesión con series, diario y revisión, con el servidor levantado | OK, sin errores nuevos en el log |
| 320 / 768 / 1440 px | Capturas con Edge headless (dentro de un iframe del ancho exacto) de portada, panel, sesión en vivo, diario, nutrición, entrenamiento y cuestionario, revisadas a mano | Sin desbordamiento horizontal en ninguna; ver los fallos corregidos |
| Tema claro | Captura del panel a 1440 px | Contraste correcto, acento `#B34B00` sobre blanco |

## Errores aparecidos y cómo se corrigieron

1. **Los iconos salían rellenos de negro.** Un `<symbol>` instanciado con `<use>` hereda los atributos de presentación del `<svg>` que lo referencia, no del documento del sprite, así que el `fill="none" stroke="currentColor"` del sprite no llegaba. El trazo pasó a la clase `.icon`.
2. **Los iconos no aparecían en absoluto** al revisar las capturas: el `<use href="fichero.svg#id">` externo no cruza orígenes. Además de ser un problema del método de captura, señalaba un riesgo real (un botón de solo icono se queda vacío si ese fichero falla), así que el sprite pasó a incrustarse en la página.
3. **Las tarjetas de estadísticas salían en blanco.** La animación de entrada partía de `opacity: 0` con `fill-mode: both`; si no llega a ejecutarse, el contenido no se ve. Las animaciones ya solo mueven.
4. **La navegación se partía en tres líneas encima de la marca** a 320 px con seis destinos: por debajo de 34 rem se queda en iconos.
5. **El campo de kilos cortaba el valor** ("8(" en vez de "80,0") a 320 px: las flechas de `input[type=number]` se comían el ancho. Quitadas, con relleno menor por debajo de 26 rem.
6. **El texto de ayuda se leía encima del botón** (ya corregido al final de la Fase 10, con el mismo método de capturas).
7. El borde de los campos, heredado de la Fase 1, daba 1,5:1 sobre el fondo: por debajo del 3:1 que pide WCAG para controles. De ahí sale `--border-strong`.

## Limitaciones conocidas

- Sin fotografía de stock: no hay clave de API para elegir y atribuir imágenes de Unsplash o Pexels como piden sus licencias (T-95). La portada usa las ilustraciones del catálogo, que sí son de dominio público.
- Las capturas de revisión salen de Edge headless, que clampa la ventana a 492 px: los anchos reales se consiguen metiendo la página en un `iframe` del tamaño exacto. No sustituye a probarlo en un teléfono de verdad.
- El contador de series sigue mostrando "3/2" cuando se hacen más de las prescritas. Es correcto y ya no molesta con el resto del diseño, pero se puede afinar.
- `instructions_es` sigue vacío: las instrucciones de los ejercicios se muestran en inglés, marcadas como tales.

## Pendiente

- Fase 12: exportación (PDF del plan, CSV de los datos), ajustes de cuenta y borrado RGPD.
- Fase 13: auditoría final (§7) y `docs/ESTADO_FINAL.md`.
- Catálogos de traducción con pybabel, como fase aparte al final.

## Criterio de cierre

Revisado a 320, 768 y 1440 px con capturas reales y contraste WCAG AA verificado por tests en los dos temas. Cumplido.
