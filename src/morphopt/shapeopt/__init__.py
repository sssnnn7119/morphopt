"""Concrete interfaces used for boundary-surface shape updates.

The common optimization model lives directly in :mod:`morphopt`: compose
``GeometryParams``, ``FEAParams``, ``MaterialsParams``, ``Solver`` and
``Updaters`` there.  This package only owns the concrete boundary Part
interface and the updater that knows how to update it.
"""

from .boundarypartinterface import BoundaryPartInterface
from .update_boundarypart import UpdaterBoundaryPart
from .surfaceinterfaces.basesurfaceconstraints import (
    BaseSurfaceConstraints,
    SurfaceRelationConstraint,
)
from .surfaceinterfaces.bspsurfaceconstraints import BspSurfaceRelationConstraint
from .surfaceinterfaces.cpgeosurfaceconstraints import CPGEOSurfaceRelationConstraint

__all__ = [
    "BoundaryPartInterface",
    "UpdaterBoundaryPart",
    "BaseSurfaceConstraints",
    "SurfaceRelationConstraint",
    "BspSurfaceRelationConstraint",
    "CPGEOSurfaceRelationConstraint",
]
