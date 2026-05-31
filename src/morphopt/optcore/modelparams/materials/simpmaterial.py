import math
from typing import Optional

import torch
import numpy as np

import torchfea
from ..base_params import BaseParams
import bspmap

import pyvista as pv

# region for void elements penalization
class SIMPElementFgrad(torchfea.elements.Element_3D):

    _serialized_attributes_exclude = torchfea.elements.Element_3D._serialized_attributes_exclude + ['_EmdUe_2', '_dN2WP']
    def __init__(self, elems_index, elems, penalfactor: torch.Tensor):
        super().__init__(elems_index, elems)

        if isinstance(penalfactor, float):
            penalfactor = torch.tensor([penalfactor], dtype=torch.get_default_dtype())

            
        if penalfactor.dim() == 0 or penalfactor.shape == (1,):
            penalfactor = penalfactor.reshape(1, 1)

        self.penalfactor = penalfactor
        """the penalization factor for SIMP material"""

    def initialize(self, *args, **kwargs):
        super().initialize(*args, **kwargs)

        self._dN2WP = torch.einsum('geija,ge->geija', self.shape_function_d2_gaussian, self.gaussian_weight * self.penalfactor)


        self._EmdUe_2 = torch.zeros([self.num_nodes_per_elem, 3, self.num_nodes_per_elem, 3, self._elems.shape[0]])

        for I0 in range(3):
            for i0 in range(3):
                for j0 in range(3):

                    I = I0
                    i = i0
                    j = j0
                    J = I0
                    k = i0
                    l = j0

                    self._EmdUe_2[:, I, :, J, :] += torch.einsum('gea, geb->abe', self._dN2WP[:, :, i, j, :], self.shape_function_d2_gaussian[:, :, k, l, :]) * 2


    def potential_Energy(self, RGC: torch.Tensor, rotation_matrix: Optional[torch.Tensor] = None):
        
        U = RGC

        if rotation_matrix is not None:
            U = torch.einsum('ij,aj->ai', rotation_matrix.T, U)
        
        Ea = super().potential_Energy(RGC, rotation_matrix)

        Ugrad2 = torch.zeros([self._num_gaussian, self._elems.shape[0], 3, 3, 3])
        for i in range(self.num_nodes_per_elem):
            Ugrad2 += torch.einsum('geij,eI->geIij',
                                         self.shape_function_d2_gaussian[..., i],
                                         U[self._elems[:, i]])
            
        Er = torch.einsum('geIij,geIij,ge->', Ugrad2, Ugrad2, self.gaussian_weight * self.penalfactor)


        return Ea + Er
    
    def _get_EpdUe_EpdUe2(self, U, if_onlyforce = False):
        result0 = super()._get_EpdUe_EpdUe2(U, if_onlyforce)

        Ugrad2 = torch.zeros([self._num_gaussian, self._elems.shape[0], 3, 3, 3])
        for i in range(self.num_nodes_per_elem):
            Ugrad2 += torch.einsum('geij,eI->geIij',
                                         self.shape_function_d2_gaussian[..., i],
                                         U[self._elems[:, i]])
            
        EmdUgrad2 = 2 * Ugrad2

        EmdUe = torch.einsum('geIij,geija->aIe', EmdUgrad2,
                                self._dN2WP)
        
        if if_onlyforce:
            return EmdUe + result0

        return EmdUe + result0[0], self._EmdUe_2 + result0[1]


