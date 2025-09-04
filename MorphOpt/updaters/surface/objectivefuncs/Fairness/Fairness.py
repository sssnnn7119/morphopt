import torch
from ..BaseObj import BaseObj
from .....modelparams import Surfaces
from .. import ShapeDerivativePneumatic
class Fairness(BaseObj):
    """
    Fairness objective function for MorphOpt.
    """

    def __init__(self, surfaces: Surfaces, sensitivity: ShapeDerivativePneumatic):
        """
        Initialize the fairness objective function with a name.
        """
        super().__init__()
        self.surfaces = surfaces
        """
        The surfaces object that contains the design variables.
        """

        self.scaler: list[torch.Tensor]
        """
        the scaler to process
        """

        self.sensitivity = sensitivity
        """the sensitivity to anchor the scaler"""

    def initialize(self, weight: list[torch.Tensor], *args, **kwargs):
        
        self.scaler = []
        for i in range(len(self.sensitivity.sensitivity)):
            sen_now = self.sensitivity.sensitivity[i].abs()
            sen_now[sen_now==0] = sen_now[sen_now!=0].min()
            self.scaler.append(weight[i] * sen_now)


    def __call__(self, weight: list[torch.Tensor], r: list[torch.Tensor], rdu: list[torch.Tensor], rdu2: list[torch.Tensor], *args, **kwargs) -> float:
        """
        Call the fairness objective function.

        Args:
            weight (list[torch.Tensor]): The weights for each point.
            r (list[torch.Tensor]): The point coordinates of the surfaces.
            rdu (list[torch.Tensor]): The partial derivatives of the surfaces.
            rdu2 (list[torch.Tensor]): The second partial derivatives of the surfaces.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            The value of the fairness objective function.
        """


        # Implement the fairness objective function here
        return sum(self.surfaces.get_penalty_fairness(self.scaler, r, rdu, rdu2))