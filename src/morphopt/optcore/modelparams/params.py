
import math
import tempfile

from torchfea import Assembly

import torch
from ..baseobject import BaseObject
from .feaparams import FEAParams
from .geometry import BaseGeometry
from .materials import BaseMaterials


import pyvista as pv




class Params(BaseObject):
    """
    Class to handle the parameters of the model.
    """
    def __init__(self, surfaces: BaseGeometry, feamodel: FEAParams, materials: BaseMaterials) -> None:
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
        return paths + ['params']

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
        
    def create_feamodel(self, path_result: str=None, pools=None):
        """
        Create the finite element model for sensitivity analysis.

        Args:
            path_result (str, optional): The path to the result folder. If None, a temporary directory will be used. Defaults to None.
            pools (list[torch.multiprocessing.Pool], optional): A list of multiprocessing pools for parallel processing. Defaults to None.
        Returns:
            feamodel: The created finite element model.
        """

        if path_result is None:
            with tempfile.TemporaryDirectory(prefix='morphopt_') as tempdir:
                part = self.geometry.generate(path_result=tempdir, pools=pools)
        else:
            part = self.geometry.generate(path_result=path_result, pools=pools)

        fe = self.feamodel.create_fea(part=part)
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

    
        import pyvista as pv
        plotter = pv.Plotter(off_screen=True, window_size=(1200, 1200))
        plotter.set_background('white')

        self.plot(plotter=plotter)

        plotter.enable_parallel_projection()
        azimuth = 210
        elevation = 20
        plotter.view_vector((math.cos(math.radians(azimuth)) * math.cos(math.radians(elevation)),
            math.sin(math.radians(azimuth)) * math.cos(math.radians(elevation)),
            math.sin(math.radians(elevation))))
        
        plotter.screenshot(foldpath + self.pathlog_required()[-1] + '/%d.jpg'%iteration)
        plotter.close()



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
    
    def plot(self, plotter: pv.Plotter = None, meshes: list[pv.DataSet] = None) -> pv.Plotter:
        """
        Plot the geometry and other relevant information using PyVista.

        Args:
            plotter (pv.Plotter, optional): An optional PyVista Plotter object to use for plotting. If None, a new Plotter will be created. Defaults to None.

        Returns:
            pv.Plotter: The PyVista Plotter object used for plotting.
        """

        if plotter is None:
            plotter = pv.Plotter()
    
        self.geometry.plot(plotter=plotter, meshes=meshes)
        self.materials.plot(plotter=plotter, meshes=meshes)
        self.feamodel.plot(plotter=plotter, meshes=meshes)

        return plotter
    
    def get_meshes(self):
        """Get the meshes associated with the geometry."""
        return self.geometry.get_meshes() + self.feamodel.get_meshes() + self.materials.get_meshes()