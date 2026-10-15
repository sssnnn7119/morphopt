

import numpy as np
from torchfea import FEAController

from ..base_model_component import BaseModelComponent


class BaseFEAComponent(BaseModelComponent):
    """
    Base class for FEA components.
    This class is not meant to be instantiated directly.
    It provides common load, boundary and contact declaration state.

    all data cannot be cuda tensors
    """

    def __init__(self):
        """
        Initialize the component and its per-step values.
        """
        super().__init__()

        self._values: list[float] = np.zeros(self.num_values).tolist()
        """List of fea parameter values."""

        self._name: str = ""
        """Name assigned by the owning FEAParams collection."""

    @property
    def name(self) -> str:
        """Name assigned when this component is registered."""
        if not self._name:
            raise ValueError(
                f"{type(self).__name__} has no name yet; register it with "
                "FEAParams.add_interface(...)."
            )
        return self._name

    @property
    def num_values(self) -> int:
        """
        Get the number of fea variables.

        Returns:
            int: The number of fea variables.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")
    
    def modify_fea(self, fe: FEAController, name: str) -> None:
        """
        create the object in FEA assembly

        Args:
            fe (FEAController): The FEA controller instance.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")
    
    def apply_fea_value(self, fe: FEAController, name: str) -> None:
        """
        Apply the values to the FEA object.
        """
        pass
