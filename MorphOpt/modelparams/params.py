
from .feamodel.feaparams import FEAParams
from .geometry.geometryparams import GeometryParams
from .materials.materialparams import Materials
class Params:
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
        

    def save(self, foldpath: str) -> None:
        """
        Save the parameters to a file.
        
        Args:
            foldpath (str): The path to save the parameters.
        """
        self.geometry.save(foldpath=foldpath + '/surfaces/data/')
        self.feamodel.save(foldpath=foldpath + '/loads/data/')
        self.materials.save(foldpath=foldpath + '/materials/data/')

    def load(self, filepath: str, iteration: int) -> None:
        """
        Load the parameters from a file.
        
        Args:
            filepath (str): The path to load the parameters from.
        """
        self.geometry.load(foldpath=filepath + '/Surfaces/Data/', iteration=iteration)
        # self.feamodel.load(filepath=filepath + '/Loads/Data/', iteration=iteration)
        # self.materials.load(filepath=filepath + '/Materials/Data/', iteration=iteration)

    def save_figure(self, filepath: str) -> None:
        """
        Save the figures of the parameters to a file.
        
        Args:
            filepath (str): The path to save the figures.
        """
        self.geometry.save_figure(filename=filepath + '/Surfaces/Figures/')
        self.feamodel.save_figure(filename=filepath + '/Loads/Figures/')
        self.materials.save_figure(filename=filepath + '/Materials/Figures/')

    def export_data(self, filepath: str):
        """
        Export the data of parameters to file(s).
        
        Args:
            filepath (str): The path to export the data.
        """
        self.geometry._export_data(filepath=filepath)
        self.feamodel._export_data(foldpath=filepath)
        self.materials._export_data(foldpath=filepath)
