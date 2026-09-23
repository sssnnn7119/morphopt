

import numpy as np
from torchfea import FEAController

from ...protocal import (
    ProtocalInitializable,
    ProtocalSavable,
    ProtocalVisualizable,
)


class BaseFEAInterface(
    ProtocalInitializable,
    ProtocalSavable,
    ProtocalVisualizable,
):
    """
    Base class for fea interfaces.
    This class is not meant to be instantiated directly.
    It provides a common interface for all fea interfaces.

    all data cannot be cuda tensors
    """

    def __init__(self):
        """
        Initialize the base interface and optional parameters.
        """
        super().__init__()

        self._values: list[float] = np.zeros(self.num_values).tolist()
        """List of fea parameter values."""

        self._name: str = ""
        """Name of the interface."""

    @property
    def name(self) -> str:
        """Name assigned when this interface is registered."""
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
