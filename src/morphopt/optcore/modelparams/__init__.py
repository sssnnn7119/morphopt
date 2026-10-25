"""Model parameters: geometry, FEA (loads/constraints) and materials."""

from .base_model_component import BaseModelComponent
from .baseparam import BaseParams
from .feaparams import FEAParams
from .geometry import GeometryParams
from .materialsparams import MaterialsParams
from .params import Params
from .parts import (
    BasePart,
    FixedPart,
    CADPart,
    BoxPart,
    INPPart,
)

__all__ = [
    "BaseModelComponent",
    "BaseParams",
    "BasePart",
    "BoxPart",
    "CADPart",
    "FEAParams",
    "FixedPart",
    "GeometryParams",
    "INPPart",
    "MaterialsParams",
    "Params",
]
