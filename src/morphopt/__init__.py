# region optcore imports
from .optcore.controller import Controller
from .optcore.modelparams import FEAParams, FixedGeometryINP, FixedGeometry, HomogeneousMaterial, Params
from .optcore.solver import Solver
from .optcore.modelparams import Params
from .optcore.updaters import Updaters
from .optcore.objfunc import ObjectiveFunction
from .optcore.history import History
from .optcore.baseobject import BaseObject
# endregion

from .opt_runner import start_optimization, debug_optimization, view_optimization_result

# region modules
from . import shapeopt
from . import codesign
from . import simp
# endregion

controller: Controller = None

