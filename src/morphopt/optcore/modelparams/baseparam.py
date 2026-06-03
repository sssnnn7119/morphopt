import torch
import torchfea
import pyvista as pv
from ..baseobject import BaseObject


class BaseParams(BaseObject):
    """
    Base class for all parameter classes including geometry, feamodel, and materials.
    """
    def __init__(self, **kwargs):
        """
        Initialize the parameters with the given keyword arguments.
        """

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
        return torch.zeros(0)
    
    def update_variables(self, x_change: torch.Tensor) -> None:
        """
        Update the variables of the class.
        
        Args:
            x_change (torch.Tensor): The change in variables.
        """
        pass
    
    def set_parameters(self, xlist: list[torch.Tensor]) -> None:
        """
        Set the parameters of the class.
        the new parameters are expected to be in a flattened format with clone and detach.
        
        Args:
            xlist (list[torch.Tensor]): The new parameters for the class.
        """
    
    def get_parameters(self) -> list[torch.Tensor]:
        """
        Get the parameters of the class.
        the parameters are expected to be in a flattened format with clone and detach.
        
        Returns:
            list[torch.Tensor]: The parameters of the class.
        """
        return []
    
    def plot(self, plotter: pv.Plotter = None, meshes: list[pv.DataSet] = None) -> pv.Plotter:
        """
        Plot the parameters.
        
        This method should be implemented in subclasses to plot specific parameters.
        
        Args:
            plotter (pv.Plotter, optional): An optional PyVista Plotter object to use for plotting. If None, a new Plotter will be created. Defaults to None.
            meshes (list[pv.DataSet], optional): An optional list of PyVista DataSet objects to plot. Defaults to None.

        Returns:
            pv.Plotter: The PyVista Plotter object used for plotting.
        """
        if plotter is None:
            plotter = pv.Plotter()

        return plotter
    
    def get_meshes(self):
        """Get the meshes associated with the geometry."""
        return []


    def _export_data(self, foldpath: str):
        """
        Export the data of parameters to file(s).
        
        Args:
            foldpath (str): The path to export the data.
        """
        pass

    def obtain_design_sensitivity_vars(self, *args, **kwargs) -> torch.Tensor:
        """
        Obtain the design sensitivity variables for the optimization problem.
        
        This method should be implemented in subclasses to obtain specific design sensitivity variables.
        
        Returns:
            torch.Tensor: The design sensitivity variables.
        """
        return torch.zeros(0)

    def modify_assembly(self, design_sensitivity_vars: torch.Tensor, assembly: torchfea.Assembly) -> None:
        """
        Modify the assembly for sensitivity analysis.
        the design_sensitivity_vars will be defined in the subclasses, and the assembly will be modified according to the design_sensitivity_vars.

        Args:
            design_sensitivity_vars (torch.Tensor): The design sensitivity variables.
            assembly (Assembly): The assembly to modify.
        """
        pass
