import torch
from ..base_params import BaseParams
import numpy as np
import os
from ... import GLOBAL
from mayavi import mlab

class Materials(BaseParams):
    """
    Class to handle the materials of the morphable model.
    """

    def __init__(self, mu: float, kappa: float, density: float) -> None:
        """
        Initialize the Materials class.

        Args:
            mu (float): The shear modulus of the material.
            kappa (float): The bulk modulus of the material.
        """
        super().__init__()
        self.mu = torch.tensor(mu)
        self.kappa = torch.tensor(kappa)
        self.density = torch.tensor(density)

    def get_modules(self, nodes: torch.Tensor = None) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Get the modules of the materials.

        Args:
            nodes (torch.Tensor): The nodes of the morphable model.

        Returns:
            torch.Tensor: The modules of the materials.
        """
        return self.mu, self.kappa

    def get_density(self, nodes: torch.Tensor = None) -> torch.Tensor:
        """
        Get the density of the materials.

        Args:
            nodes (torch.Tensor): The nodes of the morphable model.
                size: (N, 3) where N is the number of nodes.

        Returns:
            torch.Tensor: The density of the materials.
        """
        return self.density

    def get_ratio(self, nodes: torch.Tensor) -> float:
        """
        Get the ratio of maximum to minimum modulus.
        
        Returns:
            float: The ratio of maximum to minimum modulus.
        """
        return 1.0
