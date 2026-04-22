
import torchfea
import numpy as np
import torch

from ..base_params import BaseParams
from .feainterface.basefeainterface import BaseFEAInterface

from torchfea import FEA_INP, FEAController

class FEAParams(BaseParams):
    """
    Class to handle the loads in the model.
    """
    from .feainterface import PressureInterface
    from .feainterface import ContactInterface, ContactSelfInterface
    from .feainterface import ConcentratedForceInterface, ConcentratedMomentInterface
    from .feainterface import SpringToGroundInterface, SpringBetweenRPsInterface, PenaltyDoFInterface
    from .feainterface import BoundaryConditionInterface, BoundaryConditionRPInterface
    from .feainterface import CoupleInterface
    from .feainterface import ReferencePointInterface
    from .feainterface import BodyforceInterface
    def __init__(self):
        """
        Initialize the Loads class.
        """
        super().__init__()

        self.feainterfaces: dict[str, BaseFEAInterface] = {}
        """loadinterfaces (dict): A dictionary to hold the load interfaces."""

        self.fea_steps_params: list[dict[str, list[float]]] = []
        """load_steps (list): A list to hold the load steps."""

        self.define_interface()
        self.define_steps()

    def define_interface(self):
        pass

    def define_steps(self):
        pass

    
    def add_instance_from_inp(self, fe: torchfea.FEAController, inp_path: str, part_name: str, instance_name: str, translation: list[float] = None, part_name_new: str = None, instance_name_new: str = None) -> None:
        """
        Add a part and instance into the current FE assembly by reading an external INP file.

        Args:
            fe: Target FEAController to modify.
            inp_path: Absolute path to the external INP file.
            part_name: Name of the part in the external model to import.
            instance_name: Name to register for the created instance in the current assembly.
            translation: Optional [Tx, Ty, Tz] translation applied to the created instance.
            part_name_new: Optional new name for the imported part in the current assembly.
            instance_name_new: Optional new name for the created instance in the current assembly.
        """
        if part_name_new is None:
            part_name_new = part_name
        if instance_name_new is None:
            instance_name_new = instance_name

        ext_inp = torchfea.FEA_INP()
        ext_inp.read_inp(inp_path)
        fe_ext = torchfea.from_inp(ext_inp)
        part = fe_ext.assembly.get_part(part_name)
        fe.assembly.add_part(part, name=part_name_new)
        fe.assembly.add_instance(torchfea.Instance(part=part), name=instance_name_new)
        inst = fe.assembly.get_instance(instance_name_new)
        trans = translation if translation is not None else [0.0, 0.0, 0.0]
        inst._translation = torch.tensor(trans)

    def add_fea_interface(self, fea_interface: BaseFEAInterface, name: str = None) -> str:
        """
        Add a load interface to the load interfaces dictionary.

        Args:
            name (str): The name of the load interface.
            load_interface (BaseLoadInterface): The load interface object.
        Returns:
            str: The name of the load interface.
        """
        if name in self.feainterfaces:
            raise ValueError(f"Load interface with name '{name}' already exists.")
        if name is None:
            name0 = fea_interface.__class__.__name__
            ind = 0
            while '%s_%d'%(name0,ind) in self.feainterfaces:
                ind += 1
            name = '%s_%d'%(name0,ind)

        self.feainterfaces[name] = fea_interface
        fea_interface._name = name
        return name
    
    def set_step_num(self, num_steps: int) -> None:
        """
        Set the number of load steps.

        Args:
            num_steps (int): The number of load steps.
        """
        self.fea_steps_params = []
        for _ in range(num_steps):
            load_step = {}
            for name, load_interface in self.feainterfaces.items():
                load_step[name] = load_interface._values.copy()
            self.fea_steps_params.append(load_step)

    def set_step_params(self, step_index: int, load_name: str, values: list[float]) -> None:
        """
        Set the load parameters for a specific load step.

        Args:
            step_index (int): The index of the load step.
            load_name (str): The name of the load interface.
            values (list[float]): The load parameter values.
        """
        if step_index < 0 or step_index >= len(self.fea_steps_params):
            raise IndexError("step_index out of range.")
        if load_name not in self.feainterfaces:
            raise KeyError(f"Load interface with name '{load_name}' does not exist.")
        self.fea_steps_params[step_index][load_name] = values
    
    def reinitialize(self, iteration, *args, **kwargs):
        # Sort the load interfaces and load steps parameters by their keys
        sorted_fea_interfaces = dict(sorted(self.feainterfaces.items()))
        sorted_fea_steps_params = [dict(sorted(step.items())) for step in self.fea_steps_params]

        # Update the dictionaries with the sorted versions
        self.feainterfaces = sorted_fea_interfaces
        self.fea_steps_params = sorted_fea_steps_params

    @property
    def num_load_steps(self) -> int:
        """
        Get the number of load steps.

        Returns:
            int: The number of load steps.
        """
        return len(self.fea_steps_params)

    def create_fea(self, inp: torchfea.FEA_INP) -> FEAController:
        """
        Create an FEAController instance from the given FEA_INP file and add load interfaces
        Args:
            inp (torchfea.FEA_INP): The FEA input file.
        Returns:
            FEAController: The created FEAController instance with load interfaces added.
        """

        default_device = torch.tensor(0.).device
        default_dtype = torch.tensor(0.).dtype
        
        # get the FEA model
        nodes = inp.part['final_model'].nodes[:, 1:]
        part = torchfea.Part(torch.from_numpy(nodes).to(default_device).to(default_dtype))
        for surface_name, surface in inp.part['final_model'].surfaces.items():
            sf_now = []
            for sf in surface:
                sf_now.append((sf[0], sf[1]))
            part.add_surface_set(surface_name, sf_now)

        # define the set of nodes
        for set_name, node_indices in inp.part['final_model'].sets_nodes.items():
            part.set_nodes[set_name] = np.unique(np.array(list(node_indices)))

        index_bottom = np.where(np.abs(nodes[:, 2]-0) < 1e-3)[0]
        part.set_nodes['surface_0_Bottom'] = index_bottom
        index_head = np.where(np.abs(nodes[:, 2]-np.max(nodes[:, 2])) < 1e-3)[0]
        part.set_nodes['surface_0_Head'] = index_head

        for key in inp.part['final_model'].elems.keys():
            elems = inp.part['final_model'].elems[key][:, 1:]
            elems_index = inp.part['final_model'].elems[key][:, 0]
            element = torchfea.elements.initialize_element(element_type=key,
                                                        elems_index=torch.from_numpy(elems_index).to(torch.get_default_device()),     
                                                        elems=torch.from_numpy(elems).to(torch.get_default_device()), 
                                                        part=part)

            part.add_element(element, name=key)

        assembly = torchfea.Assembly()
        assembly.add_part(part=part, name='final_model')
        assembly.add_instance(instance=torchfea.Instance(part), name='final_model')

        fe = torchfea.FEAController()
        fe.assembly = assembly
        fe.solver = torchfea.solver.StaticImplicitSolver(tol_error=1e-3)

        # Add fea features
        for name, interface in self.feainterfaces.items():
            interface.modify_fea(fe, name)
        
        return fe
    
    
    def process_fea(self, fe: FEAController, step_index: int) -> None:
        """
        Process the FEA controller to update load-related information.

        Args:
            fe (FEAController): The FEA controller instance.
            step_index (int): The index of the load step.
        """
        load_step_now = self.fea_steps_params[step_index]
        for name, load_interface in self.feainterfaces.items():
            load_interface._values = load_step_now[name]
            load_interface.apply_fea_value(fe, name)

    def get_parameters(self) -> list[torch.Tensor]:
        """
        Get the parameters.

        Returns:
            list[torch.Tensor]: the parameters.
        """
        params = []
        for load_step in self.fea_steps_params:
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
        for load_step in self.fea_steps_params:
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
        for load_step in self.fea_steps_params:
            for key in load_step.keys():
                num_vars = len(load_step[key])
                change_slice = x_change[ind_now:ind_now + num_vars]
                current_params = torch.tensor(load_step[key])
                updated_params = current_params + change_slice
                load_step[key] = updated_params.detach().cpu().tolist()
                ind_now += num_vars
