
import numpy as np
import torch
from .baseloadinterface import BaseLoadInterface
from FEA.assemble.loads.pressure import Pressure
class PressureInterface(BaseLoadInterface):
    """
    Class to hold the pressure values for the MorphOpt model.
    """

    def __init__(self, surface_name: str, instance_name: str = 'final_model'):
        """
        Initialize the PressureInterface class with default values.
        """
        super().__init__()
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
        return float(self._values[0])
    
    @pressure.setter
    def pressure(self, value: float) -> None:
        """
        Set the pressure values.

        Args:
            value (float): The new pressure value.
        """
        self._values = [float(value)]

    @property
    def num_values(self) -> int:
        """
        Get the number of pressure variables.

        Returns:
            int: The number of pressure variables.
        """
        return 1
    
    def get_fea_load(self):
        pressure_load = Pressure(instance_name=self.instance_name,surface_set=self.surface_name,pressure=self.pressure)
        return pressure_load
    
    def apply_load(self, load_fea: Pressure):
        load_fea.pressure = self.pressure
