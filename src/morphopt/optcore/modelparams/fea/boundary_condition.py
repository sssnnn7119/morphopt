from copy import deepcopy

from ....constants import CONSTANT
from torchfea import FEAController
from .base_component import BaseFEAComponent
from torchfea.model.boundarys import Boundary_Condition, Boundary_Condition_RP


class BoundaryCondition(BaseFEAComponent):
    """Fix the selected translation degrees of freedom of an instance node set."""

    def __init__(
        self,
        instance_name: str,
        set_nodes_name: str,
        index_dof: list[int] | None = None,
    ) -> None:
        """Initialize BoundaryCondition and its configuration state.

        Args:
            instance_name (str): Registered Instance name in the assembly.
            set_nodes_name (str): Named node set on the selected instance.
            index_dof (list[int] | None): Zero-based degree-of-freedom indices; translations use 0–2
                and reference-point rotations use 3–5.
        """
        self.instance_name = instance_name
        self.set_nodes_name = set_nodes_name
        self.index_dof = list(
            deepcopy(CONSTANT.KERNEL.FEA.DEFAULT_TRANSLATION_DOFS)
            if index_dof is None
            else index_dof
        )
        super().__init__()

    @property
    def num_values(self) -> int:
        """Return the number of load parameters supplied by each load case.

        Returns:
            int: Number of scalar load-case parameters exposed by this component.
        """
        return 0

    def modify_fea(self, fe: FEAController, name: str) -> None:
        """Create and register this declaration in the finite-element assembly.

        Args:
            fe (FEAController): TorchFEA controller whose assembly is modified or solved.
            name (str): Name identifying the item in its owning collection.
        """
        bcobj = Boundary_Condition(instance_name=self.instance_name, set_nodes_name=self.set_nodes_name, indexDoF=self.index_dof)
        fe.assembly.add_boundary(bcobj, name)


class ReferencePointBoundaryCondition(BaseFEAComponent):
    """
    Fix selected reference-point degrees of freedom.

    Indices 0–2 select translations and 3–5 select rotations. This component
    has no load-case parameters; the selected degrees of freedom remain fixed.
    """

    def __init__(
        self, rp_name: str, index_dof: list[int] | None = None
    ) -> None:
        """Initialize ReferencePointBoundaryCondition and its configuration state.

        Args:
            rp_name (str): Registered reference-point name.
            index_dof (list[int] | None): Zero-based degree-of-freedom indices; translations use 0–2
                and reference-point rotations use 3–5.
        """
        self.rp_name = rp_name
        self.index_dof = list(
            deepcopy(CONSTANT.KERNEL.FEA.DEFAULT_TRANSLATION_DOFS)
            if index_dof is None
            else index_dof
        )
        super().__init__()

    @property
    def num_values(self) -> int:
        """Return the number of load parameters supplied by each load case.

        Returns:
            int: Number of scalar load-case parameters exposed by this component.
        """
        return 0

    def modify_fea(self, fe: FEAController, name: str) -> None:
        """Create and register the RP boundary condition in the FE assembly.

        Args:
            fe (FEAController): TorchFEA controller whose assembly is modified or solved.
            name (str): Name identifying the item in its owning collection.
        """
        bcobj = Boundary_Condition_RP(rp_name=self.rp_name, indexDoF=self.index_dof)
        fe.assembly.add_boundary(bcobj, name)


