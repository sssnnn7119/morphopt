
from json import load
import numpy as np
import torch


from ..base_params import BaseParams
from ... import GLOBAL
from .LoadInterface.baseloadinterface import BaseLoadInterface
from FEA.assemble.loads.base import BaseLoad
from FEA import FEAController

class LoadsParams(BaseParams):
    """
    Class to handle the loads in the model.
    """
    from .LoadInterface.pressureinterface import PressureInterface
    from .LoadInterface.contactinterface import ContactInterface, ContactSelfInterface
    from .LoadInterface.pointinterface import ConcentratedForceInterface, ConcentratedMomentInterface
    def __init__(self):
        """
        Initialize the Loads class.
        """
        self.loadinterfaces: dict[str, BaseLoadInterface] = {}
        """loadinterfaces (dict): A dictionary to hold the load interfaces."""

        self.load_steps_params: list[dict[str, list[float]]] = []
        """load_steps (list): A list to hold the load steps."""

    def add_load_interface(self, load_interface: BaseLoadInterface, name: str = None) -> str:
        """
        Add a load interface to the load interfaces dictionary.

        Args:
            name (str): The name of the load interface.
            load_interface (BaseLoadInterface): The load interface object.
        Returns:
            str: The name of the load interface.
        """
        if name in self.loadinterfaces:
            raise ValueError(f"Load interface with name '{name}' already exists.")
        if name is None:
            name0 = load_interface.__class__.__name__
            ind = 0
            while '%s_%d'%(name0,ind) in self.loadinterfaces:
                ind += 1
            name = '%s_%d'%(name0,ind)

        self.loadinterfaces[name] = load_interface
        return name
    
    def set_step_num(self, num_steps: int) -> None:
        """
        Set the number of load steps.

        Args:
            num_steps (int): The number of load steps.
        """
        self.load_steps_params = []
        for _ in range(num_steps):
            load_step = {}
            for name, load_interface in self.loadinterfaces.items():
                load_step[name] = load_interface._values.copy()
            self.load_steps_params.append(load_step)

    def set_step_params(self, step_index: int, load_name: str, values: list[float]) -> None:
        """
        Set the load parameters for a specific load step.

        Args:
            step_index (int): The index of the load step.
            load_name (str): The name of the load interface.
            values (list[float]): The load parameter values.
        """
        if step_index < 0 or step_index >= len(self.load_steps_params):
            raise IndexError("step_index out of range.")
        if load_name not in self.loadinterfaces:
            raise KeyError(f"Load interface with name '{load_name}' does not exist.")
        self.load_steps_params[step_index][load_name] = values
    
    def initialize(self, iteration, *args, **kwargs):
        # Sort the load interfaces and load steps parameters by their keys
        sorted_load_interfaces = dict(sorted(self.loadinterfaces.items()))
        sorted_load_steps_params = [dict(sorted(step.items())) for step in self.load_steps_params]

        # Update the dictionaries with the sorted versions
        self.loadinterfaces = sorted_load_interfaces
        self.load_steps_params = sorted_load_steps_params

    @property
    def num_load_steps(self) -> int:
        """
        Get the number of load steps.

        Returns:
            int: The number of load steps.
        """
        return len(self.load_steps_params)

    def get_loads_fea(self) -> dict[str, BaseLoad]:
        """
        Get the load step at the given index.

        Returns:
            loads_fea (dict): A dictionary of FEA load objects.
        """
        loads_fea = {}
        for name, load_interface in self.loadinterfaces.items():
            loads_fea[name] = load_interface.get_fea_load()
        return loads_fea

    def process_fea(self, fea: FEAController, step_index: int) -> None:
        """
        Process the FEA controller to update load-related information.

        Args:
            fea (FEAController): The FEA controller instance.
            step_index (int): The index of the load step.
        """
        load_step_now = self.load_steps_params[step_index]
        for name, load_interface in self.loadinterfaces.items():
            load_interface._values = load_step_now[name]
            load_interface.apply_load(fea.assembly.get_load(name))

    def get_parameters(self) -> list[torch.Tensor]:
        """
        Get the parameters.

        Returns:
            list[torch.Tensor]: the parameters.
        """
        params = []
        for load_step in self.load_steps_params:
            for params_now in load_step.values():
                params.append(torch.tensor(params_now))
        return params
    
    def set_parameters(self, xlist: list[torch.Tensor]) -> None:
        """
        Set the parameters.

        Args:
            xlist (list[torch.Tensor]): The new parameters.
        """
        ind_now = 0
        for load_step in self.load_steps_params:
            for key in load_step.keys():
                change_slice = xlist[ind_now]
                load_step[key] = change_slice.detach().cpu().tolist()
                ind_now += 1

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
        for load_step in self.load_steps_params:
            for key in load_step.keys():
                num_vars = len(load_step[key])
                change_slice = x_change[ind_now:ind_now + num_vars]
                current_params = torch.tensor(load_step[key])
                updated_params = current_params + change_slice
                load_step[key] = updated_params.detach().cpu().tolist()
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
        key_list = list(self.loadinterfaces.keys())
        for i in range(len(params)):
            params[i].data = torch.tensor(data['arr_%d'%i]).reshape(params[i].shape)
        self.set_parameters(params)

        
    def plot(self):
        pass
        
    def save_figure(self, filepath):
        from matplotlib import pyplot as plt
        
        plt.figure()
        self.plot()
        plt.savefig(filepath + '/Pressure_%d.png'% GLOBAL.History.iteration)
        plt.close()