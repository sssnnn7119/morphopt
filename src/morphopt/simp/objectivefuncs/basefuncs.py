import torch

from ...optcore.protocal import ProtocalInitializable, ProtocalSavable


class BaseConstraints(ProtocalInitializable):
    """Material penalties evaluated without sensitivity-dependent scaling."""

    def __call__(self, cps: torch.Tensor, *args, **kwargs) -> torch.Tensor:
        """Call the objective function.

        Args:
            cps (torch.Tensor): The SIMP control points.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            torch.Tensor: Differentiable scalar or one-element penalty tensor.
        """
        raise NotImplementedError("Objective function not implemented.")
    
    @staticmethod
    def barrier_function(f: torch.Tensor, f_max: torch.Tensor | float, ratio: float, p: int):
        """Apply a barrier function to the objective function.

        Args:
            f (torch.Tensor): The objective function value.
            f_max (torch.Tensor | float): The maximum value of the objective function.
            ratio (float): The ratio for the barrier function.
            p (int): The exponent for the barrier function.

        Returns:
            index (torch.Tensor): The indices of the elements that are greater than the barrier.
            fnew (torch.Tensor): The new objective function value after applying the barrier
                function.
        """
        if type(f_max) != torch.Tensor:
            f_max = torch.full_like(f, float(f_max))
        index = torch.where(f > f_max * ratio)[0]

        if index.numel() > 0:
            f = f[index]
            f_max = f_max[index]
            fnew = ((f - f_max * ratio) / (f_max - f_max * ratio))**(p)
        else:
            f = f[index]
            fnew = torch.zeros_like(f)
        return index, fnew
    

class BaseObjective(ProtocalInitializable, ProtocalSavable):
    """
    Base class for objective functions in MorphOpt.
    """

    def __init__(self):
        """
        Initialize the objective function.
        """
        self.sensitivity: torch.Tensor | None = None
        """
        Sensitivity of objective with respect to material variables.
        """

    def __call__(self, cps: torch.Tensor, *args, **kwargs) -> torch.Tensor:
        """Call the objective function.

        Args:
            cps (torch.Tensor): The SIMP control points.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            torch.Tensor: Differentiable scalar or one-element objective tensor.
        """
        raise NotImplementedError("Objective function not implemented.")
