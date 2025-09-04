from re import A
import torch

from MorphOpt import GLOBAL
from .surface.update_surfaces import UpdaterSurfaces
from .load.update_loads import UpdaterLoads
from .material.update_materials import UpdaterMaterials
from ..solvers.FE_result import FE_result
from .adjoints import Adjoints


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

        self.adjoint: Adjoints = None
        """Adjoints: An instance of the Adjoints class for storing the adjoint variables."""

    def initialize(self, iteration: int) -> None:
        """
        Initialize the Updaters class.
        This method initializes the surfaces, loads, and materials if they are present.
        """
        pass

    def _adjoint_problem(self, fe_result: FE_result) -> Adjoints:
        """
        Solve the adjoint problem according to the objective function


        """

        # evaluate the adjoint displacement
        # Get the sensitivity of the elements
        GC0_ = fe_result.U[:, -6:].detach()
        Udp0_ = fe_result.Udp[:, :, -6:].permute(
            [0, 2, 1]).detach()
        UdF0_ = fe_result.UdF[:, :, -6:].permute(
            [0, 2, 1]).detach()
        Loss, LdU, LdUdp, LdUdF = GLOBAL.OBJFUN.get_derivative(
            U=GC0_,
            Udp=Udp0_,
            UdF=UdF0_, pressure_list=fe_result.pressure_list)
        
        adjoint = Adjoints()

        # first, get the adjoint displacement for each pressure
        adjoint.ADJu = torch.einsum('tuD, tu->tD', fe_result.ADJu, LdU)

        adjoint.ADJu_udp = torch.einsum('tuD, tup->tpD', fe_result.ADJu, LdUdp)
        adjoint.ADJudp = torch.einsum('tupD, tup->tpD', fe_result.ADJudp, LdUdp)

        adjoint.ADJu_udf = torch.einsum('tuD, tuf->tfD', fe_result.ADJu, LdUdF)
        adjoint.ADJudf = torch.einsum('tufD, tuf->tfD', fe_result.ADJudf, LdUdF)

        return Loss, adjoint

    def update(self, fe_result: FE_result) -> torch.Tensor:
        """
        Update the morphology of the neuron.
        """
        
        loss, adjoint = self._adjoint_problem(fe_result=fe_result)

        self.adjoint = adjoint

        if self.if_update_surface:
            self._var_surface = self._surface.update(fe_result=fe_result, adjoint=adjoint)


        if self.if_update_load:
            self._var_load = self._load.update(fe_result, adjoint=adjoint)

            
        if self.if_update_material:
            self._var_material = self._material.update(fe_result, adjoint=adjoint)


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