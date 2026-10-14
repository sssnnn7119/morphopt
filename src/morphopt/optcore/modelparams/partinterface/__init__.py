"""Part interfaces: one ``torchfea.Part`` plus its Instances per interface."""

from .basepartinterface import BasePartInterface
from .chamberlayout import ChamberLayer, LayeredChambers
from .inppartinterface import INPPartInterface
from .primitivepartinterface import BoxPartInterface, CylinderPartInterface
from .torchfeapartinterface import (
    TorchFEAPartInterface,
    load_model_assembly,
    resolve_model_path,
)

__all__ = [
    "BasePartInterface",
    "ChamberLayer",
    "LayeredChambers",
    "BoxPartInterface",
    "CylinderPartInterface",
    "INPPartInterface",
    "TorchFEAPartInterface",
    "load_model_assembly",
    "resolve_model_path",
]
