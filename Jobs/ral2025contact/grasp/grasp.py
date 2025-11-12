import os
import sys

import FEA
import numpy as np
os.environ['KMP_DUPLICATE_LIB_OK']='True'
sys.path.append(os.getcwd())

import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import torch
from MorphOpt import *

class ObjectiveFunction(GLOBAL.ObjectiveFunction):
    def get_objective(self):
        GLOBAL.controller.params.feamodel.process_fea(self.fe, step_index=0)
        assembly = self.fe.assembly
        ins_cylinder = assembly.get_instance('cylinder')
        ins_actuator = assembly.get_instance('final_model')
        R = assembly._assemble_generalized_Matrix(GC=self.U[0].to(assembly.device))[0]
        R_now = R[assembly.RGC_list_indexStart[ins_cylinder._RGC_index]:assembly.RGC_list_indexStart[ins_cylinder._RGC_index+1]].reshape([-1, 3])

        RGC = assembly._GC2RGC(self.U[0].to(assembly.device))

        contactobj: FEA.loads.Contact = assembly._loads['Contact_ext']
        instance1 = ins_actuator
        instance2 = ins_cylinder
        contactobj._filter_point_pairs(contactobj.surface_element1, contactobj.surface_element2, 
                                 instance1.nodes + RGC[instance1._RGC_index], 
                                 instance2.nodes + RGC[instance2._RGC_index])
        
        weight = torch.einsum('gp, g, Gp, G->gGp', 
                              contactobj.surface_element1.det_Jacobian[:, contactobj._point_pairs[0]], 
                              contactobj.surface_element1.gaussian_weight,
                              contactobj.surface_element2.det_Jacobian[:, contactobj._point_pairs[1]],
                              contactobj.surface_element2.gaussian_weight)

        # U = U.clone().detach().requires_grad_(True)
        Y1 = instance1.nodes + RGC[instance1._RGC_index]
        Y2 = instance2.nodes + RGC[instance2._RGC_index]

        num_g1 = contactobj.surface_element1._num_gaussian
        num_g2 = contactobj.surface_element2._num_gaussian
        num_e1 = contactobj.surface_element1._elems.shape[0]
        num_e2 = contactobj.surface_element2._elems.shape[0]
        num_n1 = contactobj.surface_element1.num_nodes_per_elem
        num_n2 = contactobj.surface_element2.num_nodes_per_elem

        # Calculate positions and normals for both surfaces
        Ye1 = Y1[contactobj.surface_element1._elems]
        Ye2 = Y2[contactobj.surface_element2._elems]

        y1 = torch.einsum('eai, ga->gei', Ye1, contactobj.surface_element1.shape_function_gaussian[0])
        y2 = torch.einsum('eai, ga->gei', Ye2, contactobj.surface_element2.shape_function_gaussian[0])

        NR1 = torch.einsum('gma, eai->gemi', contactobj.surface_element1.shape_function_gaussian[1], Ye1)
        NR2 = torch.einsum('gma, eai->gemi', contactobj.surface_element2.shape_function_gaussian[1], Ye2)
        
        N1 = torch.cross(NR1[:, :, 0, :], NR1[:, :, 1, :], dim=-1)
        N2 = torch.cross(NR2[:, :, 0, :], NR2[:, :, 1, :], dim=-1)

        nnorm1 = N1.norm(dim=-1)
        nnorm2 = N2.norm(dim=-1)
        n1 = N1 / nnorm1[:, :, None]
        n2 = N2 / nnorm2[:, :, None]

        num_p = contactobj._point_pairs.shape[1]
        
        # Create extended tensor for two surfaces
        E1 = torch.zeros([num_g1, num_p, 2, 3], device=Y1.device)
        E1[:, :, 0] = y1[:, contactobj._point_pairs[0]]
        E1[:, :, 1] = n1[:, contactobj._point_pairs[0]]

        E2 = torch.zeros([num_g2, num_p, 2, 3], device=Y2.device)
        E2[:, :, 0] = y2[:, contactobj._point_pairs[1]]
        E2[:, :, 1] = n2[:, contactobj._point_pairs[1]]

        dy = E1[:, None, :, 0, :] - E2[None, :, :, 0, :]
        dn = E1[:, None, :, 1, :] - E2[None, :, :, 1, :]

        M = (E1[:, None, :, 1, :] * E2[None, :, :, 1, :]).sum(dim=-1)
        MM = (contactobj._penalty_start_f - M) / (contactobj._penalty_start_f - contactobj._penalty_end_f)
        MM = MM.clamp(0, 1)
        f = MM**3 * (6*MM**2 - 15*MM + 10)

        D = -(dn * dy).sum(dim=-1) / 2

        Rf = R_now.sum(dim=0)

        loss0 = -self.U[0][-2] * 1e-4
        loss1 = Rf[0]
        loss2 = -(torch.exp(-(D+0.05)**2) * weight).sum() * 1e-4
        # loss2 = (D**2 * weight).sum()
        
        # E = ins_actuator.potential_energy(RGC = assembly._GC2RGC(self.U[0].to(assembly.device)))
        # loss1 = -E.sum()

        print('Objective values: ', loss0.item(), loss2.item(), loss1.item())
        return loss0 + loss2 + loss1
 
    
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

        for case in range(self.num_tasks):
            deformed_nodes = (ins.nodes + self.fe.assembly._GC2RGC(self.U[case].to(ins.nodes.device))[ins._RGC_index]).detach().cpu().numpy()

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

            mlab.view(azimuth=90, elevation=90, distance=300)
            mlab.savefig(f"{filepath}/task_{case}_iter_{iteration}.png")
            mlab.close(fig)

