from operator import index
import torch

from torchfea import FEAController
from .basefeainterface import BaseFEAInterface
from torchfea.model.boundarys import Boundary_Condition, Boundary_Condition_RP


class BoundaryConditionInterface(BaseFEAInterface):
    """
    Nonlinear axial spring connecting a reference point to a fixed ground point.
    Values order (5 floats): [k, L0, Px, Py, Pz]
            k: stiffness
            L0: rest length
            P*: ground point coordinates
    """

    def __init__(self, instance_name: str, set_nodes_name: str, index_dof: list[int] = [0, 1, 2]) -> None:
        self.instance_name = instance_name
        self.set_nodes_name = set_nodes_name
        self.index_dof = index_dof
        super().__init__()

    @property
    def num_values(self) -> int:
        return 0

    def modify_fea(self, fe: FEAController, name: str) -> None:
        bcobj = Boundary_Condition(instance_name=self.instance_name, set_nodes_name=self.set_nodes_name, indexDoF=self.index_dof)
        fe.assembly.add_boundary(bcobj, name)


class BoundaryConditionRPInterface(BaseFEAInterface):
    """
    Reference-point boundary condition (BCRP) interface.

    This interface creates a Boundary_Condition_RP on a reference point and
    allows updating the prescribed values per degree of freedom.

    - index_dof: list of DoF indices to prescribe (e.g. [0,1,2] for translations)
    - values: list of floats with the same length as index_dof representing the
      prescribed values for each specified DoF.
    """

    def __init__(self, rp_name: str, index_dof: list[int] = [0, 1, 2]) -> None:
        self.rp_name = rp_name
        self.index_dof = index_dof
        super().__init__()

    @property
    def num_values(self) -> int:
        return 0

    def modify_fea(self, fe: FEAController, name: str) -> None:
        """Create and register the RP boundary condition in the FE assembly."""
        bcobj = Boundary_Condition_RP(rp_name=self.rp_name, indexDoF=self.index_dof)
        fe.assembly.add_boundary(bcobj, name)


