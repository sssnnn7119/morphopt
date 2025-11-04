

import numpy as np
import torch
from FEA.assemble.loads.base import BaseLoad

class BaseLoadInterface:
    """
    Base class for load interfaces.
    This class is not meant to be instantiated directly.
    It provides a common interface for all load interfaces.

    all data cannot be cuda tensors
    """

    def __init__(self):
        """
        Initialize the base interface and optional parameters.
        """

        self._values: list[float] = np.zeros(self.num_values).tolist()
        """List of load parameter values."""

    @property
    def num_values(self) -> int:
        """
        Get the number of load variables.

        Returns:
            int: The number of load variables.
        """
        return 0
    
    def get_fea_load(self) -> BaseLoad:
        """
        Get the load object for FEA.

        Returns:
            BaseLoad: The load object for FEA.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")
    
    def apply_load(self, load_fea: BaseLoad) -> None:
        """
        Apply the load to the FEA load object based on the given parameters.

        Args:
            params (list[float]): Load parameters.
            load_fea (BaseLoad): The FEA load object to apply the load to.
        """
        pass
