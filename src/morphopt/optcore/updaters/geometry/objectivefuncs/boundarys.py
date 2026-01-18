
import torch
from .basefuncs import BaseConstraints


class MinRadius(BaseConstraints):
    """
    Cylinder boundary objective function for MorphOpt.
    """

    def __init__(self, radius: float) -> None:
        """
        Initialize the Cylinder objective function.
        """
        super().__init__()

        self._radius = radius
        """
        The radius of the cylinder.
        """


    def __call__(self, r, rdu, rdu2, *args, **kwargs):
        
        thre = 0.05
        degree = 3
        
        loss = torch.zeros(1, device=r[0].device, dtype=r[0].dtype)
        for i in range(len(r)):
            
            length_r = -(r[i][:, 0]**2 + r[i][:, 1]**2).sqrt() + self._radius
            
            index_r, loss_r = self.barrier_function(length_r, thre, 0., degree)

            
            if len(index_r) > 0:
                loss = loss + (self.scaler[i][index_r] * loss_r).sum()
            
        return loss
    

class Cylinder(BaseConstraints):
    """
    Cylinder boundary objective function for MorphOpt.
    """

    def __init__(self, radius: float, height: float, bottom: float) -> None:
        """
        Initialize the Cylinder objective function.
        """
        super().__init__()

        self._radius = radius
        """
        The radius of the cylinder.
        """
        
        self._height = height + 1
        """
        The height of the cylinder.
        """
        
        self._bottom = bottom - 1
        """
        The bottom of the cylinder.
        """

    def __call__(self, r, rdu, rdu2, *args, **kwargs):
        
        thre = 0.05
        degree = 3
        
        loss = torch.zeros(1, device=r[0].device, dtype=r[0].dtype)
        for i in range(len(r)):
            
            length_r = (r[i][:, 0]**2 + r[i][:, 1]**2).sqrt() - self._radius
            length_bottom = -r[i][:, 2] + self._bottom
            length_top = r[i][:, 2] - self._height
            
            index_r, loss_r = self.barrier_function(length_r, thre, 0., degree)
            index_bottom, loss_bottom = self.barrier_function(length_bottom, thre, 0., degree)
            index_top, loss_top = self.barrier_function(length_top, thre, 0., degree)
            
            if len(index_r) > 0:
                loss = loss + (self.scaler[i][index_r] * loss_r).sum()
            if len(index_bottom) > 0:
                loss = loss + (self.scaler[i][index_bottom] * loss_bottom).sum()
            if len(index_top) > 0:
                loss = loss + (self.scaler[i][index_top] * loss_top).sum()
            
        return loss