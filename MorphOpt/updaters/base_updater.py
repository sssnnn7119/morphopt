

import torch
from tabulate import tabulate
from ..GLOBAL import History
from ..modelparams.base_params import BaseParams
from ..modelparams.params import Params
from . import optimizer


class BaseUpdater:
    """
    Base class for all Updaters.
    """

    def __init__(self, params: Params, *args, **kwargs):
        """
        Initialize the BaseUpdater.
        """
        self.max_step_iter = 50
        """Maximum number of iterations for the sub-optimization process.
        """
        
        self.obj_funcs: dict[str, callable] = {}
        """A dictionary of objective functions to be optimized.
        The keys are the names of the functions, and the values are the functions themselves.
        """
        
        self.params_update: BaseParams = None
        """The parameters of the optimization process.
        This should be set to an instance of a subclass of BaseParams.
        """
        
        self.params: Params = params
        """The parameters of optimization process.
        This should be set to an instance of the Params class.
        """
        
        self.optimizer: optimizer.BaseOpt
        """The optimization algorithm used to update the design variables.
        This should be set to an instance of a subclass of Optimizer.BaseOpt.
        """
        
        self.iteration_total = 0
        """
        The total number of iterations performed in the optimization process.
        """
                
        self.U_dim: list[int] = []
        """U_dim: The dimensions of the interest for the optimization problem.
        This is a list of integers representing the dimensions of the displacement vector.
        """
    
    def initialize(self, iter_now: int, sensitivity: list[torch.Tensor]) -> None:
        """
        Initialize the updater with the current iteration and sensitivity.
        """
        raise NotImplementedError("This method should be overridden by subclasses.")

    def _get_sensitivity(self) -> tuple[torch.Tensor, list[torch.Tensor]]:
        """
        Get the sensitivity of the elements based on the provided objective function.
        
        Parameters:
            fe_result (FE_result): The finite element analysis result containing the displacement and Jacobian.
            obj_fun (callable): The objective function to be used for sensitivity analysis.
        
        Returns:
            tuple: A tuple containing:
                - Loss (torch.Tensor): The loss value.
                - sensitivity (list[torch.Tensor]): A list of sensitivity tensors for each surface.
        """
        raise NotImplementedError("This method should be overridden by subclasses.")
    
    def _refine_sensitivity(self, iter_now: int, sensitivity: list[torch.Tensor]) -> list[torch.Tensor]:
        """
        Refine the sensitivity values based on the current iteration.
        
        Parameters:
            iter_now (int): The current iteration number.
            sensitivity (list[torch.Tensor]): The sensitivity tensors to be refined.
        
        Returns:
            list[torch.Tensor]: The refined sensitivity tensors.
        """
        # This method can be overridden by subclasses if needed
        return sensitivity
    
    def closure(self, x: torch.Tensor, return_list: bool = False) -> torch.Tensor:
        """
        This method is called to update the design variables based on the optimization algorithm used.
        
        Parameters:
            x (torch.Tensor): The current design variables.
            return_list (bool): If True, returns a list of objective function values; otherwise, returns their sum.
        
        Returns:
            torch.Tensor: The objective function value(s).
        """
        raise NotImplementedError("This method should be overridden by subclasses.")
    