GLOBAL.obj_fun = ObjectiveFunction()

class Params(_Params):
    class SurfaceParams(_GeometryParams):

        def __init__(self):

            super().__init__(max_step_length=[0.2, 0.2, 0.2, 0.2], fea_seed_size=1.5, fea_mesh_order=1)

            self.add_surface(
                self.BSP.initialize_cylinder(r0=8.,
                                                        length=80.,
                                                        seed_size=1.0,
                                                        symmetric=[1, [1]],
                                                        flip=False, maxR=0.1, maxC=1.5, maxFF=0.1, perturbation_L=12.))
            
            self.add_surface(
            self.BSP.initialize_cylinder(r0=4.,
                                                    length=74.,
                                                    seed_size=1.0,
                                                    symmetric=[1, [1]],
                                                    init_location=[0, 0, 3],
                                                    flip=True, maxR=0.1, maxC=1.5, maxFF=0.1, perturbation_L=12.))
        
            
            
            self.if_update = [True, True]
            
    class FEAParams(_FEAParams):
        def __init__(self):
            super().__init__()

        def define_interface(self):
            # Common BC / RP / Couple
            self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='surface_0_Bottom', index_dof=[0,1,2]))
            self.add_fea_interface(self.BoundaryConditionInterface(instance_name='cylinder', set_nodes_name='contact', index_dof=[0,1,2]))
            self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 0., 80.]), name='RP_head')
            self.add_fea_interface(self.CoupleInterface(rp_name='RP_head', instance_name='final_model', set_nodes_name='surface_0_Head'))

            # Define load interfaces once
            self.add_fea_interface(self.PressureInterface(instance_name='final_model', surface_name='surface_1_All'), name='P_s1')
            self.add_fea_interface(self.ContactInterface(
                instance_name1='final_model', surface_name1='surface_0_All',
                instance_name2='cylinder', surface_name2='contact',
                penalty_threshold_h=2.0
            ), name='Contact_ext')

        def define_steps(self):
            # One step amplitudes
            self.set_step_num(1)
            self.set_step_params(0, 'P_s1', [0.08])

        def create_fea(self, inp: FEA.FEA_INP) -> FEA.FEAController:

            # Use base implementation to build the deformable actuator instance and register interfaces
            fe = super().create_fea(inp)

            # Add cylinder
            self.add_instance_from_inp(
                fe,
                inp_path="C:/Users/24391/Documents/MineData/Learning/Code/Projects/MorphOpt/Jobs/ral2025contact/grasp/rec.inp",
                part_name='rec',
                instance_name='rec',
                part_name_new='cylinder',
                instance_name_new='cylinder',
                translation=[0.0, 0.0, 0.0]
            )

            return fe
            
    class MaterialParams(_Materials):
        
        def __init__(self):
            super().__init__(mu=0.482, kappa=4.8, density=1.08e-9,)
    
    def __init__(self):
        super().__init__(surfaces=self.SurfaceParams(), feamodel=self.FEAParams(), materials=self.MaterialParams())

class Solver(_MorphSolver):
    """
    Solver class for MorphOpt.
    This class is responsible for solving the finite element analysis (FEA) problem.
    """

    def __init__(self, params: Params):
        super().__init__(params=params,
                         num_process=1)
        
    # init_FEA no longer needed; functionality moved into FEA interfaces
 

class Updater(_Updaters):
    """
    Updater class for MorphOpt.
    This class is responsible for updating the design variables based on the results of the optimization process.
    """

    def __init__(self, params: Params, *args, **kwargs):
        super().__init__(surfaces=self.UpdaterSurfaces(params=params),
                         loads=None, *args, **kwargs)

    class UpdaterSurfaces(_UpdaterSurfaces):
        """
        Updater class for MorphOpt.
        This class is responsible for updating the design variables based on the results of the optimization process.
        """

        def __init__(self, params: Params):

            super().__init__(
                params=params,
                max_step_iter=50)

            shape_derivative = self.objectivefuncs.ShapeDerivativeDirect()
            self.add_objective_function(shape_derivative)
            self.add_objective_function(
                self.objectivefuncs.Fairness(surfaces=params.geometry, sensitivity=shape_derivative))
            self.add_objective_function(
                self.objectivefuncs.Distance(min_distance=
                                                            [[2.5, 2.5],
                                                             [2.5, 2.5]]))
            self.add_objective_function(
                self.objectivefuncs.boundarys.Cylinder(radius=10., height=80., bottom=0.))
    
class Controller(_Controller):
    def save(self):
        super().save()
        import shutil
        try:
            shutil.copyfile(GLOBAL.PATH.path_Result + '/Cache/TopOptRun.inp',
                            GLOBAL.PATH.path_Result + '/Log/Deformation/Data/TopOptRun_%d.inp' % (GLOBAL.History.iteration-1))
        except:
            pass
    
if __name__ == '__main__':
    torch.set_default_dtype(torch.float64)
    torch.set_default_device('cpu')

    path_result = 'Z:/Results'
    opt_label = 'GRASP'

    # region Initialize the workflow
    initializer.initialize_path(result_path=path_result, opt_label=opt_label)
    initializer.initialize_history()

    params = Params()

    solver = Solver(params=params)

    updater = Updater(params=params)

    controller = Controller(params=params, solver=solver, updater=updater)
    controller.opt_loop()
