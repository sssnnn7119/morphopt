"""Base class for material assignments to TorchFEA parts."""

from __future__ import annotations

import torch
import torchfea

from ..baseparam import BaseParams
from .materialmodels import MaterialModels


class BaseMaterialInterface(BaseParams):
    """Assign one material definition to elements in one Part.

    ``elementname`` may be empty. In that case the interface is applied to
    every element family in ``part_name``.
    """

    from .materialmodels import MaterialModels as materialmodels

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
        self.material_parameters: MaterialModels.MaterialParameters = material_parameters
        self._density: float = float(density)
        self._name: str = ""

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
                    f"{self.part_name!r}.")
            return [(self.elementname, part.elems[self.elementname])]
        if not part.elems:
            raise ValueError(f"Part {self.part_name!r} contains no elements.")
        return list(part.elems.items())

    def set_materials(self, fe: torchfea.FEAController) -> None:
        """Assign this interface to its target elements."""
        raise NotImplementedError

    def get_design_values(self) -> torch.Tensor:
        """Return live design values for a designable material interface."""
        return torch.zeros(0)
