"""Surface interfaces: the parameterised boundary surfaces of a Part.

A ``BoundaryPartInterface`` owns a list of these; each one maps a 2-D parameter
domain onto the 3-D boundary (B-spline / control-point geometry / fixed STL).
"""

from .basesurfaceinterface import (
    BaseSurfaceInterface,
    CpBasedSurfaceInterface,
    FixedSurface,
)
from .basesurfaceconstraints import BaseSurfaceConstraints, SurfaceRelationConstraint
from .bspsurfaceconstraints import BspSurfaceRelationConstraint
from .cpgeosurfaceconstraints import CPGEOSurfaceRelationConstraint
from .bspsurfaceinterface import BspSurfaceInterface
from .cpgeosurfaceinterface import CPGEOSurfaceInterface

__all__ = [
    "BaseSurfaceInterface",
    "BaseSurfaceConstraints",
    "SurfaceRelationConstraint",
    "BspSurfaceRelationConstraint",
    "CPGEOSurfaceRelationConstraint",
    "CpBasedSurfaceInterface",
    "FixedSurface",
    "BspSurfaceInterface",
    "CPGEOSurfaceInterface",
]
