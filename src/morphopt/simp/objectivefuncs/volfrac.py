import torch
from typing import Any

from ..simpmaterial import SIMP_BSPFieldMaterials
from ...optcore import MaterialsParams
from .basefuncs import BaseConstraints
import morphopt
class VolFrac(BaseConstraints):
    """
    Objective function to enforce volume fraction constraint in SIMP material optimization.
    """

    def __init__(
            self,
            volfrac_min: float,
            volfrac_max: float,
            elementname: str,
            penalty: float = 1e0,
    ) -> None:
        super().__init__()
        self.volfrac_min = float(volfrac_min)
        self.volfrac_max = float(volfrac_max)
        self.penalty = float(penalty)
        self.elementname = str(elementname).strip()
        if not self.elementname:
            raise ValueError("VolFrac requires an explicit elems name.")

        self.gaussian_points: torch.Tensor | None = None
        self.gaussian_weights: torch.Tensor | None = None

        self._indices: torch.Tensor | None = None
        self._weights: torch.Tensor | None = None
        self._material_interface: SIMP_BSPFieldMaterials | None = None


    def initialize(
            self,
            material_params: MaterialsParams,
            *args: Any,
            **kwargs: Any,
    ) -> None:
        # The aggregate may contain a SIMP field for the solid and one or
        # more homogeneous interfaces (for example the codesign shell).
        candidates = material_params.design_interfaces()
        self._material_interface = next(
            (interface for interface in candidates
             if not interface.elementname
             or interface.elementname == self.elementname),
            None)
        if self._material_interface is None:
            raise ValueError(
                f"No design material interface targets element "
                f"{self.elementname!r}.")
        material = self._material_interface
        part = morphopt.controller.objfun.fe.assembly.get_part(material.part_name)
        if self.elementname not in part.elems:
            raise KeyError(
                f"Elems {self.elementname!r} does not exist on Part "
                f"{material.part_name!r}.")
        elems = part.elems[self.elementname]
        self.gaussian_points = elems.get_gaussian_points(part.nodes).reshape(-1, 3)
        self.gaussian_weights = elems.gaussian_weight.flatten()

        self._indices, self._weights = material._get_indices_weight_for_nodes(self.gaussian_points)




    def __call__(
            self,
            material_params: MaterialsParams,
            *args: Any,
            **kwargs: Any,
    ) -> torch.Tensor:
        
        
        material = self._material_interface
        num_pts = self.gaussian_points.shape[0]
        designfield = torch.zeros([num_pts, 1], dtype=material._cps.dtype, device=self.gaussian_points.device)
        designfield[:, 0].scatter_add_(0, self._indices[0], self._weights * material._cps[self._indices[1], 0])
        ratio_now = 1 / (1 + torch.exp(-designfield)).flatten()

        volume_fraction = (ratio_now * self.gaussian_weights).sum() / self.gaussian_weights.sum()

        min_loss = self.penalty * (torch.clamp(self.volfrac_min - volume_fraction, min=0.0)) ** 2
        max_loss = self.penalty * (torch.clamp(volume_fraction - self.volfrac_max, min=0.0)) ** 2
        return min_loss + max_loss
