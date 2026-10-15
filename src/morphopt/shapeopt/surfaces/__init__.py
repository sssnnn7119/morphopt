"""Surface interfaces: the parameterised boundary surfaces of a Part.

A ``BoundaryPart`` owns a list of these; each one maps a 2-D parameter
domain onto the 3-D boundary (B-spline / control-point geometry / fixed STL).
"""

from .base_surface import (
    BaseSurface,
    ControlPointSurface,
    FixedSurface,
)
from .base_constraints import BaseSurfaceConstraints, SurfaceRelationConstraint
from .bsp_constraints import BspSurfaceRelationConstraint
from .cpgeo_constraints import CPGEOSurfaceRelationConstraint
from .bsp_surface import BspSurface
from .cpgeo_surface import CPGEOSurface

__all__ = [
    "BaseSurface",
    "BaseSurfaceConstraints",
    "SurfaceRelationConstraint",
    "BspSurfaceRelationConstraint",
    "CPGEOSurfaceRelationConstraint",
    "ControlPointSurface",
    "FixedSurface",
    "BspSurface",
    "CPGEOSurface",
]
