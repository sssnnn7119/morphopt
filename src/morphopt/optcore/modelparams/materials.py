"""Material-interface collection and material-parameter aggregation."""

from __future__ import annotations

import torchfea

from .baseparam import BaseParams

__all__ = [
    "MaterialsParams",
]


class MaterialsParams(BaseParams):
    """Ordered collection of named material interfaces."""

    from .materialinterface import BaseMaterialInterface, HomogeneousMaterial
    from .materialinterface.materialmodels import MaterialModels as materialmodels

    def set_materials(self, fe: torchfea.FEAController) -> None:
        for interface in self.interfaces.values():
            interface.set_materials(fe)

    def pathlog_required(self) -> list[str]:
        return ["materials"]