class SIMPElementFskew(torchfea.elements.Element_3D):

    _serialized_attributes_exclude = torchfea.elements.Element_3D._serialized_attributes_exclude + ['_EmdUe_2', '_dN2WP']

    def __init__(self, elems_index, elems, penalfactor: torch.Tensor):
        super().__init__(elems_index, elems)

        if isinstance(penalfactor, float):
            penalfactor = torch.tensor([penalfactor], dtype=torch.float32)

            
        if penalfactor.dim() == 0 or penalfactor.shape == (1,):
            penalfactor = penalfactor.reshape(1, 1)

        self._penalfactor = penalfactor
        """the penalization factor for SIMP material"""
    
    @property
    def penalfactor(self) -> torch.Tensor:
        return self._penalfactor
    
    @penalfactor.setter
    def penalfactor(self, value: torch.Tensor) -> None:
        if isinstance(value, float):
            value = torch.tensor([value], dtype=torch.float32)

        if value.dim() == 0 or value.shape == (1,):
            value = value.reshape(1, 1)

        self._penalfactor = value.to(torch.float32)

    def initialize(self, *args, **kwargs):
        super().initialize(*args, **kwargs)

        self._initialize_simppenalty()


    def _initialize_simppenalty(self):
        """
                initialize the penalty for SIMP material, which will be used in the energy and force calculations.
        """
        self._dN2WP = torch.einsum('geija,ge->geija', self.shape_function_d2_gaussian, self.gaussian_weight * self._penalfactor)

        self._EmdUe_2 = torch.zeros([self.num_nodes_per_elem, 3, self.num_nodes_per_elem, 3, self._elems.shape[0]])

        for I0 in range(3):
            for i0 in range(3):
                for j0 in range(3):

                    I = I0
                    i = i0
                    j = j0
                    J = I0
                    k = i0
                    l = j0

                    self._EmdUe_2[:, I, :, J, :] += torch.einsum('gea, geb->abe', self._dN2WP[:, :, i, j, :], self.shape_function_d2_gaussian[:, :, k, l, :]) * 4

                    I = I0
                    i = i0
                    j = j0
                    J = i0
                    k = I0
                    l = j0

                    self._EmdUe_2[:, I, :, J, :] += torch.einsum('gea, geb->abe', self._dN2WP[:, :, i, j, :], self.shape_function_d2_gaussian[:, :, k, l, :]) * -4

    def potential_Energy(self, RGC: torch.Tensor, rotation_matrix: Optional[torch.Tensor] = None):
        
        U = RGC

        if rotation_matrix is not None:
            U = torch.einsum('ij,aj->ai', rotation_matrix.T, U)
        
        Ea = super().potential_Energy(RGC, rotation_matrix)

        Ugrad2 = torch.zeros([self._num_gaussian, self._elems.shape[0], 3, 3, 3])
        for i in range(self.num_nodes_per_elem):
            Ugrad2 += torch.einsum('geij,eI->geIij',
                                        self.shape_function_d2_gaussian[..., i],
                                        U[self._elems[:, i]])
        
        Fskew = Ugrad2 - Ugrad2.transpose(2, 3)

        Er = torch.einsum('geIij,ge->', Fskew**2, self.gaussian_weight * self.penalfactor)


        return Ea + Er
    
    def _get_EpdUe_EpdUe2(self, U, if_onlyforce = False):
        result0 = super()._get_EpdUe_EpdUe2(U, if_onlyforce)

        Ue = U[self._elems]

        Ugrad2 = torch.zeros([self._num_gaussian, self._elems.shape[0], 3, 3, 3])
        for i in range(self.num_nodes_per_elem):
            Ugrad2 += torch.einsum('geij,eI->geIij',
                                        self.shape_function_d2_gaussian[..., i],
                                        Ue[:, i])
        
        # Fskew_geijk = Ugrad2_geijk - Ugrad2_geikj
        # Fskew = Ugrad2 - Ugrad2.transpose(2, 3) 

        # E = p Fskew_geijk Fskew_geijk w_ge
        # Er = torch.einsum('geIij,geIij,ge->', Fskew, Fskew, self.gaussian_weight * self.penalfactor)


        EmdUgrad2 = 4 * (Ugrad2 - Ugrad2.transpose(2, 3))

        EmdUe = torch.einsum('geIij,geija->aIe', EmdUgrad2,
                                self._dN2WP)
        
        if if_onlyforce:
            return EmdUe + result0

        return EmdUe + result0[0], self._EmdUe_2 + result0[1]

