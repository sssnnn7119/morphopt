from re import A
import torch

from MorphOpt import GLOBAL
from .surface.update_surfaces import UpdaterSurfaces


class Updaters:
    """
    This class is responsible for updating the morphologies of the neurons.
    """

    def __init__(self, surfaces:UpdaterSurfaces=None, *args, **kwargs):
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
            self.if_update_surface = True
        self._var_surface: torch.Tensor = None
        """
        var_surface: The updated surface variables.
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

    def update(self) -> torch.Tensor:
        """
        Update the morphology of the neuron.
        """
        
        if self.if_update_surface:
            self._var_surface = self._surface.update()
    
    def update_variables(self) -> None:
        """
        Update the variables of the surfaces and loads.
        """
        if self.if_update_surface:
            self._surface.update_variables(dx=self._var_surface)

    def save(self, foldpath: str) -> None:
        """
        Save the updater state to a file.
        """
        if self.if_update_surface:
            self._surface.save(filename=foldpath + '/updaters/')
