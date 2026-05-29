
import torch

from ..baseobject import BaseObject
import morphopt
from .geometry.update_geometry import UpdaterGeometries
from .materials.update_material import UpdaterMaterials


class Updaters(BaseObject):
    """
    This class is responsible for updating the morphologies of the neurons.
    """

    def __init__(self, surfaces: UpdaterGeometries = None, materials: UpdaterMaterials = None, device: str = None, *args, **kwargs):
        """
        Initialize the Updaters class with a neuron object.

        Args:
            surfaces (UpdaterSurfaces, optional): An instance of the UpdaterSurfaces class for updating the surfaces.
            loads (UpdaterLoads, optional): An instance of the UpdaterLoads class for updating the loads.
            materials (UpdaterMaterials, optional): An instance of the UpdaterMaterials class for updating the materials.
            device (str, optional): The device to use for computating the objective function and sensitivity analysis. If None, it will use the default device.
        """
        self._surface: UpdaterGeometries = None
        """
        UpdaterSurfaces: An instance of the UpdaterSurfaces class for updating the surfaces.
        """
        self.if_update_surface = False
        """
        if_update_surface: A flag indicating whether the surface needs to be updated.
        """
        
        if surfaces is not None:
            self._surface = surfaces
            self.if_update_surface = True
        self._var_surface: torch.Tensor = None
        """
        var_surface: The updated surface variables.
        """

        self._materials: UpdaterMaterials = None
        """
        UpdaterMaterials: An instance for updating material variables.
        """
        self.if_update_material = False
        """
        if_update_material: A flag indicating whether material variables need updates.
        """
        if materials is not None:
            self._materials = materials
            self.if_update_material = True
        self._var_material: torch.Tensor = None
        """
        var_material: The updated material variables.
        """

        self._device: str = device
        """
        The device to use for computating the objective function and sensitivity analysis. If None, it will be cpu by default.
        """

    def reinitialize(self, iteration: int) -> None:
        """
        reInitialize the Updaters class.
        This method reinitializes the surfaces, loads, and materials if they are present.
        """
        pass

    def initialize(self) -> None:
        """
        Initialize the Updaters class.
        This method initializes the surfaces, loads, and materials if they are present.
        """
        if self.if_update_surface:
            self._surface.initialize()
        if self.if_update_material:
            self._materials.initialize()

    def update(self, gradients: dict[str, torch.Tensor]) -> torch.Tensor:
        """
        Update the morphology of the neuron.
        """
        
        default_device = torch.get_default_device()

        if self._device is not None:
            torch.set_default_device(self._device)
            morphopt.controller._change_device_recursive(self, self._device)
            morphopt.controller._change_device_recursive(gradients, self._device)

        if self.if_update_surface:
            
            self._surface.reinitialize(gradient=gradients['geometry'])
            self._var_surface = self._surface.update()
        if self.if_update_material:
            
            self._materials.reinitialize(gradient=gradients['materials'])
            self._var_material = self._materials.update()

        if self._device is not None:
            torch.set_default_device(default_device)
            morphopt.controller._change_device_recursive(self, default_device)
    
    def update_variables(self) -> None:
        """
        Update the variables of the surfaces and loads.
        """
        if self.if_update_surface:
            self._surface.update_variables(dx=self._var_surface)
        if self.if_update_material:
            self._materials.update_variables(dx=self._var_material)

    def save(self, foldpath: str, iteration: int) -> None:
        """
        Save the updater state to a file.
        """
        if self.if_update_surface:
            self._surface.save(foldpath=foldpath, iteration=iteration)
        if self.if_update_material:
            self._materials.save(foldpath=foldpath, iteration=iteration)

    def load(self, foldpath: str, iteration: int) -> None:
        if self.if_update_surface:
            self._surface.load(foldpath=foldpath, iteration=iteration)
        if self.if_update_material:
            self._materials.load(foldpath=foldpath, iteration=iteration)


    def pathlog_required(self):
        paths = []
        if self.if_update_surface:
            paths += self._surface.pathlog_required()
        if self.if_update_material:
            paths += self._materials.pathlog_required()
        return paths