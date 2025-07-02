import torch
from ....modelparams import Loads

class BaseObj():
    """
    Base class for objective functions in MorphOpt.
    """

    def __init__(self, loads: Loads):
        """
        Initialize the objective function.
        """
        self.loads = loads


    def initialize(self, sensitivity, *args, **kwargs) -> None:
        """
        Initialize the objective function with the given parameters.

        Args:
            *args: Positional arguments.
            **kwargs: Keyword arguments.
        """
        pass

    def __call__(self, *args, **kwargs) -> float:
        """
        Call the objective function.

        Args:
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            The value of the objective function.
        """
        raise NotImplementedError("Objective function not implemented.")
    
    @staticmethod
    def barrier_function(f: torch.Tensor, f_max: torch.Tensor|float, ratio: float, p: int):
        """
        Apply a barrier function to the objective function.
        
        Args:
            f (torch.Tensor): The objective function value.
            f_max (float or torch.Tensor): The maximum value of the objective function.
            ratio (float): The ratio for the barrier function.
            p (float): The exponent for the barrier function.
            
        Returns:
            index (torch.Tensor): The indices of the elements that are greater than the barrier.
            fnew (torch.Tensor): The new objective function value after applying the barrier function.
        
        """
        if type(f_max) != torch.Tensor:
            f_max = torch.tensor(f_max).repeat(f.shape)
        index = torch.where(f > f_max * ratio)[0]

        if index.numel() > 0:
            f = f[index]
            f_max = f_max[index]
            fnew = ((f - f_max * ratio) / (f_max - f_max * ratio))**(p)
        else:
            f = f[index]
            fnew = torch.zeros_like(f)
        return index, fnew