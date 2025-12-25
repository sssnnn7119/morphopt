import os
import sys

import MorphOpt


os.environ['KMP_DUPLICATE_LIB_OK']='True'
sys.path.append(os.getcwd())
import FEA
import numpy as np
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import torch
from MorphOpt import *

class ThisController(MorphOpt.Controller):
    def __init__(self):
        super().__init__(path_result_folder='Z:/Results', 
                         opt_label='GRASP')

    class ObjectiveFunction(MorphOpt.ObjectiveFunction):
        def get_objective(self):
            MorphOpt.controller.params.feamodel.process_fea(self.fe, step_index=0)
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
            E10 = torch.zeros([num_g1, num_p, 2, 3], device=Y1.device)
            E10[:, :, 0] = y1[:, contactobj._point_pairs[0]]
            E10[:, :, 1] = n1[:, contactobj._point_pairs[0]]

            E20 = torch.zeros([num_g2, num_p, 2, 3], device=Y2.device)
            E20[:, :, 0] = y2[:, contactobj._point_pairs[1]]
            E20[:, :, 1] = n2[:, contactobj._point_pairs[1]]
            dy0 = E10[:, None, :, 0, :] - E20[None, :, :, 0, :]
            dn0 = E10[:, None, :, 1, :] - E20[None, :, :, 1, :]

            M0 = (E10[:, None, :, 1, :] * E20[None, :, :, 1, :]).sum(dim=-1)
            MM0 = (contactobj.penalty_start_g - M0) / (contactobj.penalty_start_g - contactobj.penalty_end_g)
            MM0 = MM0.clamp(0, 1)
            f0 = MM0**3 * (6*MM0**2 - 15*MM0 + 10)

            D0 = (dn0 * dy0).sum(dim=-1) / 2
            g0 = torch.exp(D0 * contactobj.penalty_factor_f) * contactobj.penalty_distance_f
            
            L0 = dy0.norm(dim=-1)
            T0 = (contactobj.penalty_threshold_h - L0) / (contactobj.penalty_ratio_h * contactobj.penalty_threshold_h)
            T0 = T0.clamp(0, 1)
            h0 = T0**3 * (6*T0**2 - 15*T0 + 10)

            Rf = R_now.sum(dim=0)

            loss0 = -self.U[0][-6] / 1000
            loss1 = Rf[0]
            loss2 = -(torch.exp(-(D0)**2) * weight * f0 * h0).sum() * 0e-4
            # loss2 = (D**2 * weight).sum()
            
            # E = ins_actuator.potential_energy(RGC = assembly._GC2RGC(self.U[0].to(assembly.device)))
            # loss1 = -E.sum()

            print('Objective values: ', loss0.item(), loss2.item(), loss1.item())
            print('Contact force:', Rf.tolist())
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
                # fig.scene.parallel_projection = True
                
                # extern_surf = fe.loads['pressure-1'].surface_element.cpu().numpy()
                ins1 = self.fe.assembly.get_instance('final_model')
                ins2 = self.fe.assembly.get_instance('cylinder')
                extern_surf = ins1.surfaces.get_elements('surface_0_All')[0]._elems.cpu().numpy()
                extern_surf2 = ins2.surfaces.get_elements('contact')[0]._elems.cpu().numpy()
                # extern_surf = fem.part['final_model'].surfaces['surface_1_All']

                from mayavi import mlab
                import vtk
                from mayavi import mlab
                coo=extern_surf

                # Get the deformed surface coordinates
                RGC_now = self.fe.assembly._GC2RGC(self.U[case].to(self.fe.assembly.device))
                U1 = RGC_now[ins1._RGC_index].cpu().numpy()
                U2 = RGC_now[ins2._RGC_index].cpu().numpy()
                undeformed_surface1 = ins1.nodes.cpu().numpy()
                undeformed_surface2 = ins2.nodes.cpu().numpy()
                deformed_surface1 = undeformed_surface1 + U1
                deformed_surface2 = undeformed_surface2 + U2

                r1=deformed_surface1.transpose()
                r2=deformed_surface2.transpose()

                Unorm1 = (U1**2).sum(axis=1)**0.5
                Unorm2 = (U2**2).sum(axis=1)**0.5

                # surface = mlab.pipeline.triangular_mesh_source(r[0], r[1], r[2], coo)
                # surface_vtk = surface.outputs[0]._vtk_obj
                # stlWriter = vtk.vtkSTLWriter()
                # stlWriter.SetFileName('test.stl')
                # stlWriter.SetInputConnection(surface_vtk.GetOutputPort())
                # stlWriter.Write()
                # mlab.close()

                # Plot the deformed surface
                mesh1=mlab.triangular_mesh(deformed_surface1[:, 0], deformed_surface1[:, 1], deformed_surface1[:, 2], extern_surf, scalars=Unorm1)
                mesh2=mlab.triangular_mesh(deformed_surface2[:, 0], deformed_surface2[:, 1], deformed_surface2[:, 2], extern_surf2[:, [0,1,2]], scalars=Unorm2)

                mesh1.actor.property.edge_visibility = True
                mesh1.actor.property.line_width = 1.0
                mesh1.actor.property.edge_color = (0, 0, 0)  # Black edges

                mesh2.actor.property.edge_visibility = True
                mesh2.actor.property.line_width = 1.0
                mesh2.actor.property.edge_color = (0, 0, 0)  # Black edges

                if extern_surf2.shape[1] > 3:
                    mesh3=mlab.triangular_mesh(deformed_surface2[:, 0], deformed_surface2[:, 1], deformed_surface2[:, 2], extern_surf2[:, [0,2,3]], scalars=Unorm2)
                    mesh3.actor.property.edge_visibility = True
                    mesh3.actor.property.line_width = 1.0
                    mesh3.actor.property.edge_color = (0, 0, 0)  # Black edges

                mlab.view(azimuth=100, elevation=90, distance=300, focalpoint=(0, 0, 60))
                mlab.savefig(f"{filepath}/task_{case}_iter_{iteration}.png")
                mlab.close(fig)


    class Params(MorphOpt.Params):
        class GeometryParams(MorphOpt.GeometryParams):

            def __init__(self):

                super().__init__(max_step_length=[0.2, 0.2, 0.2, 0.2], fea_seed_size=1.4, fea_mesh_order=1)

                self.add_surface(
                    self.BSP.initialize_cylinder(r0=8.,
                                                            length=120.,
                                                            seed_size=1.0,
                                                            symmetric=[1, [1]],
                                                            flip=False, maxR=0.1, maxC=1.5, maxFF=0.1, perturbation_L=10.))
                
                self.add_surface(
                self.BSP.initialize_cylinder(r0=4.,
                                                        length=114.,
                                                        seed_size=1.0,
                                                        symmetric=[1, [1]],
                                                        init_location=[0, 0, 3],
                                                        flip=True, maxR=0.1, maxC=1.5, maxFF=0.1, perturbation_L=10.))
            
                
                self._max_iter_before_regenerate = 0
                self.if_update = [True, True]
                
        class FEAParams(MorphOpt.FEAParams):
            def __init__(self):
                super().__init__()

            def define_interface(self):
                # Common BC / RP / Couple
                self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='surface_0_Bottom', index_dof=[0,1,2]))
                self.add_fea_interface(self.BoundaryConditionInterface(instance_name='cylinder', set_nodes_name='contact', index_dof=[0,1,2]))
                self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 0., 120.]), name='RP_head')
                self.add_fea_interface(self.CoupleInterface(rp_name='RP_head', instance_name='final_model', set_nodes_name='surface_0_Head'))

                # Define load interfaces once
                self.add_fea_interface(self.PressureInterface(instance_name='final_model', surface_name='surface_1_All'), name='P_s1')
                self.add_fea_interface(self.ContactInterface(
                    instance_name1='final_model', surface_name1='surface_0_All',
                    instance_name2='cylinder', surface_name2='contact',
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
                    inp_path="C:/Users/24391/Documents/MineData/Learning/Code/Projects/MorphOpt/Jobs/tmech2025contact/grasp/rec.inp",
                    part_name='rec',
                    instance_name='rec',
                    part_name_new='cylinder',
                    instance_name_new='cylinder',
                    translation=[10.0, 0.0, 0.0]
                )

                return fe
                
        class MaterialParams(MorphOpt.Materials):
            
            def __init__(self):
                super().__init__(mu=0.482, kappa=4.8, density=1.08e-9,)
        
        def __init__(self):
            super().__init__(surfaces=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialParams())

    class Solver(MorphOpt.MorphSolver):
        """
        Solver class for MorphOpt.
        This class is responsible for solving the finite element analysis (FEA) problem.
        """

        def __init__(self, params: MorphOpt.Params):
            super().__init__(params=params,
                            num_process=1)
            
        # init_FEA no longer needed; functionality moved into FEA interfaces
    

    class Updater(MorphOpt.Updaters):
        """
        Updater class for MorphOpt.
        This class is responsible for updating the design variables based on the results of the optimization process.
        """

        def __init__(self, params: MorphOpt.Params, *args, **kwargs):
            super().__init__(surfaces=self.UpdaterSurfaces(params=params),
                            loads=None, *args, **kwargs)

        class UpdaterSurfaces(MorphOpt.UpdaterGeometries):
            """
            Updater class for MorphOpt.
            This class is responsible for updating the design variables based on the results of the optimization process.
            """

            def __init__(self, params: MorphOpt.Params):

                super().__init__(
                    params=params,
                    max_step_iter=50, max_step_length=0.4)

                shape_derivative = self.objectivefuncs.ShapeDerivativeDisplacement()
                self.add_objective_function(shape_derivative)
                self.add_constraints(
                    self.objectivefuncs.Fairness(surfaces=params.geometry, sensitivity=shape_derivative))
                self.add_constraints(
                    self.objectivefuncs.Distance(min_distance=
                                                                [[1.0, 2.5],
                                                                [2.5, 2.0]]))
                self.add_constraints(
                    self.objectivefuncs.boundarys.Cylinder(radius=12., height=120., bottom=0.))
    
if __name__ == '__main__':
    MorphOpt.start_optimization(Controller=ThisController, device='cuda:0')
