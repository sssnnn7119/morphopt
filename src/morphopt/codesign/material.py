import math
from typing import Optional

import torch
import numpy as np

import torchfea
from .. import SIMP_BSPFieldMaterials
import bspmap


class CodesignMaterials(SIMP_BSPFieldMaterials):
    """
    Class to handle the materials of the model for codesign optimization.
    """

    def __init__(self, mumax, kappamax, simp_ratio_min, bounding_box, simp_field_resolution, degree, density, initial_ratio,
                 shell_mu: float, 
                 shell_kappa: float, 
                 shell_density: float,
                 elementname: str = "C3D4",
                 shell_elementname: str = "C3D6",
                 voidpenalfactor: float = 1e-2,
                 materialpenalty: int = 8,):
        
        super().__init__(mumax, kappamax, simp_ratio_min, bounding_box, simp_field_resolution, degree, density, initial_ratio, voidpenalfactor, materialpenalty, elementname)

        self.shell_mu = shell_mu
        """ The shear modulus of the shell material. """

        self.shell_kappa = shell_kappa
        """ The bulk modulus of the shell material. """

        self.shell_density = shell_density
        """ The density of the shell material. """

        self.shell_elementname = shell_elementname
        """ The name of the shell element type. """


    def set_materials(self, fe):

        # Set the SIMP materials for the shell elements
        elements = fe.assembly.get_part('final_model').elems[self.shell_elementname]

        mu = self.shell_mu
        kappa = self.shell_kappa

        materials = torchfea.materials.NeoHookean(mu=mu, kappa=kappa)
        elements.set_materials(materials)
        elements.density = self.shell_density

        super().set_materials(fe)
