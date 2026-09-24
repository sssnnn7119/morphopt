"""
A differentiable structural optimization framework that eliminates manual sensitivity derivation by fusing the adjoint method with automatic differentiation (AD). The sensitivity corresponds to the virtual work of residual force derivatives on the adjoint displacement field, computed via a single backpropagation through the residual graph. MorphOpt provides a unified interface for geometry, load, and material definition, calls torchfea for GPU-accelerated differentiable nonlinear FEA and adjoint-AD sensitivity, and employs a trust-region optimizer with L-BFGS for design updates. Validated on SIMP topology optimization with B-spline density fields and pneumatic soft robot shape optimization with deformation-dependent follower loads.
"""

# Torch and TorchFEA use GNU OpenMP in this environment.  Set MKL's matching
# threading layer before importing any module that can load NumPy or Torch.
import os as __os
import sys as __sys

if __sys.platform.startswith("linux"):
    __os.environ["MKL_THREADING_LAYER"] = "GNU"

# region: Logging Configuration
import logging as __logging


def enable_logging(level=__logging.INFO, log_file=None, file_log_level=__logging.DEBUG):
    """
    Enable logging for the FEA package.

    Parameters
    ----------
    level : int
        the logging level (e.g., logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL)
    log_file : str, optional
        the path to a log file where logs will be written. If None, logs will only be printed to the console.
    file_log_level : int
        the logging level for the log file. Default is logging.INFO.

    Examples
    --------
    >>> import torchfea
    >>> torchfea.enable_logging(level=logging.DEBUG, log_file='fem.log')
    """
    logger = __logging.getLogger(__name__)
    logger.setLevel(min(level, file_log_level))

    # clear existing handlers to avoid duplicate logs
    logger.handlers.clear()

    # logging to console
    console = __logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(
        __logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
    )
    logger.addHandler(console)

    # logging to file if log_file is provided
    if log_file:
        file_handler = __logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(file_log_level)
        file_handler.setFormatter(
            __logging.Formatter(
                "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
            )
        )
        logger.addHandler(file_handler)

    return logger


# endregion


# region modules (loaded after the core classes they subclass)
from . import codesign, shapeopt, simp
from .opt_runner import debug_optimization, start_optimization
from .optcore.controller import Controller
from .optcore.history import History
from .optcore.modelparams import (
    BasePartInterface,
    FEAParams,
    GeometryParams,
    INPPartInterface,
    MaterialsParams,
    Params,
    TorchFEAPartInterface,
    load_model_assembly,
    resolve_model_path,
)
from .optcore.modelparams.materialinterface import HomogeneousMaterial
from .optcore.objfunc import ObjectiveFunction
from .optcore.protocal import (
    ProtocalInitializable,
    ProtocalSavable,
    ProtocalUpdatable,
    ProtocalVisualizable,
)
from .optcore.solver import Solver
from .optcore.updaters import Updaters
from .shapeopt import BoundaryPartInterface, UpdaterBoundaryPart
from .simp import SIMP_BSPFieldMaterials, UpdaterSIMPMaterial

# endregion
# region scripts
from .utils import check_gradients, get_controller

# endregion

controller: Controller = None
