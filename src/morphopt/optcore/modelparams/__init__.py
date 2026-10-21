"""Model parameters: geometry, FEA (loads/constraints) and materials."""

from .base_model_component import BaseModelComponent
from .baseparam import BaseParams
from .feaparams import FEAParams
from .geometry import GeometryParams
from .materialsparams import MaterialsParams
from .params import Params
from .parts import (
    BasePart,
    CADPart,
    BoxPart,
    INPPart,
)

__all__ = [
    "BaseModelComponent",
    "BaseParams",
    "FEAParams",
    "GeometryParams",
    "MaterialsParams",
    "Params",
    "BasePart",
    "CADPart",
    "BoxPart",
    "INPPart",
]
