# Traducciones — catálogo en inglés

Fecha: 2026-09-09. Estado: **cerrada**. No es una fase del prompt maestro: es el trabajo aparte que D-05 dejó para el final, hecho antes de la auditoría (Fase 13).

## Qué se ha hecho

- **Extractor propio para el motor** (`scripts/babel_engine.py`). Los textos del motor viven en un diccionario (`app/engine/messages.py`) para no meter Flask ahí dentro, y `pybabel` solo encuentra llamadas a `_()`. El extractor recorre el módulo con `ast` y suelta cada valor de `TEMPLATES` con su código como comentario. Declarado en `babel.cfg`, donde **el orden importa**: gana el primer patrón que encaja, así que el bloque del motor va antes que `[python: app/**.py]`.
- **Traductor enchufable en el motor**: `messages.translator` es una función que la factory sustituye por `app.i18n.translate_engine_message`. Fuera de una petición (scripts, tests del motor, logs) devuelve el castellano de referencia, que es lo que esos sitios esperan.
- **Idioma de la cuenta**: la selección es `?lang=` (se recuerda en la sesión) → sesión → idioma de la cuenta → `Accept-Language` → castellano. Lo que la persona eligió en `/cuenta` manda sobre lo que diga el navegador.
- **Los planes guardados se vuelven a pintar traducidos**: `details["all_notes"]` guarda cada aviso como `código` + `parámetros`, y `plans.messages_of()` los renderiza en el idioma de la petición. Un plan generado en castellano se lee en inglés sin regenerarlo; si la fila es antigua o está mal formada, se cae al texto congelado en `details["messages"]`.
- **El PDF y el LEEME del ZIP, traducidos** (`services/exports.py`): títulos, tablas, párrafos de fórmulas y el aviso legal de todas las páginas. La primera frase del resumen calórico reutiliza a propósito el mismo mensaje que el motor ("Déficit del X % sobre el gasto"), así que dice lo mismo en los dos sitios y se traduce una sola vez.
- **Nombres del catálogo en el idioma de quien lee**: las semillas ya traían `name_es` y `name_en` para los 190 ejercicios y para el material, pero nadie usaba el inglés. `Exercise.display_name` y `Equipment.display_name` (vía `labels.catalogue_name`) eligen según el idioma de la petición, con el castellano como respaldo.
- **Catálogo**: 802 mensajes, todos traducidos, ninguno dudoso. `.po` y `.mo` versionados.

## Qué se ha probado

| Prueba | Cómo | Resultado |
|---|---|---|
| Integridad del catálogo | `tests/unit/test_catalogue.py`: nada sin traducir, nada marcado como dudoso, los marcadores del original sobreviven en la traducción (los checkers de Babel) y el `.mo` está compilado al día | 4 tests |
| Interfaz e idioma | `tests/integration/test_i18n.py`: `?lang=`, sesión, cuenta y `Accept-Language`; portada, panel, nutrición y entrenamiento en inglés; los avisos del motor en el idioma de la petición y en castellano fuera de la aplicación; un plan generado en castellano leído en inglés | 13 tests |
| Exportaciones | El PDF descargado con `?lang=en` se abre con pypdf y no queda castellano de interfaz; el LEEME del ZIP se traduce y las columnas del CSV siguen en castellano | 2 tests |
| Suite completa | `pytest` | 573 passed |
| Linter y formato | `ruff check .`, `ruff format --check .` | limpios |
| Servidor real | Alta → cuestionario → `/panel`, `/nutricion`, `/entrenamiento`, `/diario`, `/revision` y `/cuenta` con `?lang=en`: todas en inglés, sin restos de castellano de interfaz | OK |
| **El PDF leído de verdad** | `GET /cuenta/plan.pdf?lang=en` contra el servidor y texto extraído página a página | 4 páginas en inglés, incluidos los nombres de los ejercicios |

## Errores aparecidos y cómo se corrigieron

1. **`pybabel compile` se negaba: cinco errores de marcadores incompatibles.** Babel marca como `python-format` cualquier msgid donde un `%` va seguido de espacio y letra de conversión: en "Déficit del {pct} % sobre el gasto", el `% s` de "% sobre" parece un `%s`. El motor usaba llaves y el resto de la app `%(nombre)s`, y un catálogo mixto no compila. Quitar la marca del `.po` no sirve de nada: Babel la vuelve a poner al leerlo. **Se unificó todo en printf con nombre**: las 80 plantillas del motor pasaron a `%(nombre)s` con `%%` para el porcentaje literal, y `render()` formatea con `%`. El texto renderizado es idéntico, el catálogo compila sin errores y ahora el validador de Babel comprueba de verdad que cada traducción conserva sus marcadores.
2. **El PDF salía a medias en inglés.** Las etiquetas de enums venían de `app/labels.py` (traducidas) pero los títulos, las tablas y el aviso legal eran literales sueltos: "Objetivo diario" junto a "Estimated from measurements". No lo detectó ningún test: apareció al generar el PDF contra el servidor y leerlo. Los textos del PDF y del LEEME están ahora marcados, con frases completas y marcadores con nombre en vez de trozos concatenados.
3. **Las pruebas de idioma se contagiaban entre peticiones.** Flask-Babel cachea el idioma en `g`, que vive en el contexto de aplicación; el fixture de base de datos mantiene uno abierto durante todo el test y las peticiones lo reutilizan, así que todas hablaban el idioma de la primera. No es un fallo de la app (en producción cada petición trae su contexto): las pruebas llaman a `refresh()` entre peticiones, con el porqué escrito al lado.
4. **La cabecera del `.po` volvía a salir con `PROJECT VERSION` y `FULL NAME`** por más que se editara el fichero: `write_po` la regenera desde el catálogo. Se pone en el objeto `Catalog` antes de escribir.

## Decisiones

- **Las columnas de los CSV se quedan en castellano.** Son identificadores de un volcado de datos: si cambiaran con el idioma, un fichero exportado hoy no encajaría con el de mañana. El LEEME lo dice.
- **Los nombres generados y guardados en la base se muestran tal cual**: la rutina ("Torso / pierna · 4 días"), los días ("Torso A") y las comidas ("Desayuno"). Son datos escritos al crear el plan, no interfaz, y se ven igual en la web y en el PDF.
- **Solo inglés, por ahora.** Añadir otro idioma es un catálogo más y una entrada en `LANGUAGES`; no hace falta tocar código.

## Limitaciones conocidas

- Los avisos del motor cuelan códigos internos en el texto: "Split upper_lower de 4 días", "Volumen extra (+27 %) para glutes, shoulders". Se ve igual en castellano y en inglés. Corregirlo es trabajo de la Fase 13.
- No hay selector de idioma visible: se cambia en `/cuenta` o con `?lang=en`. Con dos idiomas y la cuenta decidiendo, añadir un botón más a la barra no compensaba.
- Las instrucciones de los ejercicios siguen saliendo en inglés en los dos idiomas (`instructions_es` está vacío desde la Fase 3) y la interfaz lo marca.

## Criterio de cierre

Catálogo completo y compilado sin errores, app paseada en inglés contra el servidor y PDF descargado y leído. Cumplido.
