
import numpy as np
import torch
from .baseloadinterface import BaseLoadInterface
from FEA.assemble.loads.pressure import Pressure
class PressureInterface(BaseLoadInterface):
    """
    Class to hold the pressure values for the MorphOpt model.
    """

    def __init__(self, surface_name: str, pressure: float, instance_name: str = 'final_model'):
        """
        Initialize the PressureInterface class with default values.
        """
        self._pressure: float = pressure
        """
        pressure: A 2D list to hold the pressure values.
        """
        self.instance_name = instance_name
        """
        instance_name: The name of the instance.
        """
        self.surface_name = surface_name
        """
        surface_name: The name of the surface.
        """

    @property
    def pressure(self) -> float:
        """
        Get the pressure values.

        Returns:
            float: The pressure values.
        """
        return float(self._pressure)
    
    @pressure.setter
    def pressure(self, value: float) -> None:
        """
        Set the pressure values.

        Args:
            value (float): The new pressure value.
        """
        self._pressure = float(value)

    @property
    def num_variables(self) -> int:
        """
        Get the number of pressure variables.

        Returns:
            int: The number of pressure variables.
        """
        return 1
    
    def get_fea_load(self):
        pressure_load = Pressure(instance_name=self.instance_name,surface_set=self.surface_name,pressure=self.pressure)
        return pressure_load
    
    def get_parameters(self) -> torch.Tensor:
        """
        Get the pressure parameters.

        Returns:
            torch.Tensor: The pressure parameters.
        """
        return torch.tensor(self.pressure)
    
    def set_parameters(self, xlist: torch.Tensor) -> None:
        """
        Set the pressure parameters.

        Args:
            xlist (torch.Tensor): The new pressure parameters.
        """
        self.pressure = xlist.item()

    def update_variables(self, x_change):

        pass

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