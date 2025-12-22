
import MorphOpt
from ..baseobject import BaseObject
from .feamodel.feaparams import FEAParams
from .geometry.geometryparams import GeometryParams
from .materials.materialparams import Materials
class Params(BaseObject):
    """
    Class to handle the parameters of the model.
    """
    def __init__(self, surfaces: GeometryParams, feamodel: FEAParams, materials: Materials) -> None:
        """
        Initialize the Params class.
        """
        self.geometry = surfaces
        """
        Surfaces: An instance of the Surfaces class from the ModelParams module.
        """
        self.feamodel = feamodel
        """
        Loads: An instance of the Loads class from the ModelParams module.
        """
        self.materials = materials
        """
        Materials: An instance of the Materials class from the ModelParams module.
        """

    def reinitialize(self, iteration: int) -> None:
        """
        reInitialize the parameters.
        """
        self.geometry.reinitialize(iteration=iteration)
        self.feamodel.reinitialize(iteration=iteration)
        self.materials.reinitialize(iteration=iteration)

    def initialize(self):
        """
        Initialize the parameters.
        """
        self.geometry.initialize()
        self.feamodel.initialize()
        self.materials.initialize()
        

    def save(self, foldpath: str, iteration: int) -> None:
        """
        Save the parameters to a file.
        
        Args:
            foldpath (str): The path to save the parameters.
        """
        self.geometry.save(foldpath=foldpath + '/surfaces/data/', iteration=iteration)
        self.feamodel.save(foldpath=foldpath + '/loads/data/', iteration=iteration)
        self.materials.save(foldpath=foldpath + '/materials/data/', iteration=iteration)

    def load(self, foldpath: str, iteration: int) -> None:
        """
        Load the parameters from a file.
        
        Args:
            foldpath (str): The path to load the parameters from.
        """
        self.geometry.load(foldpath=foldpath + '/surfaces/data/', iteration=iteration)
        # self.feamodel.load(foldpath=foldpath + '/loads/data/', iteration=iteration)
        # self.materials.load(foldpath=foldpath + '/materials/data/', iteration=iteration)
        
    def save_figure(self, foldpath: str, iteration: int) -> None:
        """
        Save the figures of the parameters to a file.
        
        Args:
            foldpath (str): The path to save the figures.
        """
        self.geometry.save_figure(foldpath=foldpath + '/surfaces/figures/', iteration=iteration)
        self.feamodel.save_figure(foldpath=foldpath + '/loads/figures/', iteration=iteration)
        self.materials.save_figure(foldpath=foldpath + '/materials/figures/', iteration=iteration)
    def export_data(self, filepath: str):
        """
        Export the data of parameters to file(s).
        
        Args:
            filepath (str): The path to export the data.
        """
        self.geometry._export_data(filepath=filepath)
        self.feamodel._export_data(foldpath=filepath)
        self.materials._export_data(foldpath=filepath)
