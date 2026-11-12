"""El catálogo inglés: completo, sin fuzzy, con los mismos marcadores y compilado.

Un `.po` traducido a medias o un `.mo` viejo no rompen ninguna página: se ve el
castellano por debajo y nadie se entera. Por eso se comprueba aquí.
"""

from __future__ import annotations

from babel.messages.catalog import Catalog
from babel.messages.mofile import read_mo
from babel.messages.pofile import read_po

from config import BASE_DIR

PO = BASE_DIR / "app" / "translations" / "en" / "LC_MESSAGES" / "messages.po"
MO = PO.with_suffix(".mo")


def _po() -> Catalog:
    with PO.open("rb") as handle:
        return read_po(handle, locale="en")


def _mo() -> Catalog:
    with MO.open("rb") as handle:
        return read_mo(handle)


def test_every_message_is_translated() -> None:
    faltan = [message.id for message in _po() if message.id and not message.string]
    assert faltan == []


def test_no_fuzzy_translations() -> None:
    catalog = _po()
    assert not catalog.fuzzy
    dudosas = [message.id for message in catalog if message.id and "fuzzy" in message.flags]
    assert dudosas == []


def test_placeholders_survive_the_translation() -> None:
    """Los mismos %(nombre)s en el original y en la traducción, o el texto revienta."""
    catalog = _po()
    errores = [(message.id, str(error)) for message, errors in catalog.check() for error in errors]
    assert errores == []


def test_compiled_catalogue_is_up_to_date() -> None:
    """Si alguien traduce y no ejecuta pybabel compile, la app sigue en castellano."""
    compilado = _mo()

    def _texto(string: object) -> object:
        # read_mo devuelve los plurales como lista y read_po como tupla.
        return tuple(string) if isinstance(string, list | tuple) else string

    desfase = [
        message.id
        for message in _po()
        if message.id
        and _texto(getattr(compilado.get(message.id), "string", None)) != _texto(message.string)
    ]
    assert desfase == []