class SIMPElementHuHu_LuLu(torchfea.elements.Element_3D):
    _serialized_attributes_exclude = torchfea.elements.Element_3D._serialized_attributes_exclude + ['_EmdUe_2', '_dN2WP']
    def __init__(self, elems_index, elems, penalfactor: torch.Tensor):
        super().__init__(elems_index, elems)

        self._penalfactor = penalfactor
        """the penalization factor for SIMP material"""

    def initialize(self, *args, **kwargs):
        super().initialize(*args, **kwargs)

        if self._penalfactor.dim() == 0 or self._penalfactor.shape == (1,):
            self._penalfactor = self._penalfactor.reshape(1, 1)

        self._dN2WP = torch.einsum('geija,ge->geija', self.shape_function_d2_gaussian, self.gaussian_weight * self._penalfactor)


        self._EmdUe_2 = torch.zeros([self.num_nodes_per_elem, 3, self.num_nodes_per_elem, 3, self._elems.shape[0]])

        for I0 in range(3):
            for i0 in range(3):

                I = I0
                i = i0
                j = i0
                J = I0
                k = i0
                l = i0

                self._EmdUe_2[:, I, :, J, :] -= torch.einsum('gea, geb->abe', self._dN2WP[:, :, i, j, :], self.shape_function_d2_gaussian[:, :, k, l, :]) / 3

                for j0 in range(3):

                    I = I0
                    i = i0
                    j = j0
                    J = I0
                    k = i0
                    l = j0

                    self._EmdUe_2[:, I, :, J, :] += torch.einsum('gea, geb->abe', self._dN2WP[:, :, i, j, :], self.shape_function_d2_gaussian[:, :, k, l, :])

        # self._EmdUe_2 = torch.einsum('geija, geklb,geIijJkl->aIbJe', self._dN2W, self.shape_function_d2_gaussian, EmdUgrad2_2)


    def potential_Energy(self, RGC: torch.Tensor, rotation_matrix: Optional[torch.Tensor] = None):
        
        U = RGC

        if rotation_matrix is not None:
            U = torch.einsum('ij,aj->ai', rotation_matrix.T, U)
        
        Ea = super().potential_Energy(RGC, rotation_matrix)

        Ugrad2 = torch.zeros([self._num_gaussian, self._elems.shape[0], 3, 3, 3])
        for i in range(self.num_nodes_per_elem):
            Ugrad2 += torch.einsum('geij,eI->geIij',
                                         self.shape_function_d2_gaussian[..., i],
                                         U[self._elems[:, i]])
            
        Er = 0.5 * (Ugrad2**2).sum([2, 3, 4])
        for i in range(3):
            Er -= 0.5 * (Ugrad2[:, :, :, i, i]**2).sum([-1]) / 3

        Er = (Er * self.gaussian_weight * self._penalfactor).sum()

        return Ea + Er
    
    def _get_EpdUe_EpdUe2(self, U, if_onlyforce = False):
        result0 = super()._get_EpdUe_EpdUe2(U, if_onlyforce)

        Ugrad2 = torch.zeros([self._num_gaussian, self._elems.shape[0], 3, 3, 3])
        for i in range(self.num_nodes_per_elem):
            Ugrad2 += torch.einsum('geij,eI->geIij',
                                         self.shape_function_d2_gaussian[..., i],
                                         U[self._elems[:, i]])
        
        Er = self.potential_Energy(U)

        EmdUgrad2 = Ugrad2
        for i in range(3):
            EmdUgrad2[:, :, :, i, i] -= Ugrad2[:, :, :, i, i] / 3

        EmdUe = torch.einsum('geIij,geija->aIe', EmdUgrad2,
                                self._dN2WP)
        
        if if_onlyforce:
            return EmdUe + result0

        return EmdUe + result0[0], self._EmdUe_2 + result0[1]

class SIMPElementC3D10(torchfea.elements.C3D10, SIMPElementFskew):
    pass
# endregion




def RAMP_interpolation(rho: torch.Tensor, p: int):
    """
    RAMP interpolation function for SIMP method.

    Args:
        rho (torch.Tensor): The material density.
        p (int): The penalization power.

    Returns:
        torch.Tensor: The interpolated material property.
    """
    return rho / (1 + p * (1 - rho))

def p_order_interpolation(rho: torch.Tensor, p: int):
    """
    p-order interpolation function for SIMP method.

    Args:
        rho (torch.Tensor): The material density.
        p (int): The penalization power.

    Returns:
        torch.Tensor: The interpolated material property.
    """
    return rho ** p


