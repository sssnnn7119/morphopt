import torch
from ..simpmaterial import SIMP_BSPFieldMaterials
from .basefuncs import BaseConstraints
import morphopt
class VolFrac(BaseConstraints):
    """
    Objective function to enforce volume fraction constraint in SIMP material optimization.
    """

    def __init__(self, volfrac_min: float, volfrac_max: float, penalty: float = 1e0, element_name: str = 'C3D4') -> None:
        super().__init__()
        self.volfrac_min = float(volfrac_min)
        self.volfrac_max = float(volfrac_max)
        self.penalty = float(penalty)
        self.element_name = element_name

        self.gaussian_points: torch.Tensor | None = None
        self.gaussian_weights: torch.Tensor | None = None

        self._indices: torch.Tensor | None = None
        self._weights: torch.Tensor | None = None


    def initialize(self, material_params: SIMP_BSPFieldMaterials, *args, **kwargs):
        part = morphopt.controller.objfun.fe.assembly.get_part(material_params.part_name)
        elems = part.elems[self.element_name]
        self.gaussian_points = elems.get_gaussian_points(part.nodes).reshape(-1, 3)
        self.gaussian_weights = elems.gaussian_weight.flatten()

        self._indices, self._weights = material_params._get_indices_weight_for_nodes(self.gaussian_points)




    def __call__(self, material_params: SIMP_BSPFieldMaterials, *args, **kwargs):
        
        
        num_pts = self.gaussian_points.shape[0]
        designfield = torch.zeros([num_pts, 1], dtype=material_params._cps.dtype, device=self.gaussian_points.device)
        designfield[:, 0].scatter_add_(0, self._indices[0], self._weights * material_params._cps[self._indices[1], 0])
        ratio_now = 1 / (1 + torch.exp(-designfield)).flatten()

        volume_fraction = (ratio_now * self.gaussian_weights).sum() / self.gaussian_weights.sum()

        min_loss = self.penalty * (torch.clamp(self.volfrac_min - volume_fraction, min=0.0)) ** 2
        max_loss = self.penalty * (torch.clamp(volume_fraction - self.volfrac_max, min=0.0)) ** 2
        return min_loss + max_loss
