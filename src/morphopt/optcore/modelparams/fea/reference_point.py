from torchfea import FEAController
from torchfea.model import ReferencePoint as TorchFEAReferencePoint

from .base_component import BaseFEAComponent


class ReferencePoint(BaseFEAComponent):
    """Register a reference point at the specified global coordinates."""

    def __init__(self, rp_location: list[float]) -> None:
        """Initialize ReferencePoint and its configuration state.

        Args:
            rp_location (list[float]): Reference-point Cartesian coordinates [x, y, z] in model
                length units.
        """
        self.rp_location = rp_location
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
        rp = TorchFEAReferencePoint(node=self.rp_location)
        fe.assembly.add_reference_point(rp, name)
