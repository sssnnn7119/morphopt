"""Part definitions: one ``torchfea.Part`` and its Instances per definition."""

from .base_part import BasePart
from .fixed_part import FixedPart
from .cad_part import CADPart
from .inp_part import INPPart
from .box_part import BoxPart

__all__ = [
    "BasePart",
    "BoxPart",
    "CADPart",
    "FixedPart",
    "INPPart",
]
