import torch
from .BaseObj import BaseObj
from ....modelparams import BsplineMaterials

class VolumePanelty(BaseObj):
    """Volume penalty objective function for MorphOpt.
    This class calculates the volume penalty based on the material properties and design variables.
    """

    def __init__(self, materials: BsplineMaterials, factor: float = 1e-10):
        """
        Initialize the volume penalty objective function.

        Args:
            factor (float): The penalty factor for the volume.
        """
        super().__init__()
        self.factor = factor
        """
        The penalty factor for the volume.
        Makes the material decrease when the sensitivity is zero.
        """

        self.materials = materials
        """The materials object that contains the material properties.
        """


    def __call__(self, *args, **kwargs) -> float:
        """
        Calculate the sensitivity of the objective function.

        Args:
            U (torch.Tensor): The displacement tensor.
            Udp (torch.Tensor): The displacement tensor for the design variables.

        Returns:
            float: The sensitivity value.
        """
        
        return self.materials.bspline.control_points.sum() * self.factor