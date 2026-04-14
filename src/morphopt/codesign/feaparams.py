import math

import torch
import numpy as np

import torchfea
from .. import FEAParams
import bspmap


class CodesignFEAParams(FEAParams):
    """
    Class to handle the materials of the model for codesign optimization.
    """

    def create_fea(self, inp):
        fe = super().create_fea(inp)
        fe_part = fe.assembly.get_part('final_model')
        element_c3d6 = fe_part.elems['C3D6']
        element_c3d6.initialize()

        if (element_c3d6.gaussian_weight.min() < 0):
            nodes = fe_part.nodes
            fe.initialize()
            element_c3d4 = fe_part.elems['C3D4']
            surfaceoffset = fe_part.surfaces.get_trimesh('surface_1_offset')
            surface1 = fe_part.surfaces.get_trimesh('surface_1_All')
            surfnodes = nodes[surfaceoffset]
            surfnormals = torch.cross(
                surfnodes[:, 1] - surfnodes[:, 0],
                surfnodes[:, 2] - surfnodes[:, 0],
                dim=1
            )
            surfcenter = surfnodes.mean(dim=1)

            fe.assembly.get_instance('final_model').external_surface = 'surface_1_offset'

            mesh_1all = fe.assembly.get_instance('final_model').get_mesh(surf_name='surface_1_All')
            mesh_1offset = fe.assembly.get_instance('final_model').get_mesh(surf_name='surface_1_offset')

            import morphopt
            normal_cpgeo = morphopt.controller.params.geometry.surface_list[1].get_normals(torch.from_numpy(morphopt.controller.params.geometry.surface_list[1].surf_node_uv).to(torch.get_default_device()))
            surf_nodes = nodes[morphopt.controller.params.geometry.surface_list[1].surf_node_idx]
            import pyvista as pv

            surf_nodes_np = surf_nodes.detach().cpu().numpy() if isinstance(surf_nodes, torch.Tensor) else np.asarray(surf_nodes)
            normals_np = normal_cpgeo.detach().cpu().numpy() if isinstance(normal_cpgeo, torch.Tensor) else np.asarray(normal_cpgeo)

            mesh = pv.PolyData(surf_nodes_np)
            mesh['Normals'] = normals_np

            scale = np.linalg.norm(np.ptp(surf_nodes_np, axis=0)) * 0.05
            glyphs = mesh.glyph(orient='Normals', scale=False, factor=scale)

            plotter = pv.Plotter()
            # plotter.add_mesh(mesh, color='lightgrey', point_size=5, render_points_as_spheres=True)
            # plotter.add_mesh(glyphs, color='red')
            plotter.add_mesh(mesh_1all, color='green', opacity=0.5)
            plotter.add_mesh(mesh_1offset, color='red', opacity=1.0)
            plotter.add_axes()
            plotter.show_grid()
            plotter.show()



            raise ValueError("The Gaussian weights of the C3D6 elements are negative. Please check the mesh quality.")
        
        return fe