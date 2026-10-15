
import torch
from ...constants import CONSTANT
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
        
        thre = CONSTANT.KERNEL.SHAPE_CONSTRAINTS.BARRIER_THRESHOLD
        degree = CONSTANT.KERNEL.SHAPE_CONSTRAINTS.MIN_RADIUS_EXPONENT
        
        loss = torch.zeros(1, device=r[0].device, dtype=r[0].dtype)
        for i in range(len(r)):

            if self.if_update is not None and not self.if_update[i]:
                continue
            
            length_r = -(r[i][:, 0]**2 + r[i][:, 1]**2).sqrt() + self._radius
            
            index_r, loss_r = self.barrier_function(
                length_r, thre, CONSTANT.KERNEL.SHAPE_CONSTRAINTS.BARRIER_RATIO, degree
            )

            
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
        
        self._height = height
        """
        The height of the cylinder.
        """
        
        self._bottom = bottom
        """
        The bottom of the cylinder.
        """

    def __call__(self, r, rdu, rdu2, *args, **kwargs):
        
        thre = CONSTANT.KERNEL.SHAPE_CONSTRAINTS.BARRIER_THRESHOLD
        degree = CONSTANT.KERNEL.SHAPE_CONSTRAINTS.CYLINDER_EXPONENT
        
        loss = torch.zeros(1, device=r[0].device, dtype=r[0].dtype)
        for i in range(len(r)):

            if self.if_update is not None and not self.if_update[i]:
                continue
            
            length_r = (r[i][:, 0]**2 + r[i][:, 1]**2).sqrt() - self._radius
            length_bottom = -r[i][:, 2] + self._bottom
            length_top = r[i][:, 2] - self._height
            
            barrier_ratio = CONSTANT.KERNEL.SHAPE_CONSTRAINTS.BARRIER_RATIO
            index_r, loss_r = self.barrier_function(length_r, thre, barrier_ratio, degree)
            index_bottom, loss_bottom = self.barrier_function(
                length_bottom, thre, barrier_ratio, degree
            )
            index_top, loss_top = self.barrier_function(
                length_top, thre, barrier_ratio, degree
            )
            
            if len(index_r) > 0:
                loss = loss + (self.scaler[i][index_r] * loss_r).sum()
            if len(index_bottom) > 0:
                loss = loss + (self.scaler[i][index_bottom] * loss_bottom).sum()
            if len(index_top) > 0:
                loss = loss + (self.scaler[i][index_top] * loss_top).sum()
            
        return loss
