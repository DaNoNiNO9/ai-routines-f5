"""Babel extractor for the engine's message templates.

``app/engine/messages.py`` keeps its texts in a plain dictionary so the engine
stays free of Flask and readable as the reference wording. pybabel only looks
for ``_("...")`` calls, so this extractor walks the module with ``ast`` and
yields every value of ``TEMPLATES``.

Wired up in ``babel.cfg``::

    [extractors]
    engine = scripts.babel_engine:extract_engine_messages

    [engine: app/engine/messages.py]
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from typing import IO, Any

TEMPLATES_NAME = "TEMPLATES"


def extract_engine_messages(
    fileobj: IO[bytes],
    keywords: Any,  # noqa: ARG001 - part of the Babel extractor contract
    comment_tags: Any,  # noqa: ARG001 - idem
    options: Any,  # noqa: ARG001 - idem
) -> Iterator[tuple[int, str, str, list[str]]]:
    """Yield ``(line, function, message, comments)`` for each template."""
    tree = ast.parse(fileobj.read().decode("utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign | ast.Assign):
            continue
        targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
        names = {target.id for target in targets if isinstance(target, ast.Name)}
        if TEMPLATES_NAME not in names or not isinstance(node.value, ast.Dict):
            continue
        for key, value in zip(node.value.keys, node.value.values, strict=True):
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                continue
            code = key.value if isinstance(key, ast.Constant) else "?"
            yield (value.lineno, "gettext", value.value, [f"código del motor: {code}"])
