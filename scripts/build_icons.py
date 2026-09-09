"""Build ``app/static/img/icons.svg`` from Lucide, with only the icons the app uses.

Run it when a template needs an icon that is not in ``ICONS`` yet::

    python scripts/build_icons.py

It downloads each icon from jsDelivr and writes one ``<symbol>`` per icon into a
single sprite, so a page costs one request no matter how many icons it shows.
The stroke attributes live on the root ``<svg>`` and the colour comes from
``currentColor``, so an icon takes the colour of the text around it.
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

VERSION = "1.43.0"
BASE_URL = f"https://cdn.jsdelivr.net/npm/lucide-static@{VERSION}/icons/"
SPRITE = Path(__file__).resolve().parent.parent / "app" / "static" / "img" / "icons.svg"
TIMEOUT_SECONDS = 25

# Alphabetical; the name is also the id in the sprite (``#i-<name>``).
ICONS = (
    "apple",
    "arrow-right",
    "calendar-check",
    "chart-line",
    "check",
    "chevron-left",
    "chevron-right",
    "circle-check",
    "clock",
    "dumbbell",
    "flame",
    "footprints",
    "info",
    "layout-dashboard",
    "loader-circle",
    "log-out",
    "moon",
    "notebook-pen",
    "plus",
    "repeat",
    "scale",
    "sun",
    "timer",
    "trash-2",
    "trending-down",
    "triangle-alert",
    "trophy",
    "x",
)


def fetch(name: str) -> str:
    """Inner markup of one Lucide icon.

    Raises:
        RuntimeError: If the icon cannot be downloaded or has no ``<svg>`` body.
    """
    try:
        with urllib.request.urlopen(BASE_URL + name + ".svg", timeout=TIMEOUT_SECONDS) as response:
            svg = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"no se pudo descargar el icono {name!r}: {exc}") from exc
    body = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S)
    if body is None:
        raise RuntimeError(f"el icono {name!r} no tiene cuerpo SVG")
    return re.sub(r"\s+", " ", body.group(1).strip())


def build() -> str:
    """The whole sprite as text."""
    symbols = [
        f'  <symbol id="i-{name}" viewBox="0 0 24 24">{fetch(name)}</symbol>' for name in ICONS
    ]
    return (
        f"<!-- Iconos de Lucide {VERSION} (licencia ISC). Ver docs/CREDITOS.md.\n"
        "     Sprite generado por scripts/build_icons.py: solo los iconos que usa la app. -->\n"
        '<svg xmlns="http://www.w3.org/2000/svg" fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round" style="display:none">\n'
        + "\n".join(symbols)
        + "\n</svg>\n"
    )


def main() -> int:
    """Write the sprite; returns a process exit code."""
    try:
        sprite = build()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    SPRITE.write_text(sprite, encoding="utf-8", newline="\n")
    print(f"{SPRITE.relative_to(Path.cwd())}: {len(ICONS)} iconos, {SPRITE.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
