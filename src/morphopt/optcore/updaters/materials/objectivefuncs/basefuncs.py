import torch

class BaseConstraints():
    """
    Base class for objective functions in MorphOpt.
    """

    def __init__(self):
        """
        Initialize the objective function.
        """
        self.scaler: torch.Tensor | None = None
        """
        The scaler to process material constraints.
        """

    def initialize(self, cps0: torch.Tensor, sensitivity: torch.Tensor | None = None, *args, **kwargs):
        if sensitivity is None or sensitivity.numel() == 0:
            self.scaler = torch.ones_like(cps0)
            return

        scaler = sensitivity.abs().reshape_as(cps0)
        nonzero = scaler > 0
        if nonzero.any():
            scaler = torch.where(nonzero, scaler, scaler[nonzero].min())
        else:
            scaler = torch.ones_like(cps0)
        self.scaler = scaler

    def __call__(self, cps: torch.Tensor, *args, **kwargs) -> torch.Tensor:
        """
        Call the objective function.

        Args:
            cps (torch.Tensor): The SIMP control points.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            The value of the objective function.
        """
        raise NotImplementedError("Objective function not implemented.")
    
    @staticmethod
    def barrier_function(f: torch.Tensor, f_max: torch.Tensor | float, ratio: float, p: int):
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
    

class BaseObjective():
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

    def initialize(self, gradient: torch.Tensor, cps0: torch.Tensor, *args, **kwargs) -> None:
        """
        Initialize the objective function with the given parameters.

        Args:
            gradient (torch.Tensor): The gradient of the objective function.
            weights (list[torch.Tensor]): The weights for each point.
            *args: Positional arguments.
            **kwargs: Keyword arguments.
        """
        pass

    def __call__(self, cps: torch.Tensor, *args, **kwargs) -> torch.Tensor:
        """
        Call the objective function.

        Args:
            cps (torch.Tensor): The SIMP control points.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            The value of the objective function.
        """
        raise NotImplementedError("Objective function not implemented.")