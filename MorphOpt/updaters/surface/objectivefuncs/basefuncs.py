import torch


class BaseConstraints():
    """
    Base class for objective functions in MorphOpt.
    """

    def __init__(self):
        """
        Initialize the objective function.
        """
        self.scaler: list[torch.Tensor] = []
        """
        The scaler to process the objective function.
        """


    def initialize(self, r0: list[torch.Tensor], rdu0: list[torch.Tensor], rdu20: list[torch.Tensor], sensitivity: list[torch.Tensor], weights: list[torch.Tensor], *args, **kwargs):
        
        self.scaler = []
        for i in range(len(sensitivity)):
            sen_now = sensitivity[i].reshape([3, -1]).norm(dim=0)
            sen_now[sen_now==0] = sen_now[sen_now!=0].min()
            self.scaler.append(sen_now * weights[i])

    def __call__(self, r: list[torch.Tensor], rdu: list[torch.Tensor], rdu2: list[torch.Tensor], weights: list[torch.Tensor], *args, **kwargs) -> float:
        """
        Call the objective function.

        Args:
            weight (list[torch.Tensor]): The weights for each point.
            r (list[torch.Tensor]): The point coordinates of the surfaces.
            rdu (list[torch.Tensor]): The partial derivatives of the surfaces.
            rdu2 (list[torch.Tensor]): The second partial derivatives of the surfaces.
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
    

class BaseObjective():
    """
    Base class for objective functions in MorphOpt.
    """

    def __init__(self):
        """
        Initialize the objective function.
        """
        self.sensitivity: list[torch.Tensor] = []
        """
        Sensitivity of the shape derivative with respect to the contact forces.
        """

    def initialize(self, r0: list[torch.Tensor], rdu0: list[torch.Tensor], rdu20: list[torch.Tensor], weights: list[torch.Tensor], *args, **kwargs) -> None:
        """
        Initialize the objective function with the given parameters.

        Args:
            weights (list[torch.Tensor]): The weights for each point.
            *args: Positional arguments.
            **kwargs: Keyword arguments.
        """
        pass

    def __call__(self, r: list[torch.Tensor], rdu: list[torch.Tensor], rdu2: list[torch.Tensor], *args, **kwargs) -> float:
        """
        Call the objective function.

        Args:
            weight (list[torch.Tensor]): The weights for each point.
            r (list[torch.Tensor]): The point coordinates of the surfaces.
            rdu (list[torch.Tensor]): The partial derivatives of the surfaces.
            rdu2 (list[torch.Tensor]): The second partial derivatives of the surfaces.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            The value of the objective function.
        """
        raise NotImplementedError("Objective function not implemented.")