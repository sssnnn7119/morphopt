from .basegeometry import BaseGeometry
import torchfea

import torch

class FixedMeshGeometry(BaseGeometry):
    """
    Class to handle the geometry of the morphable model when using a fixed mesh.

    This geometry is read from a fixed Abaqus .inp file and does not change
    during optimization iterations.
    """
    def __init__(self):
        super().__init__()
        self.part = None
        """
        The file path of the mesh to be loaded for the geometry.
        """
    def generate(self, *args, **kwargs):
        """Load the fixed mesh from the Abaqus INP and return a torchfea.Part."""
        return self.part

class FixedGeometryINP(FixedMeshGeometry):
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

    def initialize(self, *args, **kwargs):
        super().initialize(*args, **kwargs)

        inp = torchfea.FEA_INP()
        inp.read_inp(self._mesh_file)

        fe_ext = torchfea.from_inp(inp)
        self.part = fe_ext.assembly.get_part(self._part_name)

class FixedGeometryNodeElement(FixedMeshGeometry):
    """
    Geometry parameters class for fixed mesh geometry using node and element data.
    """
    def __init__(self, nodes: torch.Tensor, elements: torch.Tensor, element_name: str = None):
        super().__init__()
        self.nodes = nodes
        self.elements = elements
        self.element_name = element_name


    def initialize(self, *args, **kwargs):
        super().initialize(*args, **kwargs)

        part = torchfea.Part(nodes=self.nodes)

        node_per_elem = self.elements.shape[1]
        elem_type = f'C3D{node_per_elem}'

        if self.element_name is None:
            self.element_name = elem_type

        elems = torchfea.elements.initialize_element(element_type=elem_type, elems_index=torch.arange(self.elements.shape[0]), elems=self.elements)

        part.add_element(elems, name=self.element_name)