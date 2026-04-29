import os
import sys

from torch.nn.modules import loss

os.environ['KMP_DUPLICATE_LIB_OK']='True'
sys.path.append(os.getcwd())

import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import torch
import morphopt


class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder='Z:/Results', 
                         opt_label='RIGID')

    class ObjectiveFunction(morphopt.ObjectiveFunction):
        def __init__(self):
            super().__init__()

        def objective_function(self):
            assembly = self.fe.assembly
            rp_head_index = assembly.get_reference_point('RP_head')._RGC_index
            GC_start = assembly._GC_list_indexStart[rp_head_index]

            return (
                (20 - self.fe_results[0].GC[GC_start + 2])**2 / 100
                + self.fe_results[1].GC[GC_start]
                - self.fe_results[2].GC[GC_start]
                + self.fe_results[3].GC[GC_start + 1]
                - self.fe_results[4].GC[GC_start + 1]
                + 10 * self.fe_results[5].GC[GC_start + 5]
                - 10 * self.fe_results[6].GC[GC_start + 5]
            )
        
        def get_metrics(self):
            rp_head_index = self.fe.assembly.get_reference_point('RP_head')._RGC_index
            GC_start = self.fe.assembly._GC_list_indexStart[rp_head_index]
            return [self.fe_results[0].GC[GC_start + 2].item(),
                    self.fe_results[1].GC[GC_start].item() - self.fe_results[2].GC[GC_start].item(),
                    self.fe_results[3].GC[GC_start + 1].item() - self.fe_results[4].GC[GC_start + 1].item(),
                    self.fe_results[5].GC[GC_start + 5].item(),
                    -self.fe_results[5].GC[GC_start + 5].item(),]

    class Params(morphopt.Params):
        class GeometryParams(morphopt.GeometryParams):

            def __init__(self):

                super().__init__(reinitialize_per_iter=3, fea_seed_size=1.0)

                self.add_surface(
                    self.BSP.initialize_cylinder(r0=12.,
                                                            length=80.,
                                                            seed_size=1.5,
                                                            symmetric=[0, [1]],
                                                            flip=False, maxR=0.1, maxC=1.0, maxFF=0.2))

                
                self.add_surface(
                    self.CPGEO.initialize_Sphere(seed_size=1.0,
                                                flip=True,
                                                r0=5.,
                                                init_location=[0,0,20.],
                                                MaxC=0.6))
                
                self.add_surface(
                    self.CPGEO.initialize_Sphere(seed_size=1.0,
                                                flip=True,
                                                r0=5.,
                                                init_location=[0,0,60.],
                                                MaxC=0.6))



        class FEAParams(morphopt.FEAParams):

            def __init__(self):
                self.rp_dict: dict[str, morphopt.FEAParams.ReferencePointInterface] = {}
                super().__init__()

            def define_interface(self):

                # Common BC / RP / Couple
                self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='surface_0_Bottom', index_dof=[0,1,2]))
                self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 0., 80.]), name='RP_head')
                self.add_fea_interface(self.CoupleInterface(rp_name='RP_head', instance_name='final_model', set_nodes_name='surface_0_Head'))

                RP_Rigid1 = self.ReferencePointInterface(rp_location=[0., 0., 20.])
                self.rp_dict['RP_Rigid1'] = RP_Rigid1
                self.add_fea_interface(RP_Rigid1, name='RP_Rigid1')
                self.add_fea_interface(self.CoupleInterface(rp_name='RP_Rigid1', instance_name='final_model', set_nodes_name='surface_1_All'))

                RP_Rigid2 = self.ReferencePointInterface(rp_location=[0., 0., 60.])
                self.rp_dict['RP_Rigid2'] = RP_Rigid2
                self.add_fea_interface(RP_Rigid2, name='RP_Rigid2')
                self.add_fea_interface(self.CoupleInterface(rp_name='RP_Rigid2', instance_name='final_model', set_nodes_name='surface_2_All'))

                self.add_fea_interface(self.ConcentratedMomentInterface(rp_name='RP_head'),
                                        name='moment_1')
                
                self.add_fea_interface(self.ConcentratedForceInterface(rp_name='RP_head'),
                                        name='force_1')

            def define_steps(self):
                self.set_step_num(7)
                self.set_step_params(0, "moment_1", [0.0, 0.0, 0.0])
                self.set_step_params(0, "force_1", [0.0, 0.0, 20.0])

                self.set_step_params(1, "moment_1", [0.0, 0.0, 0.0])
                self.set_step_params(1, "force_1", [2.0, 0.0, 0.0])
                
                self.set_step_params(2, "moment_1", [0.0, 0.0, 0.0])
                self.set_step_params(2, "force_1", [-2.0, 0.0, 0.0])

                self.set_step_params(3, "moment_1", [0.0, 0.0, 0.0])
                self.set_step_params(3, "force_1", [0.0, 2.0, 0.0])
                
                self.set_step_params(4, "moment_1", [0.0, 0.0, 0.0])
                self.set_step_params(4, "force_1", [0.0, -2.0, 0.0])

                self.set_step_params(5, "moment_1", [0.0, 0.0, 100.0])
                self.set_step_params(5, "force_1", [0.0, 0.0, 0.0])

                self.set_step_params(6, "moment_1", [0.0, 0.0, -100.0])
                self.set_step_params(6, "force_1", [0.0, 0.0, 0.0])



            def reinitialize(self, iteration, *args, **kwargs):
                super().reinitialize(iteration, *args, **kwargs)

                # find the geometry center of each surface
                center_list = []
                for i in range(morphopt.controller.params.geometry.num_surface):
                    center_list.append(morphopt.controller.params.geometry.surface_list[i].control_points.mean(dim=0).tolist())

                self.rp_dict['RP_Rigid1'].rp_location = center_list[1]
                self.rp_dict['RP_Rigid2'].rp_location = center_list[2]

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
                            num_process=2)

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
                    params=params)

                shape_derivative = self.objectivefuncs.ShapeDerivative()
                self.add_objective_function(shape_derivative)
                self.add_constraints(
                    self.objectivefuncs.Fairness(surfaces=params.geometry, sensitivity=shape_derivative))
                self.add_constraints(
                    self.objectivefuncs.Distance(min_distance=
                                                                [[1.8, 1.2, 1.2, 1.2, 1.2],
                                                                [1.2, 1.2, 1.2, 1.2, 1.2],
                                                                [1.2, 1.2, 1.2, 1.2, 1.2],
                                                                [1.2, 1.2, 1.2, 1.2, 1.2],
                                                                [1.2, 1.2, 1.2, 1.2, 1.2]],))
                self.add_constraints(
                    self.objectivefuncs.boundarys.Cylinder(radius=12., height=77., bottom=3.))

                self.if_update = [False, True, True, True, True]
if __name__ == '__main__':
    morphopt.start_optimization(device='cuda')

