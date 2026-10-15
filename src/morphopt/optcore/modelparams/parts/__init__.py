"""Part definitions: one ``torchfea.Part`` and its Instances per definition."""

from .base_part import BasePart
from .cad_part import CADPart
from .inp_part import INPPart
from .box_part import BoxPart
from .torch_fea_part import (
    TorchFEAPart,
    load_model_assembly,
    resolve_model_path,
)

__all__ = [
    "BasePart",
    "CADPart",
    "BoxPart",
    "INPPart",
    "TorchFEAPart",
    "load_model_assembly",
    "resolve_model_path",
]
