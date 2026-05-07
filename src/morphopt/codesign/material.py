import math
from typing import Optional

import torch
import numpy as np

import torchfea
from .. import SIMPMaterials
import bspmap


class CodesignMaterials(SIMPMaterials):
    """
    Class to handle the materials of the model for codesign optimization.
    """

    def __init__(self, mumax, kappamax, simp_ratio_min, bounding_box, simp_field_resolution, degree, density, initial_ratio,
                 shell_mu: float, 
                 shell_kappa: float, 
                 shell_density: float,
                 penalfactor: float = 1e-2):
        
        super().__init__(mumax, kappamax, simp_ratio_min, bounding_box, simp_field_resolution, degree, density, initial_ratio)

        self.shell_mu = shell_mu
        """ The shear modulus of the shell material. """

        self.shell_kappa = shell_kappa
        """ The bulk modulus of the shell material. """

        self.shell_density = shell_density
        """ The density of the shell material. """

        self.penalfactor = penalfactor
        """ The penalization factor for the SIMP material. """


    class SIMPElementFgrad(torchfea.elements.Element_3D):

        def __init__(self, elems_index, elems, penalfactor: torch.Tensor):
            super().__init__(elems_index, elems)

            self.penalfactor = penalfactor
            """the penalization factor for SIMP material"""

        def initialize(self, *args, **kwargs):
            super().initialize(*args, **kwargs)
            self._dN2W = torch.einsum('geija,ge->geija', self.shape_function_d2_gaussian, self.gaussian_weight)

            EmdUgrad2_2 = torch.zeros([1, 1, 3, 3, 3, 3, 3, 3])
            for I0 in range(3):
                for i0 in range(3):
                    for j0 in range(3):
                        EmdUgrad2_2[..., I0, i0, j0, I0, i0, j0] = self.penalfactor * 2

            self._EmdUe_2 = torch.einsum('geija, geklb,geIijJkl->aIbJe', self._dN2W, self.shape_function_d2_gaussian, EmdUgrad2_2)

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
                
            Er = self.penalfactor * torch.einsum('geIij,geIij,ge->', Ugrad2, Ugrad2, self.gaussian_weight)


            return Ea + Er
        
        def _get_EpdUe_EpdUe2(self, U, if_onlyforce = False):
            result0 = super()._get_EpdUe_EpdUe2(U, if_onlyforce)

            Ugrad2 = torch.zeros([self._num_gaussian, self._elems.shape[0], 3, 3, 3])
            for i in range(self.num_nodes_per_elem):
                Ugrad2 += torch.einsum('geij,eI->geIij',
                                            self.shape_function_d2_gaussian[..., i],
                                            U[self._elems[:, i]])
                
            EmdUgrad2 = 2 * self.penalfactor * Ugrad2

            EmdUe = torch.einsum('geIij,geija->aIe', EmdUgrad2,
                                    self._dN2W)
            
            if if_onlyforce:
                return EmdUe + result0

            return EmdUe + result0[0], self._EmdUe_2 + result0[1]

    class SIMPElementFsrew(torchfea.elements.Element_3D):

        def __init__(self, elems_index, elems, penalfactor: torch.Tensor):
            super().__init__(elems_index, elems)

            self.penalfactor = penalfactor
            """the penalization factor for SIMP material"""

        def initialize(self, *args, **kwargs):
            super().initialize(*args, **kwargs)
            self._dN2W = torch.einsum('geija,ge->geija', self.shape_function_d2_gaussian, self.gaussian_weight)

            EmdUgrad2_2 = torch.zeros([1, 1, 3, 3, 3, 3, 3, 3])
            for I0 in range(3):
                for i0 in range(3):
                    for j0 in range(3):
                        EmdUgrad2_2[..., I0, i0, j0, I0, i0, j0] += self.penalfactor * 4
                        EmdUgrad2_2[..., I0, i0, j0, i0, I0, j0] += -self.penalfactor * 4

            self._EmdUe_2 = torch.einsum('geija, geklb,geIijJkl->aIbJe', self._dN2W, self.shape_function_d2_gaussian, EmdUgrad2_2)

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

            Er = self.penalfactor * torch.einsum('geIij,geIij,ge->', Fskew, Fskew, self.gaussian_weight)


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
            Fskew = Ugrad2 - Ugrad2.transpose(2, 3) 

            # E = p Fskew_geijk Fskew_geijk w_ge
            Er = self.penalfactor * torch.einsum('geIij,geIij,ge->', Fskew, Fskew, self.gaussian_weight)


            EmdUgrad2 = 4 * self.penalfactor * (Ugrad2 - Ugrad2.transpose(2, 3))

            EmdUe = torch.einsum('geIij,geija->aIe', EmdUgrad2,
                                    self._dN2W)
            
            if if_onlyforce:
                return EmdUe + result0

            return EmdUe + result0[0], self._EmdUe_2 + result0[1]


    class SIMPElementC3D10(torchfea.elements.C3D10, SIMPElementFsrew):
        pass

    def set_materials(self, fe):

        # Set the SIMP materials for the solid elements
        elements = fe.assembly.get_part('final_model').elems['C3D4']

        elements_new = self.SIMPElementC3D10(elems_index=elements._elems_index, elems=elements._elems, penalfactor=self.penalfactor)
        fe.assembly.get_part('final_model').elems['C3D4'] = elements_new

        # Set the SIMP materials for the shell elements
        elements = fe.assembly.get_part('final_model').elems['C3D6']

        mu = self.shell_mu
        kappa = self.shell_kappa

        materials = torchfea.materials.NeoHookean(mu=mu, kappa=kappa)
        elements.set_materials(materials)
        elements.density = self.shell_density


        super().set_materials(fe)
