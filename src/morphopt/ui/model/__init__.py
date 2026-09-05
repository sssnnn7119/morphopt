"""Data model for the MorphOpt UI.

The problem is held as a generic, schema-tagged node tree (``Node``) that
mirrors the Params / Geometry / Loads / Steps / Materials / Objective /
Solver / Updater hierarchy of a morphopt ``ThisController``.  The model is
deliberately generic: every node carries a ``kind`` that resolves to a field
schema (see :mod:`morphopt.ui.model.schemas`) and a ``params`` dict whose keys
match the backend constructor arguments.  Scheme templates know how to walk the
tree and emit valid morphopt code.
"""

from .problem import Node, ProblemDefinition, find_node, list_node_paths
from . import schemas
from . import loaders

__all__ = ["Node", "ProblemDefinition", "find_node", "list_node_paths", "schemas", "loaders"]
