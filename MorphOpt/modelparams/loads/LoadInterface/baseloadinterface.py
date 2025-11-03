

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

    @property
    def num_variables(self) -> int:
        """
        Get the number of load variables.

        Returns:
            int: The number of load variables.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")
    
    def get_fea_load(self) -> BaseLoad:
        """
        Get the load object for FEA.

        Returns:
            BaseLoad: The load object for FEA.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")

    def update_variables(self, x_change: torch.Tensor) -> None:
        """
        Update the load variables based on the given change.

        :param x_change: Change in load variables.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")
    
    def get_parameters(self) -> torch.Tensor:
        """
        Get the current load parameters.

        Returns:
            torch.Tensor: The current load parameters.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")
    
    def set_parameters(self, xlist: torch.Tensor) -> None:
        """
        Set the load parameters based on the given list.

        Args:
            xlist (torch.Tensor): 
        """
        raise NotImplementedError("This method should be implemented in subclasses.")
    
    def save(self, filename: str) -> None:
        """
        Save the surface data to a file.

        Parameters:
            filename (str): The name of the file to save the surface data.
        """
        pass

    def load(self, filename: str) -> None:
        """
        Load the surface data from a file.

        Parameters:
            filename (str): The name of the file to load the surface data from.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")
    
    def plot(self, *args, **kwargs) -> None:
        """
        Plot the surface.

        Parameters:
            alpha (float): The transparency of the surface.
            color (tuple[float, float, float]): The color of the surface.
        """
        pass