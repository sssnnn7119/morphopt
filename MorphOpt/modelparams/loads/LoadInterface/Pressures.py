
import numpy as np
import torch
from .BaseInterface import BaseInterface

class Pressures(BaseInterface):
    """
    Class to hold the pressure values for the MorphOpt model.
    """

    def __init__(self):
        """
        Initialize the Pressures class with default values.
        """
        self.pressure: torch.Tensor = torch.tensor([[0.0]])
        """
        pressure: A 2D list to hold the pressure values.
        """

        self.max_step_length: float = 0.005

    @property
    def num_variables(self) -> int:
        """
        Get the number of pressure variables.

        Returns:
            int: The number of pressure variables.
        """
        return self.pressure.numel()

    def get_pressure(self) -> torch.Tensor:
        """
        Get the pressure values.

        Returns:
            torch.Tensor: The pressure values.
        """
        return self.pressure
    
    def get_parameters(self) -> torch.Tensor:
        """
        Get the pressure parameters.

        Returns:
            torch.Tensor: The pressure parameters.
        """
        return self.pressure.clone()
    
    def set_parameters(self, xlist: torch.Tensor) -> None:
        """
        Set the pressure parameters.

        Args:
            xlist (torch.Tensor): The new pressure parameters.
        """
        self.pressure = xlist.reshape(self.pressure.shape).detach().clone()

    def update_variables(self, x_change):

        delta_p = 2/torch.pi * torch.atan(x_change) * self.max_step_length

        self.pressure += delta_p.reshape(self.pressure.shape)

    def save(self, filename: str) -> None:
        """
        Save the pressure data to a file.

        Parameters:
            filename (str): The name of the file to save the pressure data.
        """
        np.savetxt(filename+".txt", self.get_parameters().cpu().numpy(), delimiter=",")
    
    def load(self, filename: str) -> None:
        """
        Load the pressure data from a file.

        Parameters:
            filename (str): The name of the file to load the pressure data from.
        """
        data = np.loadtxt(filename+".txt", delimiter=",").tolist()
        self.set_parameters(torch.tensor(data))
        
    def plot(self):
        """
        Plot the pressure data.
        """
        from matplotlib import pyplot as plt
        pressure_list = self.get_pressure().cpu().numpy()
        x = np.linspace(0, 1, pressure_list.shape[1])
        for i in range(pressure_list.shape[0]):
            plt.plot(x, pressure_list[i, :], label=f'Pressure {i}')
            plt.scatter(x, pressure_list[i, :], s=10)