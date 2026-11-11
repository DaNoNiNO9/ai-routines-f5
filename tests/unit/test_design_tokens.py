"""The palette must keep WCAG AA in both themes, and the fonts must be local.

Colours are read from the stylesheet itself, so changing a token without
checking its contrast fails here instead of in someone's eyes.
"""

from __future__ import annotations

import re

import pytest

from config import BASE_DIR

CSS = (BASE_DIR / "app" / "static" / "css" / "app.css").read_text(encoding="utf-8")
FONTS_CSS = (BASE_DIR / "app" / "static" / "css" / "fonts.css").read_text(encoding="utf-8")
ICONS = BASE_DIR / "app" / "static" / "img" / "icons.svg"

AA_TEXT = 4.5
AA_UI = 3.0


def _tokens(selector: str) -> dict[str, str]:
    """The ``--name: #hex`` declarations of one block."""
    block = re.search(re.escape(selector) + r"\s*\{(.*?)\}", CSS, re.S)
    assert block is not None, f"no encuentro el bloque {selector}"
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;", block.group(1)))


def _luminance(colour: str) -> float:
    """Relative luminance of a ``#rrggbb`` colour (WCAG 2.1 definition)."""
    channels = [int(colour.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first: str, second: str) -> float:
    """WCAG contrast ratio between two colours."""
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


DARK = _tokens(':root, [data-theme="dark"]')
LIGHT = _tokens('[data-theme="light"]')

# (foreground, background, minimum): what a person actually has to read.
PAIRS = (
    ("text", "bg", AA_TEXT),
    ("text", "bg-elevated", AA_TEXT),
    ("text-muted", "bg", AA_TEXT),
    ("text-muted", "bg-elevated", AA_TEXT),
    ("accent", "bg", AA_TEXT),
    ("accent", "bg-elevated", AA_TEXT),
    ("accent-contrast", "accent", AA_TEXT),
    ("success", "bg-elevated", AA_TEXT),
    ("warning", "bg-elevated", AA_TEXT),
    ("danger", "bg-elevated", AA_TEXT),
    ("focus", "bg", AA_UI),
    # Borders of inputs and buttons are user interface components (WCAG 2.1, 1.4.11).
    ("border-strong", "bg", AA_UI),
    ("border-strong", "bg-elevated", AA_UI),
)


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize(("front", "back", "minimum"), PAIRS)
def test_palette_meets_wcag_aa(theme: str, front: str, back: str, minimum: float) -> None:
    tokens = DARK if theme == "dark" else LIGHT
    ratio = contrast(tokens[front], tokens[back])
    assert ratio >= minimum, f"{theme}: {front} sobre {back} da {ratio:.2f}:1, hace falta {minimum}"


def test_both_themes_define_the_same_tokens() -> None:
    assert set(DARK) == set(LIGHT)


def test_fonts_are_served_from_the_project() -> None:
    # Nothing is fetched from a third party at page load: no remote url() anywhere.
    assert not re.search(r"url\(\s*['\"]?https?://", CSS + FONTS_CSS)
    assert "@import" not in CSS + FONTS_CSS
    familias = set(re.findall(r"font-family: '([^']+)'", FONTS_CSS))
    assert familias == {"Barlow Condensed", "Inter"}
    for archivo in re.findall(r"url\('\.\./fonts/([^']+)'\)", FONTS_CSS):
        assert (BASE_DIR / "app" / "static" / "fonts" / archivo).is_file(), archivo
    assert "font-display: swap" in FONTS_CSS


def test_every_icon_used_in_templates_is_in_the_sprite() -> None:
    sprite = ICONS.read_text(encoding="utf-8")
    disponibles = set(re.findall(r'<symbol id="i-([\w-]+)"', sprite))
    usados: set[str] = set()
    for plantilla in (BASE_DIR / "app" / "templates").rglob("*.html"):
        usados.update(re.findall(r"icon\(\s*'([\w-]+)'", plantilla.read_text(encoding="utf-8")))
    assert usados, "ninguna plantilla usa iconos"
    assert usados <= disponibles, f"faltan en el sprite: {sorted(usados - disponibles)}"


def test_the_embedded_sprite_matches_the_source() -> None:
    """``scripts/inline_icons.py`` copies one into the other; they cannot drift."""
    plantilla = (BASE_DIR / "app" / "templates" / "components" / "sprite.html").read_text(
        encoding="utf-8"
    )
    fuente = ICONS.read_text(encoding="utf-8")
    assert plantilla.endswith(fuente), "sprite.html no está al día: python scripts/inline_icons.py"


def test_nav_link_colour_never_reaches_buttons() -> None:
    """A button inside the navigation keeps the accent's text colour.

    ``.nav-links a`` is more specific than ``.button``: written without
    ``:not(.button)`` it painted "Crear cuenta" muted grey on orange (about 1:1).
    """
    rules = re.findall(r"(\.nav-links a[^{,]*)\{[^}]*\bcolor:", CSS)
    assert rules, "no encuentro la regla de color de los enlaces de navegación"
    for selector in rules:
        if "aria-current" in selector:
            continue
        assert ":not(.button)" in selector, selector
