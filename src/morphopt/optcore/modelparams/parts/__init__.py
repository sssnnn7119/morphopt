"""Part definition classes."""

from .base import BasePartDefinition
from .boundary import BoundaryPart
from .inp import InpPart
from .instance import InstanceDefinition
from .mesh import MeshPart
from .offset import OffsetShellPart
from .torchfea import TorchFEAPart

__all__ = [
    "BasePartDefinition",
    "BoundaryPart",
    "InpPart",
    "InstanceDefinition",
    "MeshPart",
    "OffsetShellPart",
    "TorchFEAPart",
]

