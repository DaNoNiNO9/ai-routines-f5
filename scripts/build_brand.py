r"""Genera los iconos de la marca Alza en ``app/static/img/``.

La marca es una A en forma de flecha hacia arriba («alza»): un chevrón con
travesaño, en el color de contraste sobre un cuadrado redondeado naranja.
La misma geometría la usan la cabecera (``components/brand.html``), el PDF
(``services/exports.py``) y estos ficheros:

- ``favicon.svg``: navegadores actuales.
- ``favicon.ico`` (16, 32 y 48 px): navegadores antiguos y ``/favicon.ico``.
- ``apple-touch-icon.png`` (180 px): acceso directo en la pantalla del móvil.

Uso: ``.venv\Scripts\python.exe scripts\build_brand.py``
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "app" / "static" / "img"

# Geometría en una caja de 32 x 32 (la misma que en brand.html y exports.py).
BOX = 32
RADIUS = 8
CHEVRON = [(9.5, 23.5), (16.0, 9.5), (22.5, 23.5)]
BAR = [(12.6, 18.5), (19.4, 18.5)]
STROKE = 3.4

ACCENT = "#ff8a34"
CONTRAST = "#14100a"

SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {BOX} {BOX}">
<rect width="{BOX}" height="{BOX}" rx="{RADIUS}" fill="{ACCENT}"/>
<path d="M9.5 23.5 16 9.5l6.5 14M12.6 18.5h6.8" fill="none" stroke="{CONTRAST}" \
stroke-width="{STROKE}" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""


def _render(size: int, rounded: bool = True) -> Image.Image:
    """Dibuja la marca a ``size`` px con sobremuestreo para suavizar bordes."""
    scale = size * 8 / BOX
    big = round(BOX * scale)
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    radius = RADIUS * scale if rounded else 0
    draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=radius, fill=ACCENT)
    width = round(STROKE * scale)
    for line in (CHEVRON, BAR):
        points = [(x * scale, y * scale) for x, y in line]
        draw.line(points, fill=CONTRAST, width=width, joint="curve")
        for x, y in points:  # extremos redondeados
            r = width / 2
            draw.ellipse((x - r, y - r, x + r, y + r), fill=CONTRAST)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    """Escribe los tres ficheros de iconos."""
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "favicon.svg").write_text(SVG, encoding="utf-8")
    _render(48).save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    # iOS redondea las esquinas por su cuenta: el icono va a sangre.
    _render(180, rounded=False).convert("RGB").save(OUT / "apple-touch-icon.png")
    print(f"Iconos escritos en {OUT}")


if __name__ == "__main__":
    main()
