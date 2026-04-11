
from torchfea import Assembly

import torch
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
        
    def create_feamodel(self, path_result: str, pools=None) -> None:
        """
        Create the finite element model for sensitivity analysis.

        Args:
            assembly (Assembly): The assembly to create the finite element model for.
        """
        inp = self.geometry.generate(path_result=path_result, pools=pools)
        fe = self.feamodel.create_fea(inp=inp)
        self.materials.set_materials(fe)
        fe.initialize()
        
        return fe
    
    def obtain_design_sensitivity_vars(self, assembly: Assembly):
        """
        Obtain the design sensitivity variables for the optimization problem.

        Args:
            assembly (Assembly): The assembly to obtain design sensitivity variables for.
            
        Returns:
            dict[str, torch.Tensor]: A dictionary of design sensitivity variables for each parameter class.
        """
        # Initialize an empty tensor to store the design sensitivity variables
        design_sensitivity_vars = torch.zeros(0)

        # Obtain design sensitivity variables from each parameter class
        design_sensitivity_vars = {
            'geometry': self.geometry.obtain_design_sensitivity_vars(assembly),
            'feamodel': self.feamodel.obtain_design_sensitivity_vars(assembly),
            'materials': self.materials.obtain_design_sensitivity_vars(assembly)
        }


        return design_sensitivity_vars

    def modify_assembly(self, design_sensitivity_vars: dict[str, torch.Tensor], assembly: Assembly) -> None:
        """
        Modify the assembly for sensitivity analysis.

        Args:
            design_sensitivity_vars (dict[str, torch.Tensor]): The design sensitivity variables.
            assembly (Assembly): The assembly to modify.
        """
        self.geometry.modify_assembly(design_sensitivity_vars['geometry'], assembly)
        self.feamodel.modify_assembly(design_sensitivity_vars['feamodel'], assembly)
        self.materials.modify_assembly(design_sensitivity_vars['materials'], assembly)

    def save(self, foldpath: str, iteration: int) -> None:
        """
        Save the parameters to a file.
        
        Args:
            foldpath (str): The path to save the parameters.
        """
        self.geometry.save(foldpath=foldpath, iteration=iteration)
        self.feamodel.save(foldpath=foldpath, iteration=iteration)
        self.materials.save(foldpath=foldpath, iteration=iteration)

    def load(self, foldpath: str, iteration: int) -> None:
        """
        Load the parameters from a file.
        
        Args:
            foldpath (str): The path to load the parameters from.
        """
        self.geometry.load(foldpath=foldpath, iteration=iteration)
        # self.feamodel.load(foldpath=foldpath, iteration=iteration)
        self.materials.load(foldpath=foldpath, iteration=iteration)

    def export_data(self, filepath: str):
        """
        Export the data of parameters to file(s).
        
        Args:
            filepath (str): The path to export the data.
        """
        self.geometry._export_data(filepath=filepath)
        self.feamodel._export_data(foldpath=filepath)
        self.materials._export_data(foldpath=filepath)

    def pathlog_required(self) -> list[str]:
        """
        Allocate the path for saving data.
        
        Args:
            foldpath (str): The path to allocate.
        """
        paths = []
        paths += self.geometry.pathlog_required()
        paths += self.feamodel.pathlog_required()
        paths += self.materials.pathlog_required()
        return paths