"""Persistence for UI problem definitions (canonical ``*.morph`` only).

``*.morph`` is a JSON serialization of the :class:`ProblemDefinition` and is
the standard interchange format (lossless).  There is intentionally *no*
Python-script import: legacy ``.py`` files are no longer parsed; the UI only
imports ``*.morph`` and exports ``*.morph`` / a runnable ``*.py`` (generated
from the serialized model).
"""

from __future__ import annotations

import json
from pathlib import Path

from .problem import ProblemDefinition

MORPH_SUFFIX = ".morph"


def save_morph(problem: ProblemDefinition, path) -> str:
    """Write ``problem`` to a ``*.morph`` file (appends suffix if missing)."""
    path = str(path)
    if not path.endswith(MORPH_SUFFIX):
        path += MORPH_SUFFIX
    Path(path).write_text(json.dumps(problem.to_dict(), indent=2, ensure_ascii=False),
                          encoding="utf-8")
    return path


def load_morph(path) -> ProblemDefinition:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return ProblemDefinition.from_dict(data)
