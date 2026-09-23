import os

import bspmap
import numpy as np
import pyvista as pv
import torch
import torchfea

from ..optcore.modelparams.materialinterface import (
    BaseMaterialInterface,
    MaterialModels,
)
from ..optcore.protocal import ProtocalUpdatable


class SIMPScaledMaterial(torchfea.materials.Materials_Base):
    """Apply a spatial SIMP scale to any torchfea material model."""

    def __init__(
        self,
        base_material: torchfea.materials.Materials_Base,
        scale: torch.Tensor,
    ) -> None:
        super().__init__()
        self.base_material = base_material
        self.scale = scale
        # torchfea's concrete materials declare ``type`` (the inp material slot:
        # 1 = hyperelastic, 2 = linear); the abstract base does not
        self.type: int = int(base_material.type)

    def strain_energy_density_C3(self, F: torch.Tensor) -> torch.Tensor:
        energy = self.base_material.strain_energy_density_C3(F=F)
        return energy * self.scale

    def material_Constitutive_C3(
        self,
        F: torch.Tensor,
        J: torch.Tensor | None = None,
        Jneg: torch.Tensor | None = None,
        invF: torch.Tensor | None = None,
        I1: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        stress, tangent = self.base_material.material_Constitutive_C3(
            F=F, J=J, Jneg=Jneg, invF=invF, I1=I1
        )
        stress_scale = self.scale[..., None, None]
        tangent_scale = self.scale[..., None, None, None, None]
        return stress * stress_scale, tangent * tangent_scale


# region for void elements penalization
class SIMPElementFgrad(torchfea.elements.Element_3D):
    _serialized_attributes_exclude = (
        torchfea.elements.Element_3D._serialized_attributes_exclude
        + ["_EmdUe_2", "_dN2WP"]
    )

    def __init__(
        self,
        elems_index: torch.Tensor,
        elems: torch.Tensor,
        penalfactor: torch.Tensor | float,
    ) -> None:
        super().__init__(elems_index, elems)

        if isinstance(penalfactor, float):
            penalfactor = torch.tensor([penalfactor], dtype=torch.get_default_dtype())

        if penalfactor.dim() == 0 or penalfactor.shape == (1,):
            penalfactor = penalfactor.reshape(1, 1)

        self.penalfactor = penalfactor
        """the penalization factor for SIMP material"""

    def initialize(self, *args: object, **kwargs: object) -> None:
        super().initialize(*args, **kwargs)

        self._dN2WP = torch.einsum(
            "geija,ge->geija",
            self.shape_function_d2_gaussian,
            self.gaussian_weight * self.penalfactor,
        )

        self._EmdUe_2 = torch.zeros(
            [
                self.num_nodes_per_elem,
                3,
                self.num_nodes_per_elem,
                3,
                self._elems.shape[0],
            ]
        )

        for I0 in range(3):
            for i0 in range(3):
                for j0 in range(3):
                    I = I0
                    i = i0
                    j = j0
                    J = I0
                    k = i0
                    l = j0

                    self._EmdUe_2[:, I, :, J, :] += (
                        torch.einsum(
                            "gea, geb->abe",
                            self._dN2WP[:, :, i, j, :],
                            self.shape_function_d2_gaussian[:, :, k, l, :],
                        )
                        * 2
                    )

    def potential_Energy(
        self,
        RGC: torch.Tensor,
        rotation_matrix: torch.Tensor | None = None,
    ) -> torch.Tensor:

        U = RGC

        if rotation_matrix is not None:
            U = torch.einsum("ij,aj->ai", rotation_matrix.T, U)

        Ea = super().potential_Energy(RGC, rotation_matrix)

        Ugrad2 = torch.zeros([self._num_gaussian, self._elems.shape[0], 3, 3, 3])
        for i in range(self.num_nodes_per_elem):
            Ugrad2 += torch.einsum(
                "geij,eI->geIij",
                self.shape_function_d2_gaussian[..., i],
                U[self._elems[:, i]],
            )

        Er = torch.einsum(
            "geIij,geIij,ge->", Ugrad2, Ugrad2, self.gaussian_weight * self.penalfactor
        )

        return Ea + Er

    def _get_EpdUe_EpdUe2(
        self,
        U: torch.Tensor,
        if_onlyforce: bool = False,
    ) -> torch.Tensor | tuple[torch.Tensor, torch.Tensor]:
        result0 = super()._get_EpdUe_EpdUe2(U, if_onlyforce)

        Ugrad2 = torch.zeros([self._num_gaussian, self._elems.shape[0], 3, 3, 3])
        for i in range(self.num_nodes_per_elem):
            Ugrad2 += torch.einsum(
                "geij,eI->geIij",
                self.shape_function_d2_gaussian[..., i],
                U[self._elems[:, i]],
            )

        EmdUgrad2 = 2 * Ugrad2

        EmdUe = torch.einsum("geIij,geija->aIe", EmdUgrad2, self._dN2WP)

        if if_onlyforce:
            return EmdUe + result0

        return EmdUe + result0[0], self._EmdUe_2 + result0[1]


class SIMPElementFskew(torchfea.elements.Element_3D):
    _serialized_attributes_exclude = (
        torchfea.elements.Element_3D._serialized_attributes_exclude
        + ["_EmdUe_2", "_dN2WP"]
    )

    def __init__(
        self,
        elems_index: torch.Tensor,
        elems: torch.Tensor,
        penalfactor: torch.Tensor | float,
    ) -> None:
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

    def initialize(self, *args: object, **kwargs: object) -> None:
        super().initialize(*args, **kwargs)

        self._initialize_simppenalty()

    def _initialize_simppenalty(self) -> None:
        """
        initialize the penalty for SIMP material, which will be used in the energy and force calculations.
        """
        self._dN2WP = torch.einsum(
            "geija,ge->geija",
            self.shape_function_d2_gaussian,
            self.gaussian_weight * self._penalfactor,
        )

        self._EmdUe_2 = torch.zeros(
            [
                self.num_nodes_per_elem,
                3,
                self.num_nodes_per_elem,
                3,
                self._elems.shape[0],
            ]
        )

        for I0 in range(3):
            for i0 in range(3):
                for j0 in range(3):
                    I = I0
                    i = i0
                    j = j0
                    J = I0
                    k = i0
                    l = j0

                    self._EmdUe_2[:, I, :, J, :] += (
                        torch.einsum(
                            "gea, geb->abe",
                            self._dN2WP[:, :, i, j, :],
                            self.shape_function_d2_gaussian[:, :, k, l, :],
                        )
                        * 4
                    )

                    I = I0
                    i = i0
                    j = j0
                    J = i0
                    k = I0
                    l = j0

                    self._EmdUe_2[:, I, :, J, :] += (
                        torch.einsum(
                            "gea, geb->abe",
                            self._dN2WP[:, :, i, j, :],
                            self.shape_function_d2_gaussian[:, :, k, l, :],
                        )
                        * -4
                    )

    def potential_Energy(
        self,
        RGC: torch.Tensor,
        rotation_matrix: torch.Tensor | None = None,
    ) -> torch.Tensor:

        U = RGC

        if rotation_matrix is not None:
            U = torch.einsum("ij,aj->ai", rotation_matrix.T, U)

        Ea = super().potential_Energy(RGC, rotation_matrix)

        Ugrad2 = torch.zeros([self._num_gaussian, self._elems.shape[0], 3, 3, 3])
        for i in range(self.num_nodes_per_elem):
            Ugrad2 += torch.einsum(
                "geij,eI->geIij",
                self.shape_function_d2_gaussian[..., i],
                U[self._elems[:, i]],
            )

        Fskew = Ugrad2 - Ugrad2.transpose(2, 3)

        Er = torch.einsum(
            "geIij,ge->", Fskew**2, self.gaussian_weight * self.penalfactor
        )

        return Ea + Er

    def _get_EpdUe_EpdUe2(
        self,
        U: torch.Tensor,
        if_onlyforce: bool = False,
    ) -> torch.Tensor | tuple[torch.Tensor, torch.Tensor]:
        result0 = super()._get_EpdUe_EpdUe2(U, if_onlyforce)

        Ue = U[self._elems]

        Ugrad2 = torch.zeros([self._num_gaussian, self._elems.shape[0], 3, 3, 3])
        for i in range(self.num_nodes_per_elem):
            Ugrad2 += torch.einsum(
                "geij,eI->geIij", self.shape_function_d2_gaussian[..., i], Ue[:, i]
            )

        # Fskew_geijk = Ugrad2_geijk - Ugrad2_geikj
        # Fskew = Ugrad2 - Ugrad2.transpose(2, 3)

        # E = p Fskew_geijk Fskew_geijk w_ge
        # Er = torch.einsum('geIij,geIij,ge->', Fskew, Fskew, self.gaussian_weight * self.penalfactor)

        EmdUgrad2 = 4 * (Ugrad2 - Ugrad2.transpose(2, 3))

        EmdUe = torch.einsum("geIij,geija->aIe", EmdUgrad2, self._dN2WP)

        if if_onlyforce:
            return EmdUe + result0

        return EmdUe + result0[0], self._EmdUe_2 + result0[1]


class SIMPElementHuHu_LuLu(torchfea.elements.Element_3D):
    _serialized_attributes_exclude = (
        torchfea.elements.Element_3D._serialized_attributes_exclude
        + ["_EmdUe_2", "_dN2WP"]
    )

    def __init__(
        self,
        elems_index: torch.Tensor,
        elems: torch.Tensor,
        penalfactor: torch.Tensor,
    ) -> None:
        super().__init__(elems_index, elems)

        self._penalfactor = penalfactor
        """the penalization factor for SIMP material"""

    def initialize(self, *args: object, **kwargs: object) -> None:
        super().initialize(*args, **kwargs)

        if self._penalfactor.dim() == 0 or self._penalfactor.shape == (1,):
            self._penalfactor = self._penalfactor.reshape(1, 1)

        self._dN2WP = torch.einsum(
            "geija,ge->geija",
            self.shape_function_d2_gaussian,
            self.gaussian_weight * self._penalfactor,
        )

        self._EmdUe_2 = torch.zeros(
            [
                self.num_nodes_per_elem,
                3,
                self.num_nodes_per_elem,
                3,
                self._elems.shape[0],
            ]
        )

        for I0 in range(3):
            for i0 in range(3):
                I = I0
                i = i0
                j = i0
                J = I0
                k = i0
                l = i0

                self._EmdUe_2[:, I, :, J, :] -= (
                    torch.einsum(
                        "gea, geb->abe",
                        self._dN2WP[:, :, i, j, :],
                        self.shape_function_d2_gaussian[:, :, k, l, :],
                    )
                    / 3
                )

                for j0 in range(3):
                    I = I0
                    i = i0
                    j = j0
                    J = I0
                    k = i0
                    l = j0

                    self._EmdUe_2[:, I, :, J, :] += torch.einsum(
                        "gea, geb->abe",
                        self._dN2WP[:, :, i, j, :],
                        self.shape_function_d2_gaussian[:, :, k, l, :],
                    )

        # self._EmdUe_2 = torch.einsum('geija, geklb,geIijJkl->aIbJe', self._dN2W, self.shape_function_d2_gaussian, EmdUgrad2_2)

    def potential_Energy(
        self,
        RGC: torch.Tensor,
        rotation_matrix: torch.Tensor | None = None,
    ) -> torch.Tensor:

        U = RGC

        if rotation_matrix is not None:
            U = torch.einsum("ij,aj->ai", rotation_matrix.T, U)

        Ea = super().potential_Energy(RGC, rotation_matrix)

        Ugrad2 = torch.zeros([self._num_gaussian, self._elems.shape[0], 3, 3, 3])
        for i in range(self.num_nodes_per_elem):
            Ugrad2 += torch.einsum(
                "geij,eI->geIij",
                self.shape_function_d2_gaussian[..., i],
                U[self._elems[:, i]],
            )

        Er = 0.5 * (Ugrad2**2).sum([2, 3, 4])
        for i in range(3):
            Er -= 0.5 * (Ugrad2[:, :, :, i, i] ** 2).sum([-1]) / 3

        Er = (Er * self.gaussian_weight * self._penalfactor).sum()

        return Ea + Er

    def _get_EpdUe_EpdUe2(
        self,
        U: torch.Tensor,
        if_onlyforce: bool = False,
    ) -> torch.Tensor | tuple[torch.Tensor, torch.Tensor]:
        result0 = super()._get_EpdUe_EpdUe2(U, if_onlyforce)

        Ugrad2 = torch.zeros([self._num_gaussian, self._elems.shape[0], 3, 3, 3])
        for i in range(self.num_nodes_per_elem):
            Ugrad2 += torch.einsum(
                "geij,eI->geIij",
                self.shape_function_d2_gaussian[..., i],
                U[self._elems[:, i]],
            )

        Er = self.potential_Energy(U)

        EmdUgrad2 = Ugrad2
        for i in range(3):
            EmdUgrad2[:, :, :, i, i] -= Ugrad2[:, :, :, i, i] / 3

        EmdUe = torch.einsum("geIij,geija->aIe", EmdUgrad2, self._dN2WP)

        if if_onlyforce:
            return EmdUe + result0

        return EmdUe + result0[0], self._EmdUe_2 + result0[1]


class SIMPElementC3D4(torchfea.elements.C3D4, SIMPElementFskew):
    """C3D4 adapter for the optional SIMP Fskew penalty.

    C3D4 is a linear tetrahedral element, so its second shape-function
    derivatives are zero and the Fskew term evaluates to zero.  It still
    needs the adapter when the penalty option is enabled because the
    sensitivity update refreshes the penalty caches uniformly for all SIMP
    elements.
    """


class SIMPElementC3D10(torchfea.elements.C3D10, SIMPElementFskew):
    pass


class SIMPElementC3D8(torchfea.elements.C3D8, SIMPElementFskew):
    pass


class SIMPElementC3D20(torchfea.elements.C3D20, SIMPElementFskew):
    pass


# endregion


def RAMP_interpolation(rho: torch.Tensor, p: int) -> torch.Tensor:
    """
    RAMP interpolation function for SIMP method.

    Args:
        rho (torch.Tensor): The material density.
        p (int): The penalization power.

    Returns:
        torch.Tensor: The interpolated material property.
    """
    return rho / (1 + p * (1 - rho))


def p_order_interpolation(rho: torch.Tensor, p: int) -> torch.Tensor:
    """
    p-order interpolation function for SIMP method.

    Args:
        rho (torch.Tensor): The material density.
        p (int): The penalization power.

    Returns:
        torch.Tensor: The interpolated material property.
    """
    return rho**p


class SIMP_BSPFieldMaterials(BaseMaterialInterface, ProtocalUpdatable):
    """
    Class to handle the materials of the morphable model.
    """

    def __init__(
        self,
        mumax: float,
        kappamax: float,
        simp_ratio_min: float,
        bounding_box: list[float],
        simp_field_resolution: float,
        degree: int,
        material_parameters: MaterialModels.MaterialParameters,
        part_name: str,
        density: float = 0.0,
        initial_ratio: float = 0.5,
        voidpenalfactor: float = 1e-2,
        materialpenalty: int = 8,
        elementname: str = "",
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
        super().__init__(
            part_name=part_name,
            elementname=elementname,
            material_parameters=material_parameters,
            density=density,
        )
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

        self._bsp_size: list[int] = [
            int((bounding_box[1] - bounding_box[0]) / simp_field_resolution) + 1,
            int((bounding_box[3] - bounding_box[2]) / simp_field_resolution) + 1,
            int((bounding_box[5] - bounding_box[4]) / simp_field_resolution) + 1,
        ]
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

        self.materialpenalty: int = int(materialpenalty)
        """The penalization power for the SIMP interpolation. This will affect the nonlinearity of the material interpolation in the optimization process.
        """

        R0 = (
            torch.ones([self._bsp_size[0], self._bsp_size[1], self._bsp_size[2], 1])
            * self._initial_ratio
        )

        self._initial_field = R0.cpu().numpy().reshape([-1, 1])
        """Initial control points of the BSP field (the field itself is built
        by :meth:`initialize`, so declaring a model stays lightweight)."""

        self._field_bsp: bspmap.BSP | None = None
        """The BSP field, built on first use / by :meth:`initialize`."""

    # ------------------------------------------------------------------ field
    def _build_simp_field(self) -> bspmap.BSP:
        """Build the BSP design field from the stored parameters."""
        basis_x = bspmap.BasisClamped(num_cps=self._bsp_size[0], degree=self._degree)
        basis_y = bspmap.BasisClamped(num_cps=self._bsp_size[1], degree=self._degree)
        basis_z = bspmap.BasisClamped(num_cps=self._bsp_size[2], degree=self._degree)

        self._field_bsp = bspmap.BSP(
            basis=[basis_x, basis_y, basis_z],
            degree=self._degree,
            size=self._bsp_size,
            control_points=self._initial_field,
        )
        return self._field_bsp

    @property
    def simp_field(self) -> bspmap.BSP:
        """The BSP field of this SIMP interface."""
        if self._field_bsp is None:
            self._build_simp_field()
        return self._field_bsp

    def pathlog_required(self) -> list[str]:
        return ["materials"]

    @property
    def if_use_simppenalty(self) -> bool:
        """
        Whether to use the SIMP penalty in the finite element analysis. If True, the stiffness of intermediate density materials will be penalized, which can help to achieve a more discrete material distribution in the optimization process.

        Returns:
            bool: True if SIMP penalty is used, False otherwise.
        """
        return self.voidpenalfactor > 0

    def initialize(self, *args: object, **kwargs: object) -> None:
        super().initialize(*args, **kwargs)

        if self._field_bsp is None:
            self._build_simp_field()
        self._cps = (
            torch.from_numpy(self.simp_field.control_points)
            .to(
                device=torch.get_default_device(),
                dtype=torch.get_default_dtype(),
            )
            .reshape(self._bsp_size + [1])
            .reshape([-1, 1])
        )

    def reinitialize(self, iteration: int, *args: object, **kwargs: object) -> None:
        super().reinitialize(iteration, *args, **kwargs)
        self.simp_field.control_points = self._cps.cpu().numpy().reshape([-1, 1])

    def get_control_points_list(self) -> list[torch.Tensor]:
        return [self._cps.detach().clone()]

    @property
    def num_variables(self) -> int:
        """Number of scalar SIMP control-point variables."""
        return int(np.prod(self._bsp_size))

    def get_parameters(self) -> list[torch.Tensor]:
        return [self._cps.detach().clone().flatten()]

    def get_design_values(self) -> torch.Tensor:
        """Return live SIMP control points while preserving autograd."""
        return self._cps.flatten()

    def set_parameters(self, xlist: list[torch.Tensor]) -> None:
        self._cps = xlist[0].reshape_as(self._cps).to(self._cps.device)

    def get_variables(self) -> torch.Tensor:
        return torch.randn_like(self._cps.flatten()) * 1e-6

    def update_variables(
        self,
        x_change: torch.Tensor,
        max_step_length: torch.Tensor | list[torch.Tensor] | None = None,
    ) -> None:
        if max_step_length is None:
            max_step_length = torch.ones_like(self._cps.flatten())
        if isinstance(max_step_length, list):
            max_step_length = max_step_length[0]

        base_cps = self._cps.detach()
        if max_step_length.numel() == 1:
            max_step_length = max_step_length.repeat(base_cps.numel())

        max_step_length = max_step_length.reshape_as(base_cps).to(base_cps.device)
        x_change = x_change.reshape_as(base_cps)

        # Bounded update keeps variable steps stable while preserving autograd graph to x_change.
        dx = (
            2
            / torch.pi
            * torch.atan(x_change.abs())
            * x_change.sign()
            * max_step_length
        )
        self._cps = base_cps + dx

    def _get_indices_weight_for_nodes(
        self, nodes: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:

        nodes_normalized = torch.zeros_like(nodes)
        nodes_normalized[:, 0] = (nodes[:, 0] - self._bounding_box[0]) / (
            self._bounding_box[1] - self._bounding_box[0]
        )
        nodes_normalized[:, 1] = (nodes[:, 1] - self._bounding_box[2]) / (
            self._bounding_box[3] - self._bounding_box[2]
        )
        nodes_normalized[:, 2] = (nodes[:, 2] - self._bounding_box[4]) / (
            self._bounding_box[5] - self._bounding_box[4]
        )

        idx_remain = (
            (nodes_normalized[:, 0] >= 0.0)
            & (nodes_normalized[:, 0] <= 1.0)
            & (nodes_normalized[:, 1] >= 0.0)
            & (nodes_normalized[:, 1] <= 1.0)
            & (nodes_normalized[:, 2] >= 0.0)
            & (nodes_normalized[:, 2] <= 1.0)
        )

        weights, indices = self.simp_field.get_weights(
            nodes_normalized.detach().cpu().numpy()
        )

        weights = (
            torch.from_numpy(weights).to(nodes.device, dtype=self._cps.dtype).flatten()
        )

        indices_cps = (
            torch.from_numpy(indices).to(nodes.device).reshape([nodes.shape[0], -1])
        )
        indices_pts = (
            torch.arange(nodes.shape[0], device=nodes.device)
            .reshape([-1, 1])
            .repeat(1, indices_cps.shape[1])
        )
        indices = torch.stack([indices_pts, indices_cps], dim=0).reshape(2, -1)

        idx_remain_flatten = torch.where(
            torch.isin(indices[0], torch.where(idx_remain)[0])
        )[0]
        weights = weights[idx_remain_flatten]
        indices = indices[:, idx_remain_flatten]

        return indices, weights

    def _map_bsp_designfield(self, nodes: torch.Tensor) -> torch.Tensor:
        """
        Get the ratio of maximum to minimum modulus for the given nodes.

        Args:
            nodes (torch.Tensor): The coordinates of the nodes for which to compute the ratio.

        Returns:
            torch.Tensor: The ratio of maximum to minimum modulus for the given nodes.
        """

        if (
            nodes[:, 0].min() < self._bounding_box[0]
            or nodes[:, 0].max() > self._bounding_box[1]
            or nodes[:, 1].min() < self._bounding_box[2]
            or nodes[:, 1].max() > self._bounding_box[3]
            or nodes[:, 2].min() < self._bounding_box[4]
            or nodes[:, 2].max() > self._bounding_box[5]
        ):
            raise ValueError(
                "Some nodes are out of the bounding box of the SIMP field."
            )

        indices, weights = self._get_indices_weight_for_nodes(nodes)

        num_pts = nodes.shape[0]
        result = torch.zeros([num_pts, 1], dtype=self._cps.dtype, device=nodes.device)
        result[:, 0].scatter_add_(0, indices[0], weights * self._cps[indices[1], 0])

        return result

    def _map_bsp_designfield_with_spartial_derivative(
        self, nodes: torch.Tensor
    ) -> torch.Tensor:
        """
        Get the ratio of maximum to minimum modulus for the given nodes.

        Args:
            nodes (torch.Tensor): The coordinates of the nodes for which to compute the ratio.

        Returns:
            torch.Tensor: The ratio of maximum to minimum modulus for the given nodes.
        """

        nodes_normalized = torch.zeros_like(nodes)
        nodes_normalized[:, 0] = (nodes[:, 0] - self._bounding_box[0]) / (
            self._bounding_box[1] - self._bounding_box[0]
        )
        nodes_normalized[:, 1] = (nodes[:, 1] - self._bounding_box[2]) / (
            self._bounding_box[3] - self._bounding_box[2]
        )
        nodes_normalized[:, 2] = (nodes[:, 2] - self._bounding_box[4]) / (
            self._bounding_box[5] - self._bounding_box[4]
        )

        weights, indices = self.simp_field.get_weights(
            nodes_normalized.detach().cpu().numpy()
        )
        wdx = self.simp_field.get_weights(
            nodes_normalized.detach().cpu().numpy(), derivative=[1, 0, 0]
        )[0]
        wdy = self.simp_field.get_weights(
            nodes_normalized.detach().cpu().numpy(), derivative=[0, 1, 0]
        )[0]
        wdz = self.simp_field.get_weights(
            nodes_normalized.detach().cpu().numpy(), derivative=[0, 0, 1]
        )[0]

        weights = (
            torch.from_numpy(weights).to(nodes.device, dtype=self._cps.dtype).flatten()
        )
        wdx = torch.from_numpy(wdx).to(nodes.device, dtype=self._cps.dtype).flatten()
        wdy = torch.from_numpy(wdy).to(nodes.device, dtype=self._cps.dtype).flatten()
        wdz = torch.from_numpy(wdz).to(nodes.device, dtype=self._cps.dtype).flatten()

        indices_cps = (
            torch.from_numpy(indices).to(nodes.device).reshape([nodes.shape[0], -1])
        )
        indices_pts = (
            torch.arange(nodes.shape[0], device=nodes.device)
            .reshape([-1, 1])
            .repeat(1, indices_cps.shape[1])
        )
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
            +rdx.detach() * nodes_normalized[:, 0:1]
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

        normalized_designfield = (influence_max - designfield) / (
            influence_max - influence_min
        )
        normalized_designfield = torch.clamp(normalized_designfield, 0.0, 1.0)

        penalty_factor = (
            6 * normalized_designfield**5
            - 15 * normalized_designfield**4
            + 10 * normalized_designfield**3
        )

        return penalty_factor

    def _prepare_elements(
        self,
        elements: torchfea.elements.Element_3D,
        penalfactor: torch.Tensor | float,
    ) -> torchfea.elements.Element_3D:
        """Wrap one element family with the optional SIMP penalty adapter."""
        if not self.if_use_simppenalty:
            return elements

        # The fixed geometry is reused between optimization iterations; once
        # wrapped, keep that wrapper instead of wrapping it again.
        if isinstance(elements, SIMPElementFskew):
            return elements
        element_class = elements.__class__.__name__
        adapter = {
            "C3D4": SIMPElementC3D4,
            "C3D10": SIMPElementC3D10,
            "C3D8": SIMPElementC3D8,
            "C3D20": SIMPElementC3D20,
        }.get(element_class)
        if adapter is None:
            raise ValueError(
                f"SIMP Fskew penalty is not implemented for element type "
                f"'{element_class}'. Set voidpenalfactor=0 or use a supported "
                "solid element type."
            )
        return adapter(
            elems_index=elements._elems_index,
            elems=elements._elems,
            penalfactor=penalfactor,
        )

    def _set_one_element_material(
        self,
        elements: torchfea.elements.Element_3D,
        nodes: torch.Tensor,
    ) -> None:
        """Assign the current SIMP field to one element family."""
        elements._pre_load_gaussian(nodes=nodes)
        gaussian_points = elements.get_gaussian_points(nodes=nodes)
        shape_gaussian = gaussian_points.shape
        points = gaussian_points.reshape([-1, 3])
        designfield = self._map_bsp_designfield(points).reshape(
            [shape_gaussian[0], shape_gaussian[1]]
        )
        ratio_now = self.get_material_ratio(designfield)

        materials = SIMPScaledMaterial(
            MaterialModels.create_material(
                material_parameters=self.material_parameters,
            ),
            ratio_now,
        )
        elements.delete_material()
        elements.set_materials(materials)
        elements.density = self.density
        if self.if_use_simppenalty:
            elements.penalfactor = (
                self.get_penalty_factor(designfield) * self.voidpenalfactor
            )

    def set_materials(self, fe: torchfea.FEAController) -> None:
        """
        Set the materials of the FEA model.

        Args:
            fe (torchfea.FEAController): The FEA controller.
        """

        part = fe.assembly.get_part(self.part_name)
        for element_name, elements in self.target_elements(fe.assembly):
            elements_new = self._prepare_elements(elements, self.voidpenalfactor)
            part.elems[element_name] = elements_new
            self._set_one_element_material(elements_new, part.nodes)

    def obtain_design_sensitivity_vars(
        self, assembly: torchfea.Assembly
    ) -> torch.Tensor:
        """
        Get the design sensitivity variables for the optimization process.

        Returns:
            torch.Tensor: The design sensitivity variables.
        """
        return self._cps.flatten().clone().detach()

    def modify_assembly(
        self, design_sensitivity_vars: torch.Tensor, assembly: torchfea.Assembly
    ) -> None:
        """
        Modify the assembly for sensitivity analysis.
        geometry parameters will contains the nodes of the fea model, and the assembly will be modified according to the geometry parameters.
        """

        self._cps = design_sensitivity_vars.reshape_as(self._cps)
        self.simp_field._control_points = (
            self._cps.reshape(self.simp_field._control_points.shape)
            .detach()
            .cpu()
            .numpy()
        )
        part = assembly.get_part(self.part_name)
        for _element_name, elems in self.target_elements(assembly):
            elems._pre_load_gaussian(nodes=part.nodes)
            gaussian_points = elems.get_gaussian_points(nodes=part.nodes)
            shape_gaussian = gaussian_points.shape
            gaussian_points = gaussian_points.reshape([-1, 3])
            designfield = self._map_bsp_designfield_with_spartial_derivative(
                gaussian_points
            ).reshape([shape_gaussian[0], shape_gaussian[1]])
            ratio_now = self.get_material_ratio(designfield)
            elems.delete_material()
            elems.set_materials(
                SIMPScaledMaterial(
                    MaterialModels.create_material(
                        material_parameters=self.material_parameters,
                    ),
                    ratio_now,
                )
            )

            if self.if_use_simppenalty:
                elems.penalfactor = (
                    self.get_penalty_factor(designfield) * self.voidpenalfactor
                )
                elems._initialize_simppenalty()

    def save(self, foldpath: str, iteration: int) -> None:
        dirpath = self.save_directory(foldpath, self.name)
        path_now = os.path.join(dirpath, f"simp_material_iter_{iteration}.npz")
        np.savez_compressed(
            path_now,
            cps=self._cps.detach().cpu().numpy().astype(np.float16),
            bsp_size=np.array(self._bsp_size, dtype=np.int64),
            bounding_box=np.array(self._bounding_box, dtype=np.float64),
            degree=np.array([self._degree], dtype=np.int64),
            density=np.array([self.density], dtype=np.float64),
        )

        meshes = self.get_meshes()
        munow = meshes[0].point_data["density"]

        import matplotlib.pyplot as plt

        plt.figure(figsize=(8, 5))
        plt.hist(np.ravel(munow), bins=50, color="C0", alpha=0.8)
        plt.title(f"SIMP density histogram (iter {iteration})")
        plt.xlabel("Density")
        plt.ylabel("Count")
        plt.grid(True, linestyle="--", alpha=0.4)

        hist_path = os.path.join(
            dirpath, f"simp_material_iter_{iteration}_density_hist.png"
        )
        plt.savefig(hist_path, dpi=300, bbox_inches="tight")
        plt.close()

    def load(self, foldpath: str, iteration: int) -> None:
        dirpath = self.save_directory(foldpath, self.name)
        path_now = os.path.join(dirpath, f"simp_material_iter_{iteration}.npz")
        data = np.load(path_now)

        cps_np = data["cps"].astype(np.float64)
        self._cps = torch.from_numpy(cps_np).to(
            device=torch.get_default_device(),
            dtype=torch.get_default_dtype(),
        )

        bsp_size = data["bsp_size"].astype(np.int64)
        self._bsp_size = bsp_size.tolist()

        bounding_box = data["bounding_box"].astype(np.float64)
        self._bounding_box = bounding_box.tolist()

        degree = data["degree"].astype(np.int64)[0]
        self._degree = int(degree)

        density = data["density"].astype(np.float64)
        self.density = float(density[0])

        # build self.simp_field according to loaded data
        basis_x = bspmap.BasisClamped(num_cps=self._bsp_size[0], degree=self._degree)
        basis_y = bspmap.BasisClamped(num_cps=self._bsp_size[1], degree=self._degree)
        basis_z = bspmap.BasisClamped(num_cps=self._bsp_size[2], degree=self._degree)

        bsp = bspmap.BSP(
            basis=[basis_x, basis_y, basis_z],
            degree=self._degree,
            size=self._bsp_size,
            control_points=self._cps.detach().cpu().numpy().reshape([-1, 1]),
        )
        # ``simp_field`` is a read-only view that lazily exposes the backing
        # BSP object.  Restore that backing object directly during restart.
        self._field_bsp = bsp

    def get_meshes(self) -> list[pv.DataSet]:
        xmin, xmax, ymin, ymax, zmin, zmax = self._bounding_box
        nx, ny, nz = self._bsp_size

        # Sample at the BSP control-point resolution × 2 for smooth rendering
        nx_q = max(2, (nx - 1) * 2 + 1)
        ny_q = max(2, (ny - 1) * 2 + 1)
        nz_q = max(2, (nz - 1) * 2 + 1)

        xq = np.linspace(xmin, xmax, nx_q)
        yq = np.linspace(ymin, ymax, ny_q)
        zq = np.linspace(zmin, zmax, nz_q)
        xg, yg, zg = np.meshgrid(xq, yq, zq, indexing="ij")
        pts_query = np.stack([xg, yg, zg], axis=-1).reshape(-1, 3)

        designfield = self._map_bsp_designfield(
            torch.from_numpy(pts_query)
            .to(torch.get_default_device())
            .to(torch.get_default_dtype())
        )
        ratio_query = (
            self.get_material_ratio(designfield).reshape(nx_q, ny_q, nz_q).cpu().numpy()
        )
        ratio_grid = np.clip(ratio_query, 0.0, 1.0)

        spacing = (
            (xmax - xmin) / max(nx_q - 1, 1),
            (ymax - ymin) / max(ny_q - 1, 1),
            (zmax - zmin) / max(nz_q - 1, 1),
        )
        grid = pv.ImageData(
            dimensions=(nx_q, ny_q, nz_q),
            spacing=spacing,
            origin=(xmin, ymin, zmin),
        )
        grid.point_data["density"] = (
            ratio_grid.flatten(order="F") * self._mumax
        )  # Scale by mumax for better visualization of the material distribution

        return [grid]

    def plot(
        self,
        plotter: pv.Plotter | None = None,
        meshes: pv.DataSet | None = None,
    ) -> pv.Plotter:
        import pyvista as pv

        if plotter is None:
            plotter = pv.Plotter(window_size=(1400, 1000))

        if meshes is None:
            meshes = self.get_meshes()[0]

        # Threshold to convert ImageData → UnstructuredGrid with all cells
        # preserved, so per-element opacity works (add_mesh on raw ImageData
        # only renders the outer surface).
        thresh = meshes.threshold(value=0.5 * self._mumax, scalars="density")

        if thresh.n_cells > 0:
            plotter.add_mesh(
                thresh,
                scalars="density",
                cmap="viridis",
                show_edges=False,
                lighting=True,
                clim=[0, self._mumax],
                smooth_shading=True,
            )

        return plotter
