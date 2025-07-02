
import numpy as np
import torch


from FEA.FEA_INP import FEA_INP
from FEA.Main import loads
from ..base_params import BaseParams
from ... import GLOBAL

class Loads(BaseParams):
    """
    Class to handle the loads in the model.
    """
    from .LoadInterface.Pressures import Pressures
    def __init__(self):
        """
        Initialize the Loads class.
        """
        self.pressure: Loads.Pressures
        """
        Pressures: An instance of the Pressures class from the ModelParams module.
        """

    def get_params_range_pressure(self) -> np.ndarray:
        """
        Get the range of pressure parameters.

        Returns:
            np.ndarray: The range of pressure parameters.
        """
        return np.arange(0, self.pressure.num_variables, 1)

    def get_parameters(self) -> list[torch.Tensor]:
        """
        Get the pressure parameters.

        Returns:
            list[torch.Tensor]: The pressure parameters.
        """

        params = [self.pressure.get_parameters().flatten().detach().clone()]
        return params
    
    def set_parameters(self, xlist: list[torch.Tensor]) -> None:
        """
        Set the pressure parameters.

        Args:
            xlist (list[torch.Tensor]): The new pressure parameters.
        """
        self.pressure.set_parameters(xlist=xlist[0].detach().clone())

    def get_variables(self) -> torch.Tensor:
        """
        Get the pressure variables.

        Returns:
            torch.Tensor: The pressure variables.
        """
        xlist = self.get_parameters()
        x_flatten = torch.cat([torch.randn_like(xlist[i].flatten())*1e-6 for i in range(len(xlist))])
        return x_flatten
    
    def update_variables(self, x_change: torch.Tensor) -> None:
        """
        Update the pressure variables.

        Args:
            x_change (torch.Tensor): The change in pressure variables.
        """
        ind_now = 0

        # Update pressure variables
        num_pressure = self.pressure.num_variables
        self.pressure.update_variables(x_change=x_change[ind_now:ind_now + num_pressure])
        ind_now += num_pressure

    def save(self, filepath) -> None:
        """
        Save the loads to a file.
        """
        self.pressure.save(filename= filepath + '/Pressure_%d'% GLOBAL.History.iteration)

    def load(self, filepath: str, iteration: int) -> None:
        """
        Load the loads from a file.

        Args:
            filepath (str): The path to the file.
            iteration (int): The iteration number.
        """
        self.pressure.load(filename=filepath + '/Pressure_%d'% iteration)
        
    def plot(self):
        self.pressure.plot()
        
    def save_figure(self, filepath):
        from matplotlib import pyplot as plt
        
        plt.figure()
        self.plot()
        plt.savefig(filepath + '/Pressure_%d.png'% GLOBAL.History.iteration)
        plt.close()