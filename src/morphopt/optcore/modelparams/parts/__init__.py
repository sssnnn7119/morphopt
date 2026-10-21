"""Part definitions: one ``torchfea.Part`` and its Instances per definition."""

from .base_part import BasePart
from .cad_part import CADPart
from .inp_part import INPPart
from .box_part import BoxPart

__all__ = [
    "BasePart",
    "CADPart",
    "BoxPart",
    "INPPart",
]
