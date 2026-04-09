import os
import sys

import FEA
import numpy as np
os.environ['KMP_DUPLICATE_LIB_OK']='True'
sys.path.append(os.getcwd())

import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import torchfea
import torch
import morphopt

class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder='Z:/Results', 
                         opt_label='LOCOMOTION')

    class ObjectiveFunction(morphopt.ObjectiveFunction):

        def __init__(self):
            super().__init__()
            self.target_displacement = torch.tensor([10.0, 0.0, 120.0])

        def objective_function(self):
            assembly = self.fe.assembly
            GC = self.fe_results[0].GC
            end_surf = np.array(list(assembly.get_instance('final_model').sets_nodes['surface_0_Head']))
            RGC = assembly._GC2RGC(GC)
            ins_ind = assembly.get_instance('final_model')._RGC_index
            end_pos = RGC[ins_ind][end_surf].mean(dim=0) + torch.tensor([0.0, 0.0, 80.0], device=RGC[0].device)
            loss0 = (end_pos - self.target_displacement.to(end_pos.device))**2
            return loss0.sum()
            
        def get_metrics(self):
            return []
    
        
        def save_figure(self, filepath: str, iteration: int, insname: str = 'final_model', surface: str = 'surface_0_All') -> None:
            """
            Save the figures of the FEA results.

            Parameters:
                filepath (str): The path to save the figures.
                iteration (int): The current iteration number.
            """
            ins = self.fe.assembly.get_instance(insname)
            surfaces = [surface]
            surface_elements: list[FEA.elements.BaseSurface] = []
            for i in range(len(surfaces)):
                surface_elements = surface_elements + ins.surfaces.get_elements(surfaces[i])
            
            surface_connections = [surface_elements[i].surf_elems_circ.cpu().numpy() for i in range(len(surface_elements))]


            deformed_nodes = (ins.nodes + self.fe.assembly._GC2RGC(self.fe_results[0].GC.to(ins.nodes.device))[ins._RGC_index]).detach().cpu().numpy()

            from mayavi import mlab
            from matplotlib.tri import Triangulation
            from tvtk.api import tvtk
            from tvtk.common import configure_input_data

            fig = mlab.figure(size=(800, 800), bgcolor=(1, 1, 1))
            fig.scene.parallel_projection = True
            
            # Draw all surface connections using TVTK

            # Create a dataset with points and cells
            points = tvtk.Points()
            points.from_array(deformed_nodes)

            polys = tvtk.CellArray()
            mesh = tvtk.PolyData()
            mesh.points = points

            # Add all surface connections as polygons - optimized version
            # Pre-calculate the total number of cells and points for pre-allocation
            total_cells = sum(len(connection) for connection in surface_connections)
            polys.allocate(total_cells)

            # Process all faces more efficiently
            for connection in surface_connections:
                for face in connection:
                    # Skip if any node is -1 (placeholder)
                    if -1 in face:
                        continue
                    
                    # More efficient cell insertion
                    n_points = len(face)
                    # Convert face to a list/array compatible with VTK
                    polys.insert_next_cell(n_points)
                    for point_idx in face:
                        polys.insert_cell_point(point_idx)

            mesh.polys = polys

            # Create a mapper and actor
            mapper = tvtk.PolyDataMapper()
            configure_input_data(mapper, mesh)
            actor = tvtk.Actor(mapper=mapper)
            actor.property.color = (40.0/255, 120.0/255, 181.0/255)
            actor.property.opacity = 1.0

            # Add the actor to the scene
            fig.scene.add_actor(actor)

            ins2 = self.fe.assembly.get_instance('block')
            U2 = self.fe.assembly.RGC[ins2._RGC_index].cpu().numpy()
            extern_surf2 = ins2.surfaces.get_elements('contact')[0]._elems.cpu().numpy()
            undeformed_surface2 = ins2.nodes.cpu().numpy()
            deformed_surface2 = undeformed_surface2 + U2
            r2=deformed_surface2.transpose()
            Unorm2 = (U2**2).sum(axis=1)**0.5
            mesh2=mlab.triangular_mesh(deformed_surface2[:, 0], deformed_surface2[:, 1], deformed_surface2[:, 2], extern_surf2[:, [0,1,2]], scalars=Unorm2)
            mesh2.actor.property.edge_visibility = True
            mesh2.actor.property.line_width = 1.0
            mesh2.actor.property.edge_color = (0, 0, 0)  # Black edges
            if extern_surf2.shape[1] > 3:
                mesh3=mlab.triangular_mesh(deformed_surface2[:, 0], deformed_surface2[:, 1], deformed_surface2[:, 2], extern_surf2[:, [0,2,3]], scalars=Unorm2)
                mesh3.actor.property.edge_visibility = True
                mesh3.actor.property.line_width = 1.0
                mesh3.actor.property.edge_color = (0, 0, 0)  # Black edges

            mlab.points3d(self.target_displacement[0].item(), self.target_displacement[1].item(), self.target_displacement[2].item(), color=(1, 0, 0), scale_factor=2)

            mlab.view(azimuth=210, elevation=70, distance=300)
            mlab.savefig(f"{filepath}/task_{0}_iter_{iteration}.png")
            mlab.close(fig)


    class Params(morphopt.Params):
        class GeometryParams(morphopt.GeometryParams):

            def __init__(self):

                super().__init__(max_step_length=[0.2, 0.2, 0.2, 0.2], fea_seed_size=1.2, fea_mesh_order=1)

                self.add_surface(
                    self.BSP.initialize_cylinder(r0=8.,
                                                            length=80.,
                                                            seed_size=1.0,
                                                            flip=False, maxR=0.1, maxC=2.0, maxFF=0.2, perturbation_L=12.))
                
                self.add_surface(
                self.BSP.initialize_cylinder(r0=4.,
                                                        length=74.,
                                                        seed_size=1.0,
                                                        init_location=[0, 0, 3],
                                                        flip=True, maxR=0.1, maxC=2.0, maxFF=0.2, perturbation_L=12.))
            
                
                
                self.if_update = [True, True]
                
        class FEAParams(morphopt.FEAParams):
            def define_interface(self):
                # Common BC / RP / Couple
                self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='surface_0_Bottom', index_dof=[0,1,2]))
                self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 0., 80.]), name='RP_head')
                self.add_fea_interface(self.CoupleInterface(rp_name='RP_head', instance_name='final_model', set_nodes_name='surface_0_Head'))

                # Define interfaces
                self.add_fea_interface(
                    self.PressureInterface(instance_name='final_model', surface_name='surface_1_All'),
                    name='P_s1'
                )
                self.add_fea_interface(
                    self.ContactInterface(
                        instance_name1='final_model', surface_name1='surface_0_All',
                        instance_name2='block', surface_name2='contact',
                        penalty_threshold_h=3.0
                    ),
                    name='Contact_ext'
                )

            def define_steps(self):
                # Single step amplitudes
                self.set_step_num(1)
                self.set_step_params(0, 'P_s1', [0.08])

            def create_fea(self, inp: FEA.FEA_INP) -> FEA.FEAController:

                # Use base implementation to build the deformable actuator instance and register interfaces
                fe = super().create_fea(inp)

                # Add external rigid/block instance before solving (same style as grasp.py)
                self.add_instance_from_inp(
                    fe,
                    inp_path="C:/Users/24391/Documents/MineData/Learning/Code/Projects/morphopt/Jobs/ral2025contact/locomotion/rec.inp",
                    part_name='block',
                    instance_name='block',
                    translation=[0.0, 0.0, 0.0]
                )

                return fe
                
        class MaterialParams(morphopt.Materials):
            
            def __init__(self):
                super().__init__(mu=0.482, kappa=4.8, density=1.08e-9,)
        
        def __init__(self):
            super().__init__(surfaces=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialParams())


    class Solver(morphopt.MorphSolver):
        """
        Solver class for morphopt.
        This class is responsible for solving the finite element analysis (FEA) problem.
        """

        def __init__(self, params: morphopt.Params):
            super().__init__(params=params,
                            num_process=1)

        # init_FEA no longer needed; functionality moved into FEA interfaces
    

    class Updater(morphopt.Updaters):
        """
        Updater class for morphopt.
        This class is responsible for updating the design variables based on the results of the optimization process.
        """

        def __init__(self, params: morphopt.Params, *args, **kwargs):
            super().__init__(surfaces=self.UpdaterSurfaces(params=params),
                            loads=None, *args, **kwargs)

        class UpdaterSurfaces(morphopt.UpdaterGeometries):
            """
            Updater class for morphopt.
            This class is responsible for updating the design variables based on the results of the optimization process.
            """

            def __init__(self, params: morphopt.Params):

                super().__init__(
                    params=params,
                    max_step_iter=50)

                shape_derivative = self.objectivefuncs.ShapeDerivativeDisplacement()
                self.add_objective_function(shape_derivative)
                self.add_constraints(
                    self.objectivefuncs.Fairness(surfaces=params.geometry, sensitivity=shape_derivative))
                self.add_constraints(
                    self.objectivefuncs.Distance(min_distance=
                                                                [[2.5, 2.5],
                                                                [2.5, 2.5]]))
                self.add_constraints(
                    self.objectivefuncs.boundarys.Cylinder(radius=15., height=80., bottom=0.))
    
if __name__ == '__main__':
    morphopt.start_optimization(Controller=ThisController, device='cuda:0')
