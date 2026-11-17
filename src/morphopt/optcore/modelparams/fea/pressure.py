from torchfea import FEAController
from torchfea.model.loads import Pressure as TorchFEAPressure

from .base_component import BaseFEAComponent


class Pressure(BaseFEAComponent):
    """
    Surface pressure load interface.

    Values (list[float], length=1):
    - [0] pressure (scalar)
    """

    def __init__(self, surface_name: str, instance_name: str = "final_model"):
        """Initialize the Pressure class with default values.

        Args:
            surface_name (str): Named surface set on the selected instance.
            instance_name (str): Registered Instance name in the assembly.
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

    def modify_fea(self, fe: FEAController, name: str) -> None:
        """Create and register this declaration in the finite-element assembly.

        Args:
            fe (FEAController): TorchFEA controller whose assembly is modified or solved.
            name (str): Name identifying the item in its owning collection.
        """
        pressure_load = TorchFEAPressure(
            instance_name=self.instance_name,
            surface_set=self.surface_name,
            pressure=self.pressure,
        )
        fe.assembly.add_load(pressure_load, name)

    def apply_fea_value(self, fe: FEAController, name: str) -> None:
        """Apply this load case's parameter values to the registered FE component.

        Args:
            fe (FEAController): TorchFEA controller whose assembly is modified or solved.
            name (str): Name identifying the item in its owning collection.
        """
        pressure_load: TorchFEAPressure = fe.assembly.get_load(name)
        pressure_load.pressure = self.pressure
