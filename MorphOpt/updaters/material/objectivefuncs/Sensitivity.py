import torch
from .BaseObj import BaseObj
from ....modelparams import BsplineMaterials

class Sensitivity(BaseObj):
    """
    Sensitivity objective function for MorphOpt.
    This class calculates the sensitivity of the objective function with respect to the design variables.
    """

    def __init__(self, materials: BsplineMaterials):
        """
        Initialize the sensitivity objective function.

        Args:
            loads (Loads): The loads object that contains the pressure values.
        """
        self.sensitivity: torch.Tensor = None
        """
        The sensitivity tensor that will be used to calculate the sensitivity of the objective function."""
        
        self.ratio0: torch.Tensor = None
        """the initial ratio of the material properties."""
        
        self.points_request: torch.Tensor = None
        """The nodes tensor that will be used to calculate the sensitivity of the objective function."""
        
        self.materials = materials
        """
        The materials object that contains the material properties.
        """
        
    def initialize(self, points_request: torch.Tensor, sensitivity: torch.Tensor, *args, **kwargs):
        self.sensitivity = sensitivity
        self.points_request = points_request
        
        self.ratio0 = self.materials.get_ratio(self.points_request).detach().clone()


    def __call__(self, *args, **kwargs) -> float:
        """
        Calculate the sensitivity of the objective function.

        Args:
            U (torch.Tensor): The displacement tensor.
            Udp (torch.Tensor): The displacement tensor for the design variables.

        Returns:
            float: The sensitivity value.
        """
        
        return ((self.materials.get_ratio(self.points_request) - self.ratio0) * self.sensitivity).sum()