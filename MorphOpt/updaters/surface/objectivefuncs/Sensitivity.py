import torch
from .BaseObj import BaseObj

class Sensitivity(BaseObj):
    """
    Sensitivity objective function for MorphOpt.
    """

    def __init__(self):
        """
        Initialize the Sensitivity objective function with a name.
        """
        super().__init__()
        
        self.sensitivity: list[torch.Tensor] = []
        """
        the sensivities of the surfaces.
        """
        
        self.R0: list[torch.Tensor] = []
        """
        The initial point coordinates of the surfaces.
        """
        
        self.normal0: list[torch.Tensor] = []
        """
        The normal vectors of the surfaces.
        """
        
    def initialize(self, r0: list[torch.Tensor], rdu0: list[torch.Tensor], sensitivity: list[torch.Tensor], *args, **kwargs) -> None:
        """
        Set the sensivities of the surfaces.

        Args:
            sensivities (list[torch.Tensor]): The sensivities of the surfaces.
            r (list[torch.Tensor]): The point coordinates of the surfaces.
            rdu (list[torch.Tensor]): The partial derivatives of the surfaces.
        """
        self.sensitivity = sensitivity
        
        self.R0 = [r0[i].detach().clone() for i in range(len(r0))]

        
        self.normal0 = []
        for i in range(len(r0)):
            normal_vector = torch.cross(rdu0[i][:, 1], rdu0[i][:, 0], dim=0)
            normal_vector /= normal_vector.norm(dim=0)
            self.normal0.append(normal_vector.detach().clone())


    def __call__(self, weight: list[torch.Tensor], r: list[torch.Tensor], rdu: list[torch.Tensor], rdu2: list[torch.Tensor]) -> float:
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
        loss_objective = 0.0
        
        for i in range(len(weight)):

            normal_velocity = ((r[i] - self.R0[i]) * self.normal0[i]).sum(dim=0)
            loss_objective += (normal_velocity * self.sensitivity[i] *
                            weight[i]).sum()
        
        return loss_objective