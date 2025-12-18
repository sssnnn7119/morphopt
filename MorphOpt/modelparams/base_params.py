

import torch


class BaseParams:
    """
    Base class for all parameter classes.
    """
    def __init__(self, **kwargs):
        """
        Initialize the parameters with the given keyword arguments.
        """
        self.__dict__.update(kwargs)

    def __repr__(self):
        """
        Return a string representation of the parameters.
        """
        return f"{self.__class__.__name__}({self.__dict__})"

    def __str__(self):
        """
        Return a string representation of the parameters.
        """
        return self.__repr__()
    
    def reinitialize(self, iteration: int, *args, **kwargs) -> None:
        """
        reInitialize the parameters.
        
        This method should be implemented in subclasses to initialize specific parameters.
        """
        pass

    def initialize(self, *args, **kwargs) -> None:
        """
        Initialize the parameters.
        
        This method should be implemented in subclasses to initialize specific parameters.
        """
        pass
    
    def get_variables(self) -> torch.Tensor:
        """
        Get the zeros of the parameters.
        
        Returns:
            torch.Tensor: The variables of the parameters.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")
    
    def update_variables(self, x_change: torch.Tensor) -> None:
        """
        Update the variables of the class.
        
        Args:
            x_change (torch.Tensor): The change in variables.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")
    
    def set_parameters(self, xlist: list[torch.Tensor]) -> None:
        """
        Set the parameters of the class.
        the new parameters are expected to be in a flattened format with clone and detach.
        
        Args:
            xlist (list[torch.Tensor]): The new parameters for the class.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")
    
    def get_parameters(self) -> list[torch.Tensor]:
        """
        Get the parameters of the class.
        the parameters are expected to be in a flattened format with clone and detach.
        
        Returns:
            list[torch.Tensor]: The parameters of the class.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")

    def save(self, foldpath: str) -> None:
        """
        Save the parameters to a file.
        
        Args:
            foldpath (str): The name of the file to save the parameters to.
        """
        pass

    def load(self, foldpath: str, iteration: int) -> None:
        """
        Load the parameters from a file.
        
        Args:
            foldpath (str): The name of the file to load the parameters from.
            iteration (int): The iteration number to load.
        """
        pass
    
    def plot(self) -> None:
        """
        Plot the parameters.
        
        This method should be implemented in subclasses to plot specific parameters.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")
    
    def save_figure(self, filename: str) -> None:
        """
        Save the figure of the parameters to a file.
        
        Args:
            filename (str): The name of the file to save the figure to.
        """
        pass

    def _export_data(self, foldpath: str):
        """
        Export the data of parameters to file(s).
        
        Args:
            foldpath (str): The path to export the data.
        """
        pass