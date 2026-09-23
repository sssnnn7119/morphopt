"""
This module implements the shape optimization framework for morphopt. It
includes the GeometryParams collection (a list of part interfaces), the
BoundaryPartInterface that describes a Part by parameterised boundary
surfaces, and the UpdaterBoundaryPart class that updates one such Part.
"""

from ..optcore import (
    BasePartInterface,
    FEAParams,
    INPPartInterface,
    MaterialsParams,
    Params,
    Solver,
    TorchFEAPartInterface,
    ProtocalUpdatable,
    Updaters,
)
from .boundarypartinterface import BoundaryPartInterface
from .geometryparams import GeometryParams
from .meshgenerator import MeshGenerator
from .objfunc import ObjectiveFunction
from .update_boundarypart import UpdaterBoundaryPart
