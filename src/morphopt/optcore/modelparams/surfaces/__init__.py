"""Surface definitions and fairness evaluators."""

from .base import BaseSurfaceInterface, SurfaceExportFormat, SurfaceGeometryData
from .bsp import BSPCylinderSurface, BSPSurface
from .cpgeo import CPGEOCylinderSurface, CPGEOSphereSurface, CPGEOSurface
from .cpbased import CpBasedSurface
from .fairness import BSPFairnessEvaluator, CPGEOFairnessEvaluator, FairnessEvaluator
from .preload import PreLoadData, SurfacePreload
from .stl import STLSurface

__all__ = [
    "BaseSurfaceInterface",
    "BSPSurface",
    "BSPCylinderSurface",
    "BSPFairnessEvaluator",
    "CPGEOCylinderSurface",
    "CPGEOFairnessEvaluator",
    "CPGEOSphereSurface",
    "CPGEOSurface",
    "CpBasedSurface",
    "FairnessEvaluator",
    "PreLoadData",
    "STLSurface",
    "SurfaceGeometryData",
    "SurfaceExportFormat",
    "SurfacePreload",
]
