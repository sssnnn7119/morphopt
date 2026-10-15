"""Concrete interfaces used for boundary-surface shape updates.

The common optimization model lives directly in :mod:`morphopt`: compose
``GeometryParams``, ``FEAParams``, ``MaterialsParams``, ``Solver`` and
``Updaters`` there.  This package only owns the concrete boundary Part
interface and the updater that knows how to update it.
"""

from .boundary_part import BoundaryPart
from .update_boundary_part import UpdaterBoundaryPart
from .surfaces.base_constraints import (
    BaseSurfaceConstraints,
    SurfaceRelationConstraint,
)
from .surfaces.bsp_constraints import BspSurfaceRelationConstraint
from .surfaces.cpgeo_constraints import CPGEOSurfaceRelationConstraint

__all__ = [
    "BoundaryPart",
    "UpdaterBoundaryPart",
    "BaseSurfaceConstraints",
    "SurfaceRelationConstraint",
    "BspSurfaceRelationConstraint",
    "CPGEOSurfaceRelationConstraint",
]
