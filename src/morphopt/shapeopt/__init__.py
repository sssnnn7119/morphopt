"""
This module implements the shape optimization framework for morphopt. It includes the GeometryParams class for defining the geometry parameters of the optimization problem, and the UpdaterGeometries class for updating the geometry based on the optimization results.
"""

from .geometryparams import GeometryParams
from .update_geometry import UpdaterGeometries
from ..optcore import FEAParams, HomogeneousMaterial, Solver, Updaters, Params
from .objfunc import ObjectiveFunction
