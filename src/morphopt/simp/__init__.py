"""
This module implements the SIMP (Solid Isotropic Material with Penalization)
method for topology optimization. It includes the SIMPSolver class for solving
the finite element analysis (FEA) problem, the UpdaterSIMPMaterial class for
updating a SIMP material interface based on the optimization results, and the
SIMP_BSPFieldMaterials class for defining the material properties using a
B-spline field.

SIMP jobs use fixed geometry: register one ``TorchFEAPartInterface`` (imported from
a ``torchfea-ui`` export) or one ``INPPartInterface`` per Part.
"""

from ..optcore import (
    BasePartInterface,
    FEAParams,
    GeometryParams,
    INPPartInterface,
    MaterialsParams,
    ObjectiveFunction,
    Params,
    Solver,
    TorchFEAPartInterface,
    Updaters,
)
from .simpmaterial import SIMP_BSPFieldMaterials
from .solver import SIMPSolver
from .update_simpmaterial import UpdaterSIMPMaterial
