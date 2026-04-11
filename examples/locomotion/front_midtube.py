import os
import sys
import numpy as np
os.environ['KMP_DUPLICATE_LIB_OK']='True'
sys.path.append(os.getcwd())
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import torch
import torchfea
import morphopt

class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder='Z:/Results', 
                         opt_label='FRONT')
        
    class ObjectiveFunction(morphopt.ObjectiveFunction):
        def __init__(self):
            super().__init__()

        def objective_function(self):
            Uz_neg = self.fe_results[0].GC[-4]
            Uz_pos = self.fe_results[1].GC[-4]
            force_z = self.fe_results[2].GC[-5]
            Urot = self.fe_results[3].GC[-2]
            Pz = self.fe_results[3].GC[-4] + 70.
            r = Pz / torch.sin(Urot)
            loss1 = torch.exp(1 - (Uz_pos - Uz_neg) / 24)
            loss2 = torch.exp(1 + Urot / 2.1) * 5
            loss3 = r

            print('elongation:', (Uz_pos - Uz_neg).item(), 'rotation:', Urot.item(), 'Pz:', Pz.item(), 'r:', r.item(), 'force_z:', force_z.item())
            np.savetxt(f'{morphopt.controller.path_result}/Log/Deformation/{morphopt.controller.history.iteration}.txt', np.array([morphopt.controller.history.iteration, (Uz_pos - Uz_neg).item(), Urot.item(), Pz.item(), r.item(), force_z.item()]), fmt='%f', delimiter=',', newline='\n', header='', footer='', comments='# ')

            return force_z + loss1 + loss2 + loss3
    
        def get_metrics(self):
            Uz_neg = self.fe_results[0].GC[-4]
            Uz_pos = self.fe_results[1].GC[-4]

            Urot = self.fe_results[3].GC[-2]
            Pz = self.fe_results[3].GC[-4] + 70.

            r = Pz / torch.sin(Urot)

            return [(Uz_pos - Uz_neg).item(), Urot.item(), Pz.item(), r.item(), self.fe_results[2].GC[-5].item()]

    class Params(morphopt.Params):
        class GeometryParams(morphopt.GeometryParams):

            def __rotate120_240(self, r0: torch.Tensor):

                size0 = r0.shape
                r0 = r0.reshape([-1, 3]).T

                r0_120 = torch.zeros_like(r0)
                r0_120[0] = r0[0] * np.cos(2 * np.pi / 3) - r0[1] * np.sin(
                    2 * np.pi / 3)
                r0_120[1] = r0[0] * np.sin(2 * np.pi / 3) + r0[1] * np.cos(
                    2 * np.pi / 3)
                r0_120[2] = r0[2]

                r0_240 = torch.zeros_like(r0)
                r0_240[0] = r0[0] * np.cos(4 * np.pi / 3) - r0[1] * np.sin(
                    4 * np.pi / 3)
                r0_240[1] = r0[0] * np.sin(4 * np.pi / 3) + r0[1] * np.cos(
                    4 * np.pi / 3)
                r0_240[2] = r0[2]

                return r0_120.T.reshape(list(size0)), r0_240.T.reshape(list(size0))

            def __init__(self):

                super().__init__(max_step_length=[0.2, 0.2, 0.2, 0.2,0.2], reinitialize_per_iter=4, fea_seed_size=1.0, fea_mesh_order=1)

                self.surface_list: list[morphopt.GeometryParams.BSP] = []

                self.add_surface(
                    self.BSP.initialize_cylinder(r0=21.,
                                                    length=70.,
                                                    seed_size=1.0,
                                                    flip=False,
                                                    maxR=0.1,
                                                    maxC=1.2,
                                                    maxFF=0.1, perturbation_L=14))
                self.add_surface(
                    self.BSP.initialize_cylinder(seed_size=1.0,
                                                    flip=True,
                                                    r0=5.,
                                                    length=64.,
                                                    maxR=0.1,
                                                    maxC=1.2,
                                                    maxFF=0.1,
                                                    init_location=[12, 0, 3], perturbation_L=14))

                self.add_surface(
                    self.BSP.initialize_cylinder(seed_size=1.0,
                                                    flip=True,
                                                    r0=5.,
                                                    length=64.,
                                                    maxR=0.1,
                                                    maxC=1.2,
                                                    maxFF=0.1,
                                                    init_location=[-6, 10.5, 3], perturbation_L=14))

                self.add_surface(
                    self.BSP.initialize_cylinder(seed_size=1.0,
                                                    flip=True,
                                                    r0=5.,
                                                    length=64.,
                                                    maxR=0.1,
                                                    maxC=1.2,
                                                    maxFF=0.1,
                                                    init_location=[-6, -10.5, 3], perturbation_L=14))
                
                self.add_surface(
                    self.BSP.initialize_cylinder(seed_size=1.0,
                                                    flip=False,
                                                    r0=3.,
                                                    length=64.,
                                                    maxR=0.1,
                                                    maxC=1.2,
                                                    maxFF=0.1,
                                                    init_location=[0, 0, 3]))
                

            def apply_surface_constraints(self):
                # rotate the exterior surface
                size0 = self.surface_list[0].model.size
                num_points = self.surface_list[0].model.size[1] / 3
                num_points = int(num_points)
                cp0 = self.surface_list[0]._cps.reshape(size0[0], size0[1], 3)
                r0 = cp0[:, :num_points]
                r0_120, r0_240 = self.__rotate120_240(r0)
                cp0[:, num_points:2 * num_points] = r0_120
                cp0[:, 2 * num_points:] = r0_240
                r0 = cp0.clone()
                cp0[:, :, 0] = (r0[:, :, 0] + r0.flip(dims=[1])[:, :, 0]) / 2
                cp0[:, :, 1] = (r0[:, :, 1] - r0.flip(dims=[1])[:, :, 1]) / 2
                cp0[:, :, 2] = (r0[:, :, 2] + r0.flip(dims=[1])[:, :, 2]) / 2
                self.surface_list[0]._cps = cp0.reshape([-1, 3])

                # rotate the bottom surface
                r1 = self.surface_list[1]._cps.reshape(self.surface_list[1].model.size[0], self.surface_list[1].model.size[1], 3)
                r1[:, :, 0] = (r1[:, :, 0] + r1.flip(dims=[1])[:, :, 0]) / 2
                r1[:, :, 1] = (r1[:, :, 1] - r1.flip(dims=[1])[:, :, 1]) / 2
                r1[:, :, 2] = (r1[:, :, 2] + r1.flip(dims=[1])[:, :, 2]) / 2
                self.surface_list[1]._cps = r1.reshape([-1, 3])

                r1_120, r1_240 = self.__rotate120_240(r1)
                self.surface_list[2]._cps = r1_120.reshape([-1, 3])
                self.surface_list[3]._cps = r1_240.reshape([-1, 3])

                # for the internal center tube
                size4 = self.surface_list[4].model.size
                num_points = self.surface_list[4].model.size[1] / 3
                num_points = int(num_points)
                cp4 = self.surface_list[4]._cps.reshape(size4[0], size4[1], 3)
                r4 = cp4[:, :num_points]
                r4_120, r4_240 = self.__rotate120_240(r4)
                cp4[:, num_points:2 * num_points] = r4_120
                cp4[:, 2 * num_points:] = r4_240
                r4 = cp4.clone()
                cp4[:, :, 0] = (r4[:, :, 0] + r4.flip(dims=[1])[:, :, 0]) / 2
                cp4[:, :, 1] = (r4[:, :, 1] - r4.flip(dims=[1])[:, :, 1]) / 2
                cp4[:, :, 2] = (r4[:, :, 2] + r4.flip(dims=[1])[:, :, 2]) / 2
                self.surface_list[4]._cps = cp4.reshape([-1, 3])
            
        class FEAParams(morphopt.FEAParams):
            def __init__(self):
                super().__init__()

            def define_interface(self):
                # Common BC / RP / Couple
                self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='surface_0_Bottom', index_dof=[0,1,2]))
                self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 0., 70.]), name='RP_head')
                self.add_fea_interface(self.CoupleInterface(rp_name='RP_head', instance_name='final_model', set_nodes_name='surface_0_Head'))
                # Define all load interfaces once
                self.add_fea_interface(self.PressureInterface(instance_name='final_model', surface_name='surface_1_All'), name='P_s1')
                self.add_fea_interface(self.PressureInterface(instance_name='final_model', surface_name='surface_2_All'), name='P_s2')
                self.add_fea_interface(self.PressureInterface(instance_name='final_model', surface_name='surface_3_All'), name='P_s3')

                self.add_fea_interface(self.BodyforceInterface(element_name='element-0', instance_name='final_model'), name='BodyForce')

                # Contact self (no amplitude, but needs to exist in FEA)
                self.add_fea_interface(self.ContactSelfInterface(instance_name='final_model', surface_name='surface_0_All'), name='CS_s0')
                self.add_fea_interface(self.ContactSelfInterface(instance_name='final_model', surface_name='surface_1_All'), name='CS_s1')
                self.add_fea_interface(self.ContactSelfInterface(instance_name='final_model', surface_name='surface_2_All'), name='CS_s2')
                self.add_fea_interface(self.ContactSelfInterface(instance_name='final_model', surface_name='surface_3_All'), name='CS_s3')

            def define_steps(self):
                # Define step amplitudes
                self.set_step_num(4)
                self.set_step_params(0, 'P_s1', [-0.08])
                self.set_step_params(0, 'P_s2', [-0.08])
                self.set_step_params(0, 'P_s3', [-0.08])
                self.set_step_params(0, 'BodyForce', [0., 0., 0.])

                self.set_step_params(1, 'P_s1', [0.08])
                self.set_step_params(1, 'P_s2', [0.08])
                self.set_step_params(1, 'P_s3', [0.08])
                self.set_step_params(1, 'BodyForce', [0., 0., 0.])

                self.set_step_params(2, 'P_s1', [0.08])
                self.set_step_params(2, 'P_s2', [0.08])
                self.set_step_params(2, 'P_s3', [0.08])
                self.set_step_params(2, 'BodyForce', [0., 9.81e-6, 0.])

                self.set_step_params(3, 'P_s1', [-0.08])
                self.set_step_params(3, 'P_s2', [0.1])
                self.set_step_params(3, 'P_s3', [0.1])
                self.set_step_params(3, 'BodyForce', [0., 0., 0.])

        class MaterialParams(morphopt.Materials):
            
            def __init__(self):
                super().__init__(mu=0.48, kappa=4.8, density=1.08e-9,)
        
        def __init__(self):
            super().__init__(surfaces=self.GeometryParams(), feamodel=self.FEAParams(), materials=self.MaterialParams())


    class Solver(morphopt.MorphSolver):
        """
        Solver class for morphopt.
        This class is responsible for solving the finite element analysis (FEA) problem.
        """

        def __init__(self, params: morphopt.Params):
            super().__init__(params=params,
                            num_process=2, task_index_list=[[0], [1, 2], [3]])
    
    
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

                shape_derivative = self.objectivefuncs.ShapeDerivative()
                self.add_objective_function(shape_derivative)
                self.add_constraints(
                    self.objectivefuncs.Fairness(surfaces=params.geometry, sensitivity=shape_derivative))
                self.add_constraints(
                    self.objectivefuncs.Distance(min_distance=
                                                                [[1.0, 2.5, 2.5, 2.5, 2.5],
                                                                [2.5, 2.0, 2.5, 2.5, 2.5],
                                                                [2.5, 2.5, 2.0, 2.5, 2.5],
                                                                [2.5, 2.5, 2.5, 2.0, 2.5],
                                                                [2.5, 2.5, 2.5, 2.5, 2.0]]))
                self.add_constraints(
                    self.objectivefuncs.boundarys.Cylinder(radius=22.5, height=70., bottom=0.))
                
                self.if_update = [True, True, True, True, False]

    
if __name__ == '__main__':
    morphopt.start_optimization(device='cuda:0', restart_per_iteration=10)

