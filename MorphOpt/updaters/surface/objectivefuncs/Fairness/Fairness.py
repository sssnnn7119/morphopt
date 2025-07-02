import torch
from ..BaseObj import BaseObj
from .....modelparams import Surfaces

class Fairness(BaseObj):
    """
    Fairness objective function for MorphOpt.
    """

    def __init__(self, surfaces: Surfaces):
        """
        Initialize the fairness objective function with a name.
        """
        super().__init__()
        self.surfaces = surfaces
        """
        The surfaces object that contains the design variables.
        """


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
        return sum(self.surfaces.get_penalty_fairness(weight, r, rdu, rdu2))