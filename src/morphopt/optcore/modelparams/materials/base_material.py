"""Base class for material assignments to TorchFEA Parts."""

from __future__ import annotations

import torch
import torchfea

from ..base_model_component import BaseModelComponent
from .models import MaterialModels


class BaseMaterial(BaseModelComponent):
    """Assign one material definition to elements in one Part.

    ``elementname`` may be empty. In that case the material is applied to
    every element family in ``part_name``.
    """

    from .models import MaterialModels as models

    def __init__(
        self,
        part_name: str,
        material_parameters: MaterialModels.MaterialParameters,
        elementname: str = "",
        density: float = 0.0,
    ) -> None:
        super().__init__()
        self.part_name = str(part_name or "").strip()
        if not self.part_name:
            raise ValueError("part_name cannot be empty.")
        self.elementname = str(elementname or "").strip()
        self.material_parameters: MaterialModels.MaterialParameters = (
            material_parameters
        )
        self._density: float = float(density)
        self._name: str = ""
        """Registration name inside the owning MaterialsParams collection."""

    @property
    def name(self) -> str:
        """Name of this material inside its owning collection.

        The collection assigns the name when this material is registered, so it
        is unavailable before registration.
        """
        if not self._name:
            raise ValueError(
                f"{type(self).__name__} has no name yet; register it with "
                "MaterialsParams.add_interface(..., name=...)."
            )
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = str(value)

    @property
    def density(self) -> float:
        """Return the mass density assigned to the target elements."""
        return self._density

    @density.setter
    def density(self, value: float) -> None:
        """Set the mass density assigned to the target elements."""
        self._density = float(value)

    def target_elements(
        self,
        assembly: torchfea.Assembly,
    ) -> list[tuple[str, torchfea.elements.Element_3D]]:
        """Return the selected element families from the target Part."""
        part = assembly.get_part(self.part_name)
        if self.elementname:
            if self.elementname not in part.elems:
                raise KeyError(
                    f"Element {self.elementname!r} does not exist on Part "
                    f"{self.part_name!r}."
                )
            return [(self.elementname, part.elems[self.elementname])]
        if not part.elems:
            raise ValueError(f"Part {self.part_name!r} contains no elements.")
        return list(part.elems.items())

    def set_materials(self, fe: torchfea.FEAController) -> None:
        """Assign this interface to its target elements."""
        raise NotImplementedError

    def get_design_values(self) -> torch.Tensor:
        """Return live design values for a designable material component."""
        return torch.zeros(0)
