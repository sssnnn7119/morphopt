"""Application services shared by the MorphOpt desktop views.

The package is deliberately independent from Qt widgets.  It coordinates the
domain model, generated source, result folders and optimization processes;
widgets are responsible only for interaction and presentation.
"""

from .editing import DefinitionCommands
from .expressions import DefinitionValues
from .definitions import ProblemLibrary, ProblemSession
from .quickstart import QuickstartObjective, QuickstartOptions, build_quickstart
from .editor_routing import EditorKind, EditorRoute, route_editor
from .finite_element import FiniteElementSession, IterationModel
from .results import ResultSession, last_completed_iteration
from .runs import (
    OptimizationRunSession,
    RunMode,
    RunSource,
    RunSourceKind,
)

__all__ = [
    "DefinitionCommands",
    "DefinitionValues",
    "EditorKind",
    "EditorRoute",
    "FiniteElementSession",
    "IterationModel",
    "OptimizationRunSession",
    "ProblemLibrary",
    "ProblemSession",
    "QuickstartObjective",
    "QuickstartOptions",
    "build_quickstart",
    "ResultSession",
    "RunMode",
    "RunSource",
    "RunSourceKind",
    "last_completed_iteration",
    "route_editor",
]
