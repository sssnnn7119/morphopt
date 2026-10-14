"""Part interfaces: one ``torchfea.Part`` plus its Instances per interface."""

from .basepartinterface import BasePartInterface
from .cadpartinterface import CADPartInterface
from .inppartinterface import INPPartInterface
from .primitivepartinterface import BoxPartInterface
from .torchfeapartinterface import (
    TorchFEAPartInterface,
    load_model_assembly,
    resolve_model_path,
)

__all__ = [
    "BasePartInterface",
    "CADPartInterface",
    "BoxPartInterface",
    "INPPartInterface",
    "TorchFEAPartInterface",
    "load_model_assembly",
    "resolve_model_path",
]
