"""Uniform material assignment interface."""

from __future__ import annotations

import torchfea

from .basematerialinterface import BaseMaterialInterface
from .materialmodels import MaterialModels


class HomogeneousMaterial(BaseMaterialInterface):
    """Assign one uniform TorchFEA material to a Part."""

    def set_materials(self, fe: torchfea.FEAController) -> None:
        """Assign the uniform material and density to target elements."""
        for _name, elements in self.target_elements(fe.assembly):
            elements.delete_material()
            elements.set_materials(MaterialModels.create_material(
                material_parameters=self.material_parameters,
            ))
            elements.density = self.density
