"""Cavity offset Parts and their geometry updater.

Compose parameters, objectives, solvers and updater collections using the
common morphopt interfaces. SIMP materials use the simp interfaces.
"""

from .offset_boundary_part import OffsetBoundaryPart
from .update_offset_boundary_part import UpdaterOffsetBoundaryPart
from .constraints import InwardCurvatureRadius, OffsetSurfaceMinThickness

__all__ = [
    "OffsetBoundaryPart",
    "UpdaterOffsetBoundaryPart",
    "InwardCurvatureRadius",
    "OffsetSurfaceMinThickness",
]
