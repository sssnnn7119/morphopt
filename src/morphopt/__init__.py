"""MorphOpt V4 public package.

The V4 package is intentionally independent from :mod:`morphopt3`.  The
domain modules are small, composable objects and the runtime is driven by
``Controller``/``TaskRunner``.
"""

from .logging import configure_logging, get_logger
from .task import RuntimeEvent, TaskRunner, start_optimization
from .optcore.controller import Controller, StepResult
from .optcore.design_registry import DesignBlock, DesignKey, DesignRegistry
from .optcore.history import History, HistoryRecord
from .optcore.objective import ObjectiveFunction
from .optcore.sensitivity import SensitivityAnalyzer
from .optcore.solver import Solver, StaticResult
from .optcore.modelparams import FEAParams, GeometryParams, MaterialsParams, Params, ReferencePoint
from .optcore.updaters import Updaters
from .utils import check_gradients, load_controller

__all__ = [
    "Controller",
    "DesignBlock",
    "DesignKey",
    "DesignRegistry",
    "FEAParams",
    "GeometryParams",
    "History",
    "HistoryRecord",
    "MaterialsParams",
    "ObjectiveFunction",
    "Params",
    "ReferencePoint",
    "RuntimeEvent",
    "SensitivityAnalyzer",
    "Solver",
    "StaticResult",
    "StepResult",
    "TaskRunner",
    "Updaters",
    "configure_logging",
    "get_logger",
    "check_gradients",
    "load_controller",
    "start_optimization",
]
