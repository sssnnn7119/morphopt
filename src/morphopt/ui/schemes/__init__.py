"""Per-scheme templates for the MorphOpt definition workbench.

Each scheme module knows:
* which classes the generated ``ThisController`` must subclass,
* how to build a sensible *default* problem tree (mirroring the canonical
  example job scripts in ``examples/`` / ``myjobs/``),
* which code slots (objective, constraints, ...) get sensible default text.

The actual source rendering lives in :mod:`morphopt.ui.codegen`.
"""

from .base import SchemeTemplate, get_template, SCHEME_REGISTRY

__all__ = ["SchemeTemplate", "get_template", "SCHEME_REGISTRY"]
