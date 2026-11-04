import torch
import torchfea


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

        # Er = self.potential_Energy(U)

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
