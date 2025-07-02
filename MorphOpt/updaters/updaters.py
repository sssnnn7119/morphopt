import torch
from .surface.update_surfaces import UpdaterSurfaces
from .load.update_loads import UpdaterLoads
from .material.update_materials import UpdaterMaterials
from ..solvers.FE_result import FE_result

class Updaters:
    """
    This class is responsible for updating the morphologies of the neurons.
    """

    def __init__(self, surfaces:UpdaterSurfaces=None, loads:UpdaterLoads=None, materials:UpdaterMaterials=None, U_dim=[-6,-5,-4,-3,-2,-1], *args, **kwargs):
        """
        Initialize the Updaters class with a neuron object.

        Args:
            surfaces (UpdaterSurfaces, optional): An instance of the UpdaterSurfaces class for updating the surfaces.
            loads (UpdaterLoads, optional): An instance of the UpdaterLoads class for updating the loads.
            materials (UpdaterMaterials, optional): An instance of the UpdaterMaterials class for updating the materials.
        """
        self._surface: UpdaterSurfaces = None
        """
        UpdaterSurfaces: An instance of the UpdaterSurfaces class for updating the surfaces.
        """
        self.if_update_surface = False
        """
        if_update_surface: A flag indicating whether the surface needs to be updated.
        """
        
        if surfaces is not None:
            self._surface = surfaces
            self._surface.U_dim = U_dim
            self.if_update_surface = True
        self._var_surface: torch.Tensor = None
        """
        var_surface: The updated surface variables.
        """

        self._load: UpdaterLoads = None
        """
        UpdateLoads: An instance of the UpdateLoads class for updating the loads.
        """
        self.if_update_load = False
        """
        if_update_load: A flag indicating whether the load needs to be updated.
        """
        if loads is not None:
            self._load = loads
            self._load.U_dim = U_dim
            self.if_update_load = True
        self._var_load: torch.Tensor = None
        """
        var_load: The updated load variables.
        """
        
        self._material: UpdaterMaterials = None
        """
        UpdaterMaterials: An instance of the UpdaterMaterials class for updating the materials.
        """
        self.if_update_material = False
        if materials is not None:
            self._material = materials
            self._material.U_dim = U_dim
            self.if_update_material = True
        self._var_material: torch.Tensor = None
        """var_material: The updated material variables.
        """

        
    def initialize(self, iteration: int) -> None:
        """
        Initialize the Updaters class.
        This method initializes the surfaces, loads, and materials if they are present.
        """
        pass

    def objective_function(self, U: torch.Tensor, Udp: torch.Tensor, *args, **kwargs) -> torch.Tensor:
        """
        Get the sensitivity of the elements.

        Parameters:
            U (torch.Tensor): The displacement vector.
                [num_task, U]
            Udp (torch.Tensor): The Jacobian vector.
                [num_task, U, pressure]

        Returns:
            tuple: A tuple containing:
                Loss (float): The loss value.
        """
        raise NotImplementedError(
            "This method should be implemented in a subclass.")


    def update(self, fe_result: FE_result) -> torch.Tensor:
        """
        Update the morphology of the neuron.
        """
        
        obj_fun = lambda U, Udp, UdF, *args, **kwargs: self.objective_function(U=U, Udp=Udp, UdF=UdF, FE_result = fe_result, *args, **kwargs)

        loss = 0.
        if self.if_update_surface:
            loss, self._var_surface = self._surface.update(fe_result, obj_fun=obj_fun)


        if self.if_update_load:
            loss, self._var_load = self._load.update(fe_result, obj_fun=obj_fun)

            
        if self.if_update_material:
            loss, self._var_material = self._material.update(fe_result, obj_fun=obj_fun)


        return loss
    
    def update_variables(self) -> None:
        """
        Update the variables of the surfaces and loads.
        """
        if self.if_update_surface:
            self._surface.params_update.update_variables(x_change=self._var_surface)
        if self.if_update_load:
            self._load.params_update.update_variables(x_change=self._var_load)
        if self.if_update_material:
            self._material.params_update.update_variables(x_change=self._var_material)