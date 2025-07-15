import torch

class ObjectiveFunction:
    """
    The objective functions in MorphOpt.
    """

    def __init__(self):
        pass

    def get_objective(self, U: torch.Tensor, Udp: torch.Tensor, UdF: torch.Tensor, pressure_list: torch.Tensor, *args, **kwargs) -> torch.Tensor:
        """
        Get the value of the objective function.

        Args:
            U (torch.Tensor): The displacement field.
            Udp (torch.Tensor): The partial derivatives of the displacement field.
            UdF (torch.Tensor): The compliance matrix.
            pressure_list (torch.Tensor): The pressure.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            torch.Tensor: The value of the objective function.
        """
        raise NotImplementedError("This method should be overridden by subclasses.")
    
    def get_derivative(self, U: torch.Tensor, Udp: torch.Tensor, UdF: torch.Tensor, pressure_list: torch.Tensor, *args, **kwargs) -> torch.Tensor:
        """
        Get the derivative of the objective function.

        Args:
            U (torch.Tensor): The displacement field.
            Udp (torch.Tensor): The partial derivatives of the displacement field.
            UdF (torch.Tensor): The compliance matrix.
            pressure_list (torch.Tensor): The pressure.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            LdU (torch.Tensor): The derivative of the objective function with respect to the displacement field.
            LdUdp (torch.Tensor): The derivative of the objective function with respect to the partial derivatives.
            LdUdF (torch.Tensor): The derivative of the objective function with respect to the compliance matrix.

        """
        # Get the sensitivity of the elements
        U0_ = U.detach().to('cpu').requires_grad_()
        Udp0_ = Udp.detach().to('cpu').requires_grad_()
        UdF0_ = UdF.detach().to('cpu').requires_grad_()
        
        Loss = self.get_objective(U=U0_, Udp=Udp0_, UdF=UdF0_, pressure_list=pressure_list, *args, **kwargs)
        grads = torch.autograd.grad(Loss, 
                       [U0_, Udp0_, UdF0_], 
                       retain_graph=False, 
                       allow_unused=True)
        LdU, LdUdp, LdUdF = grads

        if LdU is None:
            LdU = torch.zeros_like(U0_)
        if LdUdp is None:
            LdUdp = torch.zeros_like(Udp0_)
        if LdUdF is None:
            LdUdF = torch.zeros_like(UdF0_)

        return Loss, LdU, LdUdp, LdUdF