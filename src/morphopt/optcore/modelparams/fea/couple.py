from torchfea import FEAController
from torchfea.model.constraints import Couple as TorchFEACouple

from .base_component import BaseFEAComponent


class Couple(BaseFEAComponent):
    """Kinematically couple an instance node set to a reference point."""

    def __init__(self, rp_name: str, instance_name: str, set_nodes_name: str) -> None:
        """Initialize Couple and its configuration state.

        Args:
            rp_name (str): Registered reference-point name.
            instance_name (str): Registered Instance name in the assembly.
            set_nodes_name (str): Named node set on the selected instance.
        """
        self.rp_name = rp_name
        self.instance_name = instance_name
        self.set_nodes_name = set_nodes_name
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
        loadobj = TorchFEACouple(
            instance_name=self.instance_name,
            set_nodes_name=self.set_nodes_name,
            rp_name=self.rp_name,
        )
        fe.assembly.add_constraint(loadobj, name)
