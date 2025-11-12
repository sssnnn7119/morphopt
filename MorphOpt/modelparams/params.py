
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

    def initialize(self, iteration: int) -> None:
        """
        Initialize the parameters.
        """
        self.geometry.initialize(iteration=iteration)
        self.feamodel.initialize(iteration=iteration)
        self.materials.initialize(iteration=iteration)

    def save(self, filepath: str) -> None:
        """
        Save the parameters to a file.
        
        Args:
            filepath (str): The path to save the parameters.
        """
        self.geometry.save(filepath=filepath + '/Surfaces/Data/')
        self.feamodel.save(filepath=filepath + '/Loads/Data/')
        self.materials.save(filepath=filepath + '/Materials/Data/')

    def load(self, filepath: str, iteration: int) -> None:
        """
        Load the parameters from a file.
        
        Args:
            filepath (str): The path to load the parameters from.
        """
        self.geometry.load(filepath=filepath + '/Surfaces/Data/', iteration=iteration)
        self.feamodel.load(filepath=filepath + '/Loads/Data/', iteration=iteration)
        self.materials.load(filepath=filepath + '/Materials/Data/', iteration=iteration)

    def save_figure(self, filepath: str) -> None:
        """
        Save the figures of the parameters to a file.
        
        Args:
            filepath (str): The path to save the figures.
        """
        self.geometry.save_figure(filepath=filepath + '/Surfaces/Figures/')
        self.feamodel.save_figure(filepath=filepath + '/Loads/Figures/')
        self.materials.save_figure(filepath=filepath + '/Materials/Figures/')

    def export_data(self, filepath: str):
        """
        Export the data of parameters to file(s).
        
        Args:
            filepath (str): The path to export the data.
        """
        self.geometry._export_data(filepath=filepath)
        self.feamodel._export_data(filepath=filepath)
        self.materials._export_data(filepath=filepath)
