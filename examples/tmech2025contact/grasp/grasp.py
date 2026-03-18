import os
import sys

import morphopt


os.environ['KMP_DUPLICATE_LIB_OK']='True'
sys.path.append(os.getcwd())
import torchfea
import numpy as np
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import torch
from morphopt import *

class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder='Z:/Results', 
                         opt_label='GRASP')

    class ObjectiveFunction(morphopt.ObjectiveFunction):
        def get_objective(self):
            morphopt.controller.params.feamodel.process_fea(self.fe, step_index=0)
            assembly = self.fe.assembly
            ins_cylinder = assembly.get_instance('cylinder')
            ins_actuator = assembly.get_instance('final_model')
            R = assembly._assemble_generalized_Matrix(GC=self.U[0].to(assembly.device))[0]
            R_now = R[assembly.RGC_list_indexStart[ins_cylinder._RGC_index]:assembly.RGC_list_indexStart[ins_cylinder._RGC_index+1]].reshape([-1, 3])

            RGC = assembly._GC2RGC(self.U[0].to(assembly.device))

            contactobj: torchfea.loads.Contact = assembly._loads['Contact_ext']
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

            loss0 = -self.U[0][-2]
            loss1 = Rf[0]
            loss2 = -(torch.exp(-(D0)**2) * weight * f0 * h0).sum() * 1e-4
            # loss2 = (D**2 * weight).sum()
            
            # E = ins_actuator.potential_energy(RGC = assembly._GC2RGC(self.U[0].to(assembly.device)))
            # loss1 = -E.sum()

            print('Objective values: ', loss0.item(), loss2.item(), loss1.item())
            print('Contact force:', Rf.tolist())
            return loss0 + loss2
        
        def get_metrics(self):
            morphopt.controller.params.feamodel.process_fea(self.fe, step_index=0)
            assembly = self.fe.assembly
            ins_cylinder = assembly.get_instance('cylinder')
            ins_actuator = assembly.get_instance('final_model')
            R = assembly._assemble_generalized_Matrix(GC=self.U[0].to(assembly.device))[0]
            R_now = R[assembly.RGC_list_indexStart[ins_cylinder._RGC_index]:assembly.RGC_list_indexStart[ins_cylinder._RGC_index+1]].reshape([-1, 3])

            RGC = assembly._GC2RGC(self.U[0].to(assembly.device))

            contactobj: torchfea.loads.Contact = assembly._loads['Contact_ext']
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

            loss0 = -self.U[0][-2] / 1000
            loss1 = Rf[0]
            loss2 = -(torch.exp(-(D0)**2) * weight * f0 * h0).sum() * 1e-4

            return [self.U[0][-2].item(), loss2.item()]
    

    class Params(morphopt.Params):
        class GeometryParams(morphopt.GeometryParams):

            def __init__(self):

                super().__init__(max_step_length=[0.2, 0.2, 0.2, 0.2], fea_seed_size=1.0, fea_mesh_order=1)

                self.add_surface(
                    self.BSP.initialize_cylinder(r0=8.,
                                                            length=80.,
                                                            seed_size=1.0,
                                                            symmetric=[1, [1]],
                                                            flip=False, maxR=0.1, maxC=0.8, maxFF=0.1, perturbation_L=10.))
                
                self.add_surface(
                self.BSP.initialize_cylinder(r0=4.,
                                                        length=74.,
                                                        seed_size=1.0,
                                                        symmetric=[1, [1]],
                                                        init_location=[0, 0, 3],
                                                        flip=True, maxR=0.1, maxC=0.8, maxFF=0.1, perturbation_L=10.))
            
                
                self._max_iter_before_regenerate = 0
                self.if_update = [True, True]
            def apply_surface_constraints(self):
                # rotate the exterior surface
                size0 = self.surface_list[0].model.size
                cp0 = self.surface_list[0]._cps.reshape(size0[0], size0[1], 3)
                r0 = cp0.clone()
                cp0[:, :, 0] = (r0[:, :, 0] + r0.flip(dims=[1])[:, :, 0]) / 2
                cp0[:, :, 1] = (r0[:, :, 1] - r0.flip(dims=[1])[:, :, 1]) / 2
                cp0[:, :, 2] = (r0[:, :, 2] + r0.flip(dims=[1])[:, :, 2]) / 2
                self.surface_list[0]._cps = cp0.reshape([-1, 3])

                size0 = self.surface_list[1].model.size
                cp0 = self.surface_list[1]._cps.reshape(size0[0], size0[1], 3)
                r0 = cp0.clone()
                cp0[:, :, 0] = (r0[:, :, 0] + r0.flip(dims=[1])[:, :, 0]) / 2
                cp0[:, :, 1] = (r0[:, :, 1] - r0.flip(dims=[1])[:, :, 1]) / 2
                cp0[:, :, 2] = (r0[:, :, 2] + r0.flip(dims=[1])[:, :, 2]) / 2
                self.surface_list[1]._cps = cp0.reshape([-1, 3])


        class FEAParams(morphopt.FEAParams):
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
                ), name='Contact_ext')

            def define_steps(self):
                # One step amplitudes
                self.set_step_num(1)
                self.set_step_params(0, 'P_s1', [0.08])

            def create_fea(self, inp: torchfea.FEA_INP) -> torchfea.FEAController:

                # Use base implementation to build the deformable actuator instance and register interfaces
                fe = super().create_fea(inp)

                # Add cylinder
                self.add_instance_from_inp(
                    fe,
                    inp_path="D:/Work/code/morphopt/examples/tmech2025contact/grasp/obj.inp",
                    part_name='obj',
                    instance_name='obj',
                    part_name_new='cylinder',
                    instance_name_new='cylinder',
                    translation=[-3.,0,-5.]
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
                    self.objectivefuncs.boundarys.Cylinder(radius=12., height=80., bottom=0.))
    
if __name__ == '__main__':
    morphopt.start_optimization(device='cuda:0')
