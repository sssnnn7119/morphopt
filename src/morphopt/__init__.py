# region optcore imports
from .optcore.controller import Controller
from .optcore.modelparams import GeometryParams, FEAParams, Materials, SIMP_BSPFieldMaterials
from .optcore.solver import MorphSolver
from .optcore.updaters.geometry import UpdaterGeometries
from .optcore.updaters.materials import UpdaterMaterials
from .optcore.updaters.updaters import Updaters
from .optcore.modelparams import Params
from .optcore.objfunc import ObjectiveFunction
from .optcore.history import History
from .optcore.baseobject import BaseObject
# endregion

from .opt_runner import start_optimization, debug_optimization, view_optimization_result

# region codesign imports
from . import codesign
# endregion

controller: Controller = None

__all__ = [
    "Controller",
    "GeometryParams",
    "FEAParams",
    "Materials",
    "SIMPMaterials",
    "MorphSolver",
    "UpdaterGeometries",
    "UpdaterMaterials",
    "Updaters",
    "Params",
    "ObjectiveFunction",
    "History",
    "BaseObject",

    "start_optimization",
    "debug_optimization",
    "view_optimization_result",

    'codesign',
]

