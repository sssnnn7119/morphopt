from platform import node

from .baseparam import BaseParams
import torchfea

import torch

class BaseGeometry(BaseParams):
    """
    Base class for geometry parameter classes.

    Subclasses must provide the mesh/geometry generation and assembly modification
    behavior used by the optimization pipeline.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)

    def generate(self, path_result: str, pools=None) -> torchfea.Assembly:
        """Generate the FEA part for the current geometry."""
        raise NotImplementedError
    


class FixedGeometry(BaseGeometry):
    """
    Class to handle the geometry of the morphable model when using a fixed mesh.

    This geometry is read from a fixed Abaqus .inp file and does not change
    during optimization iterations.
    """
    def __init__(self):
        super().__init__()
        self.assembly: torchfea.Assembly = None
        """
        The FEA assembly containing the geometry for the optimization problem. This assembly is generated from a fixed mesh and does not change during optimization iterations.
        """

    def define_assembly(self)-> torchfea.Assembly:
        """
        Define the assembly for the geometry using node and element data.

        This method should be implemented in subclasses to create the assembly based on specific node and element data.

        Returns:
            torchfea.Assembly: The defined assembly for the geometry.
        """
        raise NotImplementedError
    
    def initialize(self, *args, **kwargs):
        super().initialize(*args, **kwargs)
        self.assembly = self.define_assembly()

    def generate(self, *args, **kwargs):
        """Load the fixed mesh from the Abaqus INP and return a torchfea.Assembly."""

        return self.assembly

class FixedGeometryINP(FixedGeometry):
    """
    Geometry parameters class for fixed mesh geometry using an Abaqus .inp file.
    """
    def __init__(self, mesh_file: str, part_name: str = 'final_model'):
        super().__init__()
        self._mesh_file = mesh_file
        """
        The file path of the mesh to be loaded for the geometry.
        """

        self._part_name = part_name
        """The name of the part in the Abaqus INP file to be used for the geometry."""

    def define_assembly(self):
        inp = torchfea.FEA_INP()
        inp.read_inp(self._mesh_file)

        fe_ext = torchfea.from_inp(inp)
        
        assembly = torchfea.Assembly()

        assembly.add_part(part=fe_ext.assembly.get_part(self._part_name), name='final_model')
        assembly.add_instance(instance=torchfea.Instance(part_name='final_model', external_surface='surface_0_All'), name='final_model')
        self.assembly = assembly
