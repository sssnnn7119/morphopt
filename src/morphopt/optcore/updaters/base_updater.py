

import torch
from ..modelparams.base_params import BaseParams
from ..modelparams.params import Params
from . import optimizer
from ..baseobject import BaseObject

class BaseUpdater(BaseObject):
    """
    Base class for all Updaters.
    """

    def __init__(self, params: Params, *args, **kwargs):
        """
        Initialize the BaseUpdater.
        """

        self.obj_funcs: dict[str, callable] = {}
        """A dictionary of objective functions to be optimized.
        The keys are the names of the functions, and the values are the functions themselves.
        """

        self.constraints_funcs: dict[str, callable] = {}
        """A dictionary of constraints to be satisfied.
        The keys are the names of the constraints, and the values are the constraints themselves.
        """

        self.params: Params = params
        """The parameters of optimization process.
        This should be set to an instance of the Params class.
        """
        
        self.optimizer: optimizer.BaseOpt
        """The optimization algorithm used to update the design variables.
        This should be set to an instance of a subclass of Optimizer.BaseOpt.
        """

    
    def reinitialize(self, iter_now: int, sensitivity: list[torch.Tensor]) -> None:
        """
        reInitialize the updater with the current iteration and sensitivity.
        """
        raise NotImplementedError("This method should be overridden by subclasses.")
        
    def initialize(self) -> None:
        """
        Initialize the updater.
        """
        raise NotImplementedError("This method should be overridden by subclasses.")
    
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
    
    def update_variables(self, dx: torch.Tensor) -> None:
        """
        Update the variables of the surfaces.
        """
        pass

    def update(self) -> torch.Tensor:
        """
        Update the parameters of the optimization process.
        """
        raise NotImplementedError("This method should be overridden by subclasses.")