from operator import index
import torch

from torchfea import FEAController
from .basefeainterface import BaseFEAInterface
from torchfea.model.constraints import Couple


class CoupleInterface(BaseFEAInterface):
    """
    Nonlinear axial spring connecting a reference point to a fixed ground point.
    Values order (5 floats): [k, L0, Px, Py, Pz]
            k: stiffness
            L0: rest length
            P*: ground point coordinates
    """

    def __init__(self, rp_name: str, instance_name: str, set_nodes_name: str) -> None:
        self.rp_name = rp_name
        self.instance_name = instance_name
        self.set_nodes_name = set_nodes_name
        super().__init__()

    @property
    def num_values(self) -> int:
        return 0

    def modify_fea(self, fe: FEAController, name: str) -> None:
        loadobj = Couple(instance_name=self.instance_name, set_nodes_name=self.set_nodes_name, rp_name=self.rp_name)
        fe.assembly.add_constraint(loadobj, name)

