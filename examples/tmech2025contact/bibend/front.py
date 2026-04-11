import os
import sys

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
                         opt_label='BIBEND')

    class ObjectiveFunction(morphopt.ObjectiveFunction):
        def __init__(self):
            super().__init__()

        def objective_function(self):
            assembly = self.fe.assembly
            rp_index = assembly.get_reference_point('RP_head')._RGC_index
            return -self.fe_results[0].GC[assembly._GC_list_indexStart[rp_index] + 4]
            
        def get_metrics(self):
            return []

    class Params(morphopt.Params):
        class GeometryParams(morphopt.GeometryParams):

            def __init__(self):

                super().__init__(max_step_length=[0.4, 0.4, 0.4, 0.4], fea_seed_size=0.9, fea_mesh_order=1)

                self.add_surface(
                    self.BSP.initialize_cylinder(r0=21.,
                                                            length=50.,
                                                            seed_size=1.0,
                                                            symmetric=[1, [1]],
                                                            flip=False, maxR=0.1, maxC=1.2, maxFF=0.2, perturbation_L=10.0))
                
                self.add_surface(
                self.BSP.initialize_cylinder(r0=6.,
                                                        length=44.,
                                                        seed_size=1.0,
                                                        symmetric=[1, [1]],
                                                        init_location=[-11, 0, 3],
                                                        flip=True, maxR=0.1, maxC=1.2, maxFF=0.2, perturbation_L=10.0))
            
                self.add_surface(
                self.BSP.initialize_cylinder(r0=6.,
                                                        length=44.,
                                                        seed_size=1.0,
                                                        symmetric=[1, [1]],
                                                        init_location=[11, 0, 3],
                                                        flip=True, maxR=0.1, maxC=1.2, maxFF=0.2, perturbation_L=10.0))
                
                
                self.if_update = [True, True, True]


            def _symmetry(self, control_points: torch.Tensor):
                # for the surface 0
                # rotation symmetric
                s1 = int(control_points.shape[1] / 4)
                part1 = control_points[:, 0:s1, :].clone()
                part2 = control_points[:, s1:s1*2, :].clone()
                part3 = control_points[:, s1*2:s1*3, :].clone()
                part4 = control_points[:, s1*3:s1*4, :].clone()

                part2_flipped = part2.flip(dims=[1]).clone()
                part2_flipped = torch.cat([part2_flipped[..., 0:1] * -1, part2_flipped[..., 1:]], dim=2)
                
                part3_mod = part3.clone()
                part3_mod = torch.cat([part3_mod[..., 0:1] * -1, part3_mod[..., 1:2] * -1, part3_mod[..., 2:]], dim=2)
                
                part4_flipped = part4.flip(dims=[1]).clone()
                part4_flipped = torch.cat([part4_flipped[..., 0:1], part4_flipped[..., 1:2] * -1, part4_flipped[..., 2:]], dim=2)

                part1_avg = (part1 + part2_flipped + part3_mod + part4_flipped) / 4
                
                part2_result = part1_avg.flip(dims=[1]).clone()
                part2_result = torch.cat([part2_result[..., 0:1] * -1, part2_result[..., 1:]], dim=2)
                
                part3_result = part1_avg.clone()
                part3_result = torch.cat([part3_result[..., 0:1] * -1, part3_result[..., 1:2] * -1, part3_result[..., 2:]], dim=2)
                
                part4_result = part1_avg.flip(dims=[1]).clone()
                part4_result = torch.cat([part4_result[..., 0:1], part4_result[..., 1:2] * -1, part4_result[..., 2:]], dim=2)

                return torch.cat([part1_avg, part2_result, part3_result, part4_result], dim=1)


            def apply_surface_constraints(self):



                cp0 = self.surface_list[0].control_points
                surfinterface0: morphopt.GeometryParams.BSP = self.surface_list[0]
                cp0 = cp0.reshape(surfinterface0.model.size[0], surfinterface0.model.size[1], 3)
                cp0 = self._symmetry(cp0)
                cp0[:, :, 0] = (cp0[:, :, 0] + cp0[:, :, 0].flip(dims=[1])) / 2
                cp0[:, :, 1] = (cp0[:, :, 1] - cp0[:, :, 1].flip(dims=[1])) / 2
                cp0[:, :, 2] = (cp0[:, :, 2] + cp0[:, :, 2].flip(dims=[1])) / 2
                surfinterface0._cps = cp0.reshape(-1, 3)

                cp1 = self.surface_list[1].control_points
                surfinterface1: morphopt.GeometryParams.BSP = self.surface_list[1]
                cp1 = cp1.reshape(surfinterface1.model.size[0], surfinterface1.model.size[1], 3)
                cp1[:, :, 0] = (cp1[:, :, 0] + cp1[:, :, 0].flip(dims=[1])) / 2
                cp1[:, :, 1] = (cp1[:, :, 1] - cp1[:, :, 1].flip(dims=[1])) / 2
                cp1[:, :, 2] = (cp1[:, :, 2] + cp1[:, :, 2].flip(dims=[1])) / 2
                surfinterface1._cps = cp1.reshape(-1, 3)

                control_points_ = self.surface_list[1].control_points.clone()

                control_points_[:, 0] *= -1
                control_points_[:, 1] *= -1

                self.surface_list[2]._cps = control_points_

                
        class FEAParams(morphopt.FEAParams):
            def __init__(self):
                super().__init__()

            def define_interface(self):
                # Common BC / RP / Couple
                self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='surface_0_Bottom', index_dof=[0,1,2]))
                self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 0., 50.]), name='RP_head')
                self.add_fea_interface(self.CoupleInterface(rp_name='RP_head', instance_name='final_model', set_nodes_name='surface_0_Head'))
                # Define interfaces
                self.add_fea_interface(self.PressureInterface(instance_name='final_model', surface_name='surface_1_All'), name='P_s1')
                self.add_fea_interface(self.ContactSelfInterface(instance_name='final_model', surface_name='surface_0_All'), name='CS_s0')
                self.add_fea_interface(self.ContactSelfInterface(instance_name='final_model', surface_name='surface_1_All'), name='CS_s1')
                self.add_fea_interface(self.ContactSelfInterface(instance_name='final_model', surface_name='surface_2_All'), name='CS_s2')

            def define_steps(self):
                # One step amplitudes
                self.set_step_num(1)
                self.set_step_params(0, 'P_s1', [0.06])
                
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
                                                                [[2.5, 2.5, 2.5, 2.5],
                                                                [2.5, 2.5, 2.5, 2.5],
                                                                [2.5, 2.5, 2.5, 2.5],
                                                                [2.5, 2.5, 2.5, 2.5]]))
                self.add_constraints(
                    self.objectivefuncs.boundarys.Cylinder(radius=22., height=50., bottom=0.))

    
if __name__ == '__main__':
    morphopt.start_optimization(device='cuda:0')

