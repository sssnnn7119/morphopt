"""Application services shared by the MorphOpt desktop views.

The package is deliberately independent from Qt widgets.  It coordinates the
domain model, generated source, result folders and optimization processes;
widgets are responsible only for interaction and presentation.
"""

from .definitions import MissingImportedModelError, ProblemLibrary, ProblemSession
from .editor_routing import EditorKind, EditorRoute, route_editor
from .results import ResultSession, last_completed_iteration
from .runs import (
    OptimizationRunSession,
    RunMode,
    RunSource,
    RunSourceKind,
)

__all__ = [
    "EditorKind",
    "EditorRoute",
    "OptimizationRunSession",
    "MissingImportedModelError",
    "ProblemLibrary",
    "ProblemSession",
    "ResultSession",
    "RunMode",
    "RunSource",
    "RunSourceKind",
    "last_completed_iteration",
    "route_editor",
]
