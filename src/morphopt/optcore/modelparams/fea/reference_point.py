from operator import index
import torch

from torchfea import FEAController
from .base_component import BaseFEAComponent
from torchfea.model import ReferencePoint as TorchFEAReferencePoint


class ReferencePoint(BaseFEAComponent):
    """
    Nonlinear axial spring connecting a reference point to a fixed ground point.
    Values order (5 floats): [k, L0, Px, Py, Pz]
            k: stiffness
            L0: rest length
            P*: ground point coordinates
    """

    def __init__(self, rp_location: list[float]) -> None:
        self.rp_location = rp_location
        super().__init__()

    @property
    def num_values(self) -> int:
        return 0

    def modify_fea(self, fe: FEAController, name: str) -> None:
        rp = TorchFEAReferencePoint(node=self.rp_location)
        fe.assembly.add_reference_point(rp, name)

