"""Cavity offset Parts and their geometry updater.

Compose parameters, objectives, solvers and updater collections using the
common morphopt interfaces. SIMP materials use the simp interfaces.
"""

from .constraints import InwardCurvatureRadius, OffsetSurfaceMinThickness
from .offset_boundary_part import OffsetBoundaryPart
from .update_offset_boundary_part import UpdaterOffsetBoundaryPart

__all__ = [
    "InwardCurvatureRadius",
    "OffsetBoundaryPart",
    "OffsetSurfaceMinThickness",
    "UpdaterOffsetBoundaryPart",
]
