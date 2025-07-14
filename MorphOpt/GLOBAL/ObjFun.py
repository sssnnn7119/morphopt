import torch

class ObjectiveFunction:
    """
    The objective functions in MorphOpt.
    """

    def __init__(self, surfaces):
        pass

    def get_objective(self, U: torch.Tensor, Udp: torch.Tensor, UdF: torch.Tensor, *args, **kwargs) -> torch.Tensor:
        """
        Get the value of the objective function.

        Args:
            U (torch.Tensor): The displacement field.
            Udp (torch.Tensor): The partial derivatives of the displacement field.
            UdF (torch.Tensor): The compliance matrix.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            torch.Tensor: The value of the objective function.
        """
        raise NotImplementedError("This method should be overridden by subclasses.")
    
    def get_derivative(self, U: torch.Tensor, Udp: torch.Tensor, UdF: torch.Tensor, *args, **kwargs) -> torch.Tensor:
        """
        Get the derivative of the objective function.

        Args:
            U (torch.Tensor): The displacement field.
            Udp (torch.Tensor): The partial derivatives of the displacement field.
            UdF (torch.Tensor): The compliance matrix.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            LdU (torch.Tensor): The derivative of the objective function with respect to the displacement field.
            LdUdp (torch.Tensor): The derivative of the objective function with respect to the partial derivatives.
            LdUdF (torch.Tensor): The derivative of the objective function with respect to the compliance matrix.

        """
        raise NotImplementedError("This method should be overridden by subclasses.")