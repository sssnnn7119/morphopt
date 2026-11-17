"""Material-interface collection and material-parameter aggregation."""

from __future__ import annotations

import torchfea

from .baseparam import BaseParams

__all__ = [
    "MaterialsParams",
]


class MaterialsParams(BaseParams):
    """Ordered collection of named material interfaces."""

    from .materials import BaseMaterial, HomogeneousMaterial
    from .materials.models import MaterialModels as models

    def set_materials(self, fe: torchfea.FEAController) -> None:
        """Set materials.

        Args:
            fe (torchfea.FEAController): TorchFEA controller whose assembly is modified or solved.
        """
        for interface in self.interfaces.values():
            interface.set_materials(fe)

    def pathlog_required(self) -> list[str]:
        """Return log subdirectories required by this component.

        Returns:
            list[str]: Relative log subdirectory names required before persistence.
        """
        return ["materials"]
