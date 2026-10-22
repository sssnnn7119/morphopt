"""Boundary interfaces with parametric, BREP or triangular-mesh geometry."""

from .base_surface import (
    BaseSurface,
    ControlPointSurface,
)
from .base_constraints import BaseSurfaceConstraints, SurfaceRelationConstraint
from .bsp_constraints import BspSurfaceRelationConstraint
from .cpgeo_constraints import CPGEOSurfaceRelationConstraint
from .bsp_surface import BspSurface
from .cpgeo_surface import CPGEOSurface
from .brep_surface import BREPSurface
from .mesh_surface import MeshSurface

__all__ = [
    "BaseSurface",
    "BaseSurfaceConstraints",
    "SurfaceRelationConstraint",
    "BspSurfaceRelationConstraint",
    "CPGEOSurfaceRelationConstraint",
    "ControlPointSurface",
    "MeshSurface",
    "BspSurface",
    "CPGEOSurface",
    "BREPSurface",
]
