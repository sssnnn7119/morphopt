"""Cavity offset Parts and their geometry updater.

Compose parameters, objectives, solvers and updater collections using the
common morphopt interfaces. SIMP materials use the simp interfaces.
"""

from .offsetboundarypartinterface import OffsetBoundaryPartInterface
from .update_offsetboundarypart import UpdaterOffsetBoundaryPart
from .constraints import InwardCurvatureRadius, OffsetSurfaceMinThickness

__all__ = [
    "OffsetBoundaryPartInterface",
    "UpdaterOffsetBoundaryPart",
    "InwardCurvatureRadius",
    "OffsetSurfaceMinThickness",
]
