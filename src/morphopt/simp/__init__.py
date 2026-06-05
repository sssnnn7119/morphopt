"""
This module implements the SIMP (Solid Isotropic Material with Penalization) method for topology optimization. It includes the SIMPSolver class for solving the finite element analysis (FEA) problem, the UpdaterMaterials class for updating the material properties based on the optimization results, and the SIMP_BSPFieldMaterials class for defining the material properties using a B-spline field.
"""


from .solver import SIMPSolver
from .update_material import UpdaterMaterials
from .simpmaterial import SIMP_BSPFieldMaterials
from ..optcore import FEAParams, HomogeneousMaterial, Solver, Updaters, ObjectiveFunction, Params, FixedGeometryNodeElement, FixedGeometryINP