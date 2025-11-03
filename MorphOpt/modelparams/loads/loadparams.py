
from json import load
import numpy as np
import torch


from ..base_params import BaseParams
from ... import GLOBAL
from .LoadInterface.baseloadinterface import BaseLoadInterface
from FEA.assemble.loads.base import BaseLoad
class LoadStep:
    """
    Class to handle a load step in the model.
    """
    def __init__(self):
        """
        Initialize the LoadStep class.
        """
        self.load_set: list[BaseLoadInterface] = []
        """load_set (list): A list to hold the loads in this step."""

    @property
    def num_variables(self) -> int:
        """
        Get the total number of load variables in this step.

        Returns:
            int: The total number of load variables.
        """
        total_vars = 0
        for load_interface in self.load_set:
            total_vars += load_interface.num_variables
        return total_vars

    def get_loads(self) -> list[BaseLoad]:
        """
        Get the loads in this step.

        Returns:
            list[BaseLoad]: The loads in this step.
        """
        loads_fea = {}
        
        for i, load_interface in enumerate(self.load_set):
            loads_fea['load_%d' % i] = load_interface.get_fea_load()
        return loads_fea
    
    def get_parameters(self) -> list[torch.Tensor]:
        """
        Get the parameters of all loads in this step.

        Returns:
            list[torch.Tensor]: The parameters of all loads in this step.
        """
        params = []
        for load_interface in self.load_set:
            params.append(load_interface.get_parameters().flatten().detach().clone())
        params = torch.cat(params)
        return params
    
    def set_parameters(self, xlist: torch.Tensor) -> None:
        """
        Set the parameters of all loads in this step.

        Args:
            xlist (torch.Tensor): The new parameters for all loads in this step.
        """
        ind_now = 0
        for load_interface in self.load_set:
            num_vars = load_interface.num_variables
            load_interface.set_parameters(xlist=xlist[ind_now:ind_now + num_vars])
            ind_now += num_vars

    def update_variables(self, x_change: torch.Tensor) -> None:
        """
        Update the variables of all loads in this step.

        Args:
            x_change (torch.Tensor): The change in variables.
        """
        ind_now = 0
        for load_interface in self.load_set:
            num_vars = load_interface.num_variables
            load_interface.update_variables(x_change=x_change[ind_now:ind_now + num_vars])
            ind_now += num_vars

class LoadsParams(BaseParams):
    """
    Class to handle the loads in the model.
    """
    from .LoadInterface.pressureinterface import PressureInterface
    from .LoadInterface.contactinterface import ContactInterface, ContactSelfInterface
    def __init__(self):
        """
        Initialize the Loads class.
        """
        self.load_steps: list[LoadStep] = []
        """load_steps (list): A list to hold the load steps."""

    @property
    def num_load_steps(self) -> int:
        """
        Get the number of load steps.

        Returns:
            int: The number of load steps.
        """
        return len(self.load_steps)

    def get_loads(self, step_index: int) -> LoadStep:
        """
        Get the load step at the given index.

        Args:
            step_index (int): The index of the load step.

        Returns:
            LoadStep: The load step at the given index.
        """
        return self.load_steps[step_index].get_loads()

    def get_parameters(self) -> list[torch.Tensor]:
        """
        Get the pressure parameters.

        Returns:
            list[torch.Tensor]: The pressure parameters.
        """

        params = []
        for load_step in self.load_steps:
            step_params = load_step.get_parameters()
            params.append(step_params)
        return params
    
    def set_parameters(self, xlist: list[torch.Tensor]) -> None:
        """
        Set the pressure parameters.

        Args:
            xlist (list[torch.Tensor]): The new pressure parameters.
        """
        for i in range(len(self.load_steps)):
            self.load_steps[i].set_parameters(xlist=xlist[i])

    def get_variables(self) -> torch.Tensor:
        """
        Get the pressure variables.

        Returns:
            torch.Tensor: The pressure variables.
        """
        xlist = self.get_parameters()
        x_flatten = torch.cat([torch.randn_like(xlist[i].flatten())*1e-6 for i in range(len(xlist))])
        return x_flatten
    
    def update_variables(self, x_change: torch.Tensor) -> None:
        """
        Update the pressure variables.

        Args:
            x_change (torch.Tensor): The change in pressure variables.
        """
        ind_now = 0

        # Update pressure variables
        for load_step in self.load_steps:
            num_vars = load_step.num_variables
            load_step.update_variables(x_change=x_change[ind_now:ind_now + num_vars])
            ind_now += num_vars

    def save(self, filepath) -> None:
        """
        Save the loads to a file.
        """
        params = self.get_parameters()
        params = [p.detach().cpu().numpy() for p in params]
        np.savez(filepath + '/loads_iter-%d.npz'% GLOBAL.History.iteration, *params)

    def load(self, filepath: str, iteration: int) -> None:
        """
        Load the loads from a file.

        Args:
            filepath (str): The path to the file.
            iteration (int): The iteration number.
        """
        data = np.load(filepath + '/loads_iter-%d.npz'% iteration)
        params = self.get_parameters()
        for i in range(len(params)):
            param_shape = params[i].shape
            param_data = torch.tensor(data['arr_%d'% i]).reshape(param_shape)
            self.load_steps[i].set_parameters(param_data)

        
    def plot(self):
        pass
        
    def save_figure(self, filepath):
        from matplotlib import pyplot as plt
        
        plt.figure()
        self.plot()
        plt.savefig(filepath + '/Pressure_%d.png'% GLOBAL.History.iteration)
        plt.close()