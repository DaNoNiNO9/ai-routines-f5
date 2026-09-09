"""Copy the icon sprite into the template that embeds it.

Run it after ``scripts/build_icons.py``::

    python scripts/build_icons.py && python scripts/inline_icons.py

The sprite lives twice on purpose: ``app/static/img/icons.svg`` is the source
of truth (and can be opened on its own), and the template is what every page
embeds. A test checks that both stay in step.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPRITE = ROOT / "app" / "static" / "img" / "icons.svg"
TEMPLATE = ROOT / "app" / "templates" / "components" / "sprite.html"
HEADER = """{# Sprite de iconos incrustado por base.html.
   Va dentro del documento (y no como fichero enlazado con <use href="...svg#id">)
   para ahorrar una petición y para que los iconos no dependan de que ese fichero
   cargue: un botón con solo icono se quedaría vacío. Se regenera con
   scripts/build_icons.py y se copia aquí con scripts/inline_icons.py. #}
"""


def main() -> int:
    """Write the template from the sprite; returns a process exit code."""
    TEMPLATE.write_text(HEADER + SPRITE.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    print(f"{TEMPLATE.relative_to(ROOT)}: {TEMPLATE.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
