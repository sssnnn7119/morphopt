
import torchfea
from ..base_params import BaseParams

class Materials(BaseParams):
    """
    Class to handle the materials of the morphable model.
    """

    def __init__(self, mu: float, kappa: float, density: float, elementname: str = "C3D4") -> None:
        """
        Initialize the Materials class.

        Args:
            mu (float): The shear modulus of the material.
            kappa (float): The bulk modulus of the material.
            elementname (str): The name of the element type.
        """
        super().__init__()
        self._mu: float
        self._kappa: float
        self._density: float

        self.mu = mu
        self.kappa = kappa
        self.density = density

        self.elementname = elementname
        """ The name of the element type. """

    @property
    def mu(self) -> float:
        """
        Get the shear modulus.

        Returns:
            float: The shear modulus.
        """
        return self._mu
    
    @mu.setter
    def mu(self, value: float) -> None:
        """
        Set the shear modulus.

        Args:
            value (float): The new shear modulus.
        """
        self._mu = float(value)

    @property
    def kappa(self) -> float:
        """
        Get the bulk modulus.

        Returns:
            float: The bulk modulus.
        """
        return self._kappa
    
    @kappa.setter
    def kappa(self, value: float) -> None:
        """
        Set the bulk modulus.

        Args:
            value (float): The new bulk modulus.
        """
        self._kappa = float(value)

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

    def set_materials(self, fe: torchfea.FEAController) -> None:
        """
        Set the materials of the FEA model.

        Args:
            fe (torchfea.FEAController): The FEA controller.
        """
        elements = fe.assembly.get_part('final_model').elems[self.elementname]
        mu = self.mu
        kappa = self.kappa
        materials = torchfea.materials.NeoHookeanLnJ(mu=mu, kappa=kappa)
        elements.set_materials(materials)
        elements.density = self.density