class SIMP_BSPFieldMaterials(BaseParams):
    """
    Class to handle the materials of the morphable model.
    """

    def __init__(self, 
                 mumax: float, 
                 kappamax: float, 
                 simp_ratio_min: float,
                 bounding_box: list[float],
                 simp_field_resolution: float,
                 degree: int,
                 density: float,
                 initial_ratio: float = 0.5,
                 voidpenalfactor: float = 1e-2,
                 materialpenalty: int = 8,
                 elementname: str = "C3D4",
                 ) -> None:
        """
        Initialize the SIMPMaterials class.

        Args:
            mumax (float): The maximum shear modulus for SIMP interpolation. The actual shear modulus will be interpolated between `simp_ratio_min*mumax` and `mumax`.
            kappamax (float): The maximum bulk modulus for SIMP interpolation. The actual bulk modulus will be interpolated between `simp_ratio_min*kappamax` and `kappamax`.
            simp_ratio_min (float): The minimum ratio for SIMP interpolation. The actual material properties will be interpolated between `simp_ratio_min` and 1.
            bounding_box (list[float]): The bounding box of the design domain, specified as `[xmin, xmax, ymin, ymax, zmin, zmax]`.
            simp_field_resolution (float): The resolution of the SIMP field, specified as the size of each voxel in the field.
            degree (int): The degree of the B-spline basis functions.
            density (float): The density of the material.
            initial_ratio (float): The initial ratio for SIMP interpolation, used to initialize the control points of the BSP field.
            voidpenalfactor (float): The penalization factor for the SIMP material.
            materialpenalty (int): The penalization power for the SIMP interpolation.
        """
        super().__init__()
        self._mumax: float = float(mumax)
        """
        The maximum shear modulus for SIMP interpolation. The actual shear modulus will be interpolated between `simp_ratio_min*mumax` and `mumax`.
        """

        self._kappamax: float = float(kappamax)
        """
        The maximum bulk modulus for SIMP interpolation. The actual bulk modulus will be interpolated between `simp_ratio_min*kappamax` and `kappamax`.
        """

        self._simp_ratio_min: float = float(simp_ratio_min)
        """
        The minimum ratio for SIMP interpolation. The actual material properties will be interpolated between `simp_ratio_min` and 1.
        """

        self.simp_field: bspmap.BSP
        """
        The BSP field for SIMP interpolation. This will be used to compute the interpolated material properties.
        """

        self._density: float = float(density)
        """
        The density of the material.
        """

        self._bounding_box: list[float] = bounding_box
        """
        The bounding box of the design domain, specified as `[xmin, xmax, ymin, ymax, zmin, zmax]`.
        """

        self._simp_field_resolution: float = float(simp_field_resolution)
        """
        The resolution of the SIMP field, specified as the size of each voxel in the field.
        """

        self._degree: int = degree
        """
        The degree of the B-spline basis functions for the SIMP field.
        """

        self._bsp_size: list[int] = [int((bounding_box[1] - bounding_box[0]) / simp_field_resolution) + 1,
                                int((bounding_box[3] - bounding_box[2]) / simp_field_resolution) + 1,
                                int((bounding_box[5] - bounding_box[4]) / simp_field_resolution) + 1]
        """
        The size of the BSP field for SIMP interpolation, computed based on the bounding box and the resolution.
        """

        self._cps: torch.Tensor
        """
        The control points of the BSP field for SIMP interpolation. This will be initialized in the `initialize` method.
        """

        self._initial_ratio: float = float(initial_ratio)
        """ The initial ratio for SIMP interpolation, used to initialize the control points of the BSP field.
        """

        self.voidpenalfactor: float = float(voidpenalfactor)
        """ The penalization factor for the SIMP material. This will affect the stiffness of intermediate density materials in the optimization process.
        """

        self.materialpenalty: int = 8
        """The penalization power for the SIMP interpolation. This will affect the nonlinearity of the material interpolation in the optimization process.
        """

        self.elementname = elementname
        """ The name of the element type to which the SIMP material will be applied. """

    def pathlog_required(self) -> list[str]:
        return ['materials']


    def initialize(self, *args, **kwargs):
        super().initialize(*args, **kwargs)



        R0 = torch.ones([self._bsp_size[0], self._bsp_size[1], self._bsp_size[2], 1]) * self._initial_ratio

        basis_x = bspmap.BasisClamped(num_cps=self._bsp_size[0], degree=self._degree)
        basis_y = bspmap.BasisClamped(num_cps=self._bsp_size[1], degree=self._degree)
        basis_z = bspmap.BasisClamped(num_cps=self._bsp_size[2], degree=self._degree)

        bsp = bspmap.BSP(basis=[basis_x, basis_y, basis_z],
                         degree=self._degree,
                         size=self._bsp_size,
                         control_points=R0.cpu().numpy().reshape([-1, 1]))
        self.simp_field = bsp

        self._cps = torch.from_numpy(bsp.control_points).to(
            device=torch.get_default_device(),
            dtype=torch.get_default_dtype(),
        ).reshape(self._bsp_size + [1]).reshape([-1, 1])

    def reinitialize(self, iteration, *args, **kwargs):
        super().reinitialize(iteration, *args, **kwargs)
        self.simp_field.control_points = self._cps.cpu().numpy().reshape([-1, 1])


    def get_control_points_list(self) -> list[torch.Tensor]:
        return [self._cps.detach().clone()]

    def get_parameters(self) -> list[torch.Tensor]:
        return [self._cps.detach().clone().flatten()]

    def set_parameters(self, xlist: list[torch.Tensor]) -> None:
        self._cps = xlist[0].reshape_as(self._cps).to(self._cps.device)

    def get_variables(self) -> torch.Tensor:
        return torch.randn_like(self._cps.flatten()) * 1e-6

    def update_variables(self, x_change: torch.Tensor, max_step_length: torch.Tensor | list[torch.Tensor]) -> None:
        if isinstance(max_step_length, list):
            max_step_length = max_step_length[0]

        base_cps = self._cps.detach()
        if max_step_length.numel() == 1:
            max_step_length = max_step_length.repeat(base_cps.numel())

        max_step_length = max_step_length.reshape_as(base_cps).to(base_cps.device)
        x_change = x_change.reshape_as(base_cps)

        # Bounded update keeps variable steps stable while preserving autograd graph to x_change.
        dx = 2 / torch.pi * torch.atan(x_change.abs()) * x_change.sign() * max_step_length
        self._cps = base_cps + dx

    @property
    def density(self) -> float:
        """
        Get the density.

        Returns:
            float: The density.
        """
        return self._density
    
    @density.setter
    def density(self, value: float) -> None:
        """
        Set the density.

        Args:
            value (float): The new density.
        """
        self._density = float(value)

    def _map_bsp_designfield(self, nodes: torch.Tensor) -> torch.Tensor:
        """
        Get the ratio of maximum to minimum modulus for the given nodes.

        Args:
            nodes (torch.Tensor): The coordinates of the nodes for which to compute the ratio.

        Returns:
            torch.Tensor: The ratio of maximum to minimum modulus for the given nodes.
        """

        nodes_normalized = torch.zeros_like(nodes)
        nodes_normalized[:, 0] = (nodes[:, 0] - self._bounding_box[0]) / (self._bounding_box[1] - self._bounding_box[0])
        nodes_normalized[:, 1] = (nodes[:, 1] - self._bounding_box[2]) / (self._bounding_box[3] - self._bounding_box[2])
        nodes_normalized[:, 2] = (nodes[:, 2] - self._bounding_box[4]) / (self._bounding_box[5] - self._bounding_box[4])

        idx_remain = (nodes_normalized[:, 0] >= 0.0) & (nodes_normalized[:, 0] <= 1.0) & (nodes_normalized[:, 1] >= 0.0) & (nodes_normalized[:, 1] <= 1.0) & (nodes_normalized[:, 2] >= 0.0) & (nodes_normalized[:, 2] <= 1.0)

        weights, indices = self.simp_field.get_weights(nodes_normalized.detach().cpu().numpy())

        weights = torch.from_numpy(weights).to(nodes.device, dtype=self._cps.dtype).flatten()

        indices_cps = torch.from_numpy(indices).to(nodes.device).reshape([nodes.shape[0], -1])
        indices_pts = torch.arange(nodes.shape[0], device=nodes.device).reshape([-1,1]).repeat(1, indices_cps.shape[1])
        indices = torch.stack([indices_pts, indices_cps], dim=0).reshape(2, -1)

        num_pts = nodes.shape[0]

        idx_remain_flatten = torch.where(torch.isin(indices[0], torch.where(idx_remain)[0]))[0]
        weights = weights[idx_remain_flatten]
        indices = indices[:, idx_remain_flatten]
        
        result = torch.zeros([num_pts, 1], dtype=self._cps.dtype, device=nodes.device)
        result[:, 0].scatter_add_(0, indices[0], weights * self._cps[indices[1], 0])

        result[~idx_remain] = 0.0

        return result
    
    def _map_bsp_designfield_with_spartial_derivative(self, nodes: torch.Tensor) -> torch.Tensor:
        """
        Get the ratio of maximum to minimum modulus for the given nodes.

        Args:
            nodes (torch.Tensor): The coordinates of the nodes for which to compute the ratio.

        Returns:
            torch.Tensor: The ratio of maximum to minimum modulus for the given nodes.
        """

        nodes_normalized = torch.zeros_like(nodes)
        nodes_normalized[:, 0] = (nodes[:, 0] - self._bounding_box[0]) / (self._bounding_box[1] - self._bounding_box[0])
        nodes_normalized[:, 1] = (nodes[:, 1] - self._bounding_box[2]) / (self._bounding_box[3] - self._bounding_box[2])
        nodes_normalized[:, 2] = (nodes[:, 2] - self._bounding_box[4]) / (self._bounding_box[5] - self._bounding_box[4])

        weights, indices = self.simp_field.get_weights(nodes_normalized.detach().cpu().numpy())
        wdx = self.simp_field.get_weights(nodes_normalized.detach().cpu().numpy(), derivative=[1,0,0])[0]
        wdy = self.simp_field.get_weights(nodes_normalized.detach().cpu().numpy(), derivative=[0,1,0])[0]
        wdz = self.simp_field.get_weights(nodes_normalized.detach().cpu().numpy(), derivative=[0,0,1])[0]

        weights = torch.from_numpy(weights).to(nodes.device, dtype=self._cps.dtype).flatten()
        wdx = torch.from_numpy(wdx).to(nodes.device, dtype=self._cps.dtype).flatten()
        wdy = torch.from_numpy(wdy).to(nodes.device, dtype=self._cps.dtype).flatten()
        wdz = torch.from_numpy(wdz).to(nodes.device, dtype=self._cps.dtype).flatten()

        indices_cps = torch.from_numpy(indices).to(nodes.device).reshape([nodes.shape[0], -1])
        indices_pts = torch.arange(nodes.shape[0], device=nodes.device).reshape([-1,1]).repeat(1, indices_cps.shape[1])
        indices = torch.stack([indices_pts, indices_cps], dim=0).reshape(2, -1)

        num_pts = nodes.shape[0]
        
        result = torch.zeros([num_pts, 1], dtype=self._cps.dtype, device=nodes.device)
        result[:, 0].scatter_add_(0, indices[0], weights * self._cps[indices[1], 0])
        rdx = torch.zeros([num_pts, 1], dtype=self._cps.dtype, device=nodes.device)
        rdx[:, 0].scatter_add_(0, indices[0], wdx * self._cps[indices[1], 0])
        rdy = torch.zeros([num_pts, 1], dtype=self._cps.dtype, device=nodes.device)
        rdy[:, 0].scatter_add_(0, indices[0], wdy * self._cps[indices[1], 0])
        rdz = torch.zeros([num_pts, 1], dtype=self._cps.dtype, device=nodes.device)
        rdz[:, 0].scatter_add_(0, indices[0], wdz * self._cps[indices[1], 0])

        surrogate = (
            + rdx.detach() * nodes_normalized[:, 0:1]
            + rdy.detach() * nodes_normalized[:, 1:2]
            + rdz.detach() * nodes_normalized[:, 2:3]
        )

        result = result + (surrogate - surrogate.detach())
        return result


    def get_material_ratio(self, designfield: torch.Tensor) -> torch.Tensor:
        """
        Get the material density rho for the given ratio.

        Args:
            designfield (torch.Tensor): The design field values.
        Returns:
            torch.Tensor: The material density rho for the given ratio.
        """

        rho = 1 / (1 + torch.exp(-designfield))

        rho_penalty = RAMP_interpolation(rho, p=self.materialpenalty)

        ratio = rho_penalty * (1 - self._simp_ratio_min) + self._simp_ratio_min

        return ratio
    
    def get_penalty_factor(self, designfield: torch.Tensor) -> torch.Tensor:
        """
        Get the penalty factor for the given design field.

        Args:
            designfield (torch.Tensor): The design field values.

        Returns:
            torch.Tensor: The penalty factor for the given design field.
        """

        influence_max = -3
        influence_min = -6

        normalized_designfield = (influence_max - designfield) / (influence_max - influence_min)
        normalized_designfield = torch.clamp(normalized_designfield, 0.0, 1.0)

        penalty_factor = 6 * normalized_designfield**5 - 15 * normalized_designfield**4 + 10 * normalized_designfield**3

        return penalty_factor

    def set_materials(self, fe: torchfea.FEAController) -> None:
        """
        Set the materials of the FEA model.

        Args:
            fe (torchfea.FEAController): The FEA controller.
        """

        # Set the SIMP materials for the solid elements
        elements = fe.assembly.get_part('final_model').elems[self.elementname]

        elements_new = SIMPElementC3D10(elems_index=elements._elems_index, elems=elements._elems, penalfactor=self.voidpenalfactor)
        fe.assembly.get_part('final_model').elems[self.elementname] = elements_new

        nodes = fe.assembly.get_part('final_model').nodes
        elements_new._pre_load_gaussian(nodes=nodes)

        gaussian_points_locations = elements_new.get_gaussian_points(nodes=nodes)

        shape_gaussian = gaussian_points_locations.shape
        gaussian_points_locations = gaussian_points_locations.reshape([-1, 3])

        designfield = self._map_bsp_designfield(gaussian_points_locations).reshape([shape_gaussian[0], shape_gaussian[1]])
        ratio_now = self.get_material_ratio(designfield)

        mu = ratio_now * self._mumax
        kappa = ratio_now * self._kappamax

        materials = torchfea.materials.NeoHookeanLnJ(mu=mu, kappa=kappa)
        elements_new.set_materials(materials)
        elements_new.density = self.density
        elements_new.penalfactor = self.get_penalty_factor(designfield) * self.voidpenalfactor


    def obtain_design_sensitivity_vars(self, assembly: torchfea.Assembly) -> torch.Tensor:
        """
        Get the design sensitivity variables for the optimization process.

        Returns:
            torch.Tensor: The design sensitivity variables.
        """
        return self._cps.flatten().clone().detach()

    def modify_assembly(self, design_sensitivity_vars: torch.Tensor, assembly: torchfea.Assembly) -> None:
        """
        Modify the assembly for sensitivity analysis.
        geometry parameters will contains the nodes of the fea model, and the assembly will be modified according to the geometry parameters.
        """

        gaussian_points_locations = self._get_gaussian_points(assembly)
        
        shape_gaussian = gaussian_points_locations.shape
        gaussian_points_locations = gaussian_points_locations.reshape([-1, 3])


        self._cps = design_sensitivity_vars.reshape_as(self._cps)

        designfield = self._map_bsp_designfield_with_spartial_derivative(gaussian_points_locations).reshape([shape_gaussian[0], shape_gaussian[1]])

        ratio_now = self.get_material_ratio(designfield)


        elems: SIMPElementC3D10 = assembly.get_part("final_model").elems[self.elementname]
        
        elems.materials['material-0']._mu = ratio_now * self._mumax
        elems.materials['material-0']._kappa = ratio_now * self._kappamax
        elems.penalfactor = self.get_penalty_factor(designfield) * self.voidpenalfactor
        elems._initialize_simppenalty()


    def save(self, foldpath: str, iteration: int) -> None:
        path_now = f"{foldpath}{self.pathlog_required()[0]}/simp_material_iter_{iteration}.npz"
        np.savez_compressed(
            path_now,
            cps=self._cps.detach().cpu().numpy().astype(np.float16),
            bsp_size=np.array(self._bsp_size, dtype=np.int64),
            bounding_box=np.array(self._bounding_box, dtype=np.float64),
            degree=np.array([self._degree], dtype=np.int64),
            density=np.array([self._density], dtype=np.float64),
        )

        import pyvista as pv
        plotter = pv.Plotter(off_screen=True, window_size=(1400, 1000))
        self.plot(plotter=plotter)
        plotter.screenshot(f"{foldpath}{self.pathlog_required()[0]}/density_field_{iteration}.jpg")
        plotter.close()

    def load(self, foldpath: str, iteration: int) -> None:
        path_now = f"{foldpath}{self.pathlog_required()[0]}/simp_material_iter_{iteration}.npz"
        data = np.load(path_now)

        cps_np = data["cps"].astype(np.float64)
        self._cps = torch.from_numpy(cps_np).to(
            device=torch.get_default_device(),
            dtype=torch.get_default_dtype(),
        ).reshape_as(self._cps)

        if "density" in data:
            self._density = float(data["density"][0])

        # Keep BSP map synchronized with control points used in optimization.
        self.simp_field.control_points = self._cps.detach().cpu().numpy().reshape([-1, 1])

    def get_volume(self):
        xmin, xmax, ymin, ymax, zmin, zmax = self._bounding_box
        nx, ny, nz = self._bsp_size

        # Query a denser field (3x control-point resolution per axis) instead of
        # visualizing control points directly.
        nx_q = max(2, (nx - 1) * 2 + 1)
        ny_q = max(2, (ny - 1) * 2 + 1)
        nz_q = max(2, (nz - 1) * 2 + 1)

        xq = np.linspace(xmin, xmax, nx_q)
        yq = np.linspace(ymin, ymax, ny_q)
        zq = np.linspace(zmin, zmax, nz_q)
        xg, yg, zg = np.meshgrid(xq, yq, zq, indexing="ij")
        pts_query = np.stack([xg, yg, zg], axis=-1).reshape(-1, 3)

        designfield = self._map_bsp_designfield(torch.from_numpy(pts_query).to(torch.get_default_device()).to(torch.get_default_dtype()))

        ratio_query = self.get_material_ratio(designfield).reshape(nx_q, ny_q, nz_q).cpu().numpy()
        ratio_grid = np.clip(ratio_query, 0.0, 1.0)

        sx = (xmax - xmin) / max(nx_q - 1, 1)
        sy = (ymax - ymin) / max(ny_q - 1, 1)
        sz = (zmax - zmin) / max(nz_q - 1, 1)

        grid = pv.ImageData(
            dimensions=(nx_q, ny_q, nz_q),
            spacing=(sx, sy, sz),
            origin=(xmin, ymin, zmin),
        )
        grid.point_data["ratio"] = ratio_grid.flatten(order="F")

        return grid

    def plot(self, plotter=None):
        import pyvista as pv

        if plotter is None:
            plotter = pv.Plotter(window_size=(1400, 1000))

        grid = self.get_volume()

        plotter.set_background("#ffffff")
        volume_actor = plotter.add_volume(
            grid,
            scalars="ratio",
            cmap="viridis",
            clim=[0.0, 1.0],
            opacity=[0.0, 0.02, 0.08, 0.2, 0.45, 0.75, 1.0],
            shade=True,
            ambient=0.25,
            diffuse=0.7,
            specular=0.15,
            specular_power=8.0,
        )
        if hasattr(volume_actor, 'mapper'):
            volume_actor.mapper.scalar_range = (0.0, 1.0)

        plotter.add_bounding_box(color="black", line_width=1.2)
        plotter.show_bounds(xtitle="X", ytitle="Y", ztitle="Z", color="black")
        plotter.add_text("SIMP Density Field", position="upper_left", font_size=12, color="black")
        plotter.add_scalar_bar(mapper=volume_actor.mapper if hasattr(volume_actor, 'mapper') else None, title="Density Ratio", n_labels=5, bold=True)

        plotter.enable_parallel_projection()
        # Add some padding to the bounds
        padding = 0.05 * max(self._bounding_box[1] - self._bounding_box[0], 
                             self._bounding_box[3] - self._bounding_box[2], 
                             self._bounding_box[5] - self._bounding_box[4])
        
        plotter.show_bounds(xtitle='X', ytitle='Y', ztitle='Z', color='black',
                            bounds=[self._bounding_box[0]-padding, self._bounding_box[1]+padding, 
                                    self._bounding_box[2]-padding, self._bounding_box[3]+padding, 
                                    self._bounding_box[4]-padding, self._bounding_box[5]+padding])
        
        plotter.enable_parallel_projection()
        azimuth = 210
        elevation = 20
        plotter.view_vector((math.cos(math.radians(azimuth)) * math.cos(math.radians(elevation)),
            math.sin(math.radians(azimuth)) * math.cos(math.radians(elevation)),
            math.sin(math.radians(elevation))))
        
        return plotter
    
    def _get_gaussian_points(self, assembly: torchfea.Assembly) -> torch.Tensor:
        """
        Get the normalized Gaussian points for the elements in the assembly.

        Args:
            assembly (torchfea.Assembly): The FEA assembly.

        Returns:
            torch.Tensor: The normalized Gaussian points.
        """
        gaussian_points_locations = assembly.get_part('final_model').elems[self.elementname].get_gaussian_points(assembly.get_part('final_model').nodes)

        return gaussian_points_locations