
from .feamodel.feaparams import FEAParams
from .surfaces.surfaceparams import SurfacesParams
from .materials.materialparams import Materials
class Params:
    """
    Class to handle the parameters of the model.
    """
    def __init__(self, surfaces: SurfacesParams, loads: FEAParams, materials: Materials) -> None:
        """
        Initialize the Params class.
        """
        self.surfaces = surfaces
        """
        Surfaces: An instance of the Surfaces class from the ModelParams module.
        """
        self.loads = loads
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
        self.surfaces.initialize(iteration=iteration)
        self.loads.initialize(iteration=iteration)
        self.materials.initialize(iteration=iteration)

    def save(self, filepath: str) -> None:
        """
        Save the parameters to a file.
        
        Args:
            filepath (str): The path to save the parameters.
        """
        self.surfaces.save(filepath=filepath + '/Surfaces/Data/')
        self.loads.save(filepath=filepath + '/Loads/Data/')
        self.materials.save(filepath=filepath + '/Materials/Data/')

    def load(self, filepath: str, iteration: int) -> None:
        """
        Load the parameters from a file.
        
        Args:
            filepath (str): The path to load the parameters from.
        """
        self.surfaces.load(filepath=filepath + '/Surfaces/Data/', iteration=iteration)
        self.loads.load(filepath=filepath + '/Loads/Data/', iteration=iteration)
        self.materials.load(filepath=filepath + '/Materials/Data/', iteration=iteration)

    def save_figure(self, filepath: str) -> None:
        """
        Save the figures of the parameters to a file.
        
        Args:
            filepath (str): The path to save the figures.
        """
        self.surfaces.save_figure(filepath=filepath + '/Surfaces/Figures/')
        self.loads.save_figure(filepath=filepath + '/Loads/Figures/')
        self.materials.save_figure(filepath=filepath + '/Materials/Figures/')

    def export_data(self, filepath: str):
        """
        Export the data of parameters to file(s).
        
        Args:
            filepath (str): The path to export the data.
        """
        self.surfaces.export_data(filepath=filepath)
        self.loads.export_data(filepath=filepath)
        self.materials.export_data(filepath=filepath)