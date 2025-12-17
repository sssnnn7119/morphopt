from FEA import FEAController
import torch
from .basefeainterface import BaseFEAInterface

from FEA.assemble.loads.body_force import BodyForce


class BodyforceInterface(BaseFEAInterface):
    """
    Body fclass Bodyforce) load interface.

    Values (list[float], length=3):
    - [0] fx
    - [1] fy
    - [2] fz
    """

    def __init__(self, element_name: str, instance_name: str = 'final_model'):
        """
        Initializclass BodyforceInterface class.
        """
        super().__init__()
        self.instance_name = instance_name
        self.element_name = element_name

    @property
    def force_density(self) -> list[float]:
        """
        Get the force density values.

        Returns:
            list[float]: The force density values [fx, fy, fz].
        """
        return self._values
    
    @force_density.setter
    def force_density(self, value: list[float]) -> None:
        """
        Set the force density values.

        Args:
            value (list[float]): The new force density values [fx, fy, fz].
        """
        if len(value) != 3:
            raise ValueError("Force density must be a list of 3 floats.")
        self._values = [float(v) for v in value]

    @property
    def num_values(self) -> int:
        """
        Get the number of variables.

        Returns:
            int: The number of variables (3 for fx, fy, fz).
        """
        return 3
    
    def modify_fea(self, fe: FEAController, name: str) -> None:
        body_force = BodyForce(instance_name=self.instance_name, element_name=self.element_name, force_density=self.force_density)
        fe.assembly.add_load(body_force, name)
    
    def apply_fea_value(self, fe: FEAController, name: str) -> None:
        body_force: BodyForce = fe.assembly.get_load(name)
        device = body_force.force_density.device
        body_force.force_density = torch.tensor(self.force_density, dtype=torch.float64, device=device)
        
        # Update cached values if initialized
        if hasattr(body_force, '_element'):
            body_force._pdU_values = torch.einsum('i, ge, gea->eai', body_force.force_density, body_force._element.gaussian_weight, body_force._element.shape_function_d0_gaussian).flatten()

	