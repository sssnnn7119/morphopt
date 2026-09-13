"""Material assignment interfaces."""

from .basematerialinterface import BaseMaterialInterface
from .homogeneousmaterial import HomogeneousMaterial
from .materialmodels import MaterialModels

__all__ = [
    "BaseMaterialInterface",
    "HomogeneousMaterial",
    "MaterialModels",
]
