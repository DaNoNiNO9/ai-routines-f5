# Fase 12 — Exportación, ajustes de cuenta y borrado RGPD

Fecha: 2026-09-09. Estado: **cerrada**.

## Qué se ha hecho

- **PDF del plan** (`services/exports.py`, ReportLab elegido por el usuario, T-96): portada con el nombre y el objetivo, objetivo diario con macros, reparto por comidas, ciclado de carbohidratos, "cómo se ha calculado" con las fórmulas nombradas, avisos del motor y la rutina día a día con series, repeticiones, RIR y descansos. El aviso de herramienta orientativa va en **todas** las páginas (T-98). Si la seguridad bloqueó el plan, el PDF se genera igual y explica por qué (T-99).
- **Exportación de datos**: un ZIP con once CSV (cuenta, cuestionarios, pesajes, ingestas, actividad, perímetros, planes, ajustes, rutinas, sesiones y series) más un `LEEME.txt` que describe cada fichero. UTF-8 con BOM y fechas ISO (T-100).
- **Página de cuenta** (`/cuenta`): nombre, idioma y zona horaria (validada contra las zonas IANA reales); cambio de correo y de contraseña, los dos pidiendo la contraseña actual (T-102); las dos descargas; y el borrado con contraseña más la palabra BORRAR.
- **Borrado RGPD**: `auth.delete_account()` borra de verdad en cascada, no marca una bandera (T-103). Se cierra la sesión antes de borrar.
- **Servicio de auth ampliado**: `change_password()`, `change_email()` (con la carrera de correos duplicados cubierta) y `delete_account()`.
- Enlace a la cuenta en la navegación y estilos de la zona de peligro.

## Qué se ha probado

| Prueba | Cómo | Resultado |
|---|---|---|
| Exportación (servicio) | `tests/unit/services/test_exports_service.py`: el PDF abre con pypdf, tiene metadatos, el aviso en cada página, las cifras del plan y los nombres de los ejercicios; el PDF de un plan bloqueado explica el motivo; el ZIP tiene los once CSV con BOM y solo los datos de su dueño; una cuenta vacía también exporta; los nombres de fichero salen en ASCII | 7 tests |
| Cuenta (web) | `tests/integration/test_account.py`: acceso sin sesión, la página con sus cuatro secciones, cambios de perfil válidos e inválidos, cambio de correo (contraseña incorrecta, correo ocupado, correcto y el nuevo entra), cambio de contraseña (actual incorrecta, débil, no coinciden, correcta y la nueva entra), descargas con sus cabeceras, borrado con palabra o contraseña incorrectas, borrado completo y borrado que no toca a los demás | 13 tests |
| Suite completa | `pytest --cov` | 563 passed; cobertura de `app/` 98,2 % |
| Linter y formato | `ruff check .`, `ruff format --check .` | limpios |
| Servidor real | Cuenta nueva → cuestionario → diario → `GET /cuenta/plan.pdf` (9,4 KB, `Content-Type: application/pdf`, `Content-Disposition` con el nombre en ASCII) y `GET /cuenta/datos.zip` (3,4 KB, ZIP válido con 12 entradas) | OK |
| **El PDF abierto de verdad** | Renderizado a imagen con pypdfium2 y revisado a ojo, página a página | 4 páginas correctas: cabecera, tablas alineadas, rutina completa y aviso al pie de todas |

## Errores aparecidos y cómo se corrigieron

1. **El nombre del fichero rompía la cabecera.** `Content-Disposition` es ASCII: un usuario llamado "Ana Ríos" generaba una cabecera con un byte no ASCII (y con un nombre en otro alfabeto habría reventado). Ahora el nombre se normaliza y se queda en ASCII (T-101).
2. **El PDF imprimía los enums en crudo**: "objetivo: fat loss", "1392 kcal (katch_mcardle)", "26.1 % (navy)". Un documento que alguien enseña a su dietista no puede hablar en inglés de programador. Ahora usa las etiquetas de `app/labels.py`, y hay un test que falla si vuelve a colarse un valor de enum.
3. **Cabeceras de tabla desalineadas**: los valores iban a la derecha y los títulos a la izquierda. La alineación empieza ahora en la fila de cabecera.
4. **Paréntesis anidados** ("26.1 % (Estimado por perímetros (fórmula Navy))"): el método pasó a su propia fila.
5. **El visor de PDF de Edge headless sale en blanco**, así que no valía para revisarlo. Se añadió `pypdfium2` como dependencia **de desarrollo** para rasterizar el PDF y poder mirarlo de verdad.

## Limitaciones conocidas

- El PDF va en Helvetica, no en las tipografías de la app: ReportLab necesita TTF y las nuestras están en woff2 (T-97).
- El PDF no lleva las ilustraciones de los ejercicios: pesarían varios megas y el documento está pensado para imprimirse.
- La exportación se genera en memoria y en la propia petición. Con años de series podría tardar; a esa escala habría que generarla en segundo plano y enviarla por correo.
- Cambiar el correo no pide confirmar la dirección nueva: se marca como no verificada (`email_verified_at = None`), pero no hay verificación por correo todavía.
- El borrado es inmediato y sin periodo de gracia. Es lo que pide el artículo 17, pero conviene decirlo.

## Pendiente

- Fase 13: auditoría final (§7 del prompt) y `docs/ESTADO_FINAL.md`.
- Catálogos de traducción con pybabel, como fase aparte al final.

## Criterio de cierre

Exportaciones generadas y abiertas correctamente: el PDF descargado del servidor se ha rasterizado y revisado página a página, y el ZIP se ha abierto y leído. Cumplido.
