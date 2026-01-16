import os
import sys

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
        def get_objective(self, *args, **kwargs):

            rp_head_index = self.fe.assembly.get_reference_point('RP_head')._RGC_index

            GC_start = self.fe.assembly._GC_list_indexStart[rp_head_index]

            loss1 = torch.exp(1.5-self.U[0][GC_start + 4]) * 5
            loss11 = -self.U[5][GC_start + 4]
            loss2 = self.U[1][GC_start + 3]
            loss3 = -self.U[2][GC_start + 3]
            loss4 = self.U[3][GC_start + 5]
            loss5 = -self.U[4][GC_start + 5]
            return loss1 + loss2 + loss3 + loss4 + loss5 + loss11
        
        def get_metrics(self):
            rp_head_index = self.fe.assembly.get_reference_point('RP_head')._RGC_index
            GC_start = self.fe.assembly._GC_list_indexStart[rp_head_index]
            return [self.U[0][GC_start + 4],
                    self.U[1][GC_start + 3],
                    self.U[2][GC_start + 3],
                    self.U[3][GC_start + 5],
                    self.U[4][GC_start + 5],
                    self.U[5][GC_start + 4],]

    class Params(morphopt.Params):
        class GeometryParams(morphopt.GeometryParams):

            def __init__(self):

                super().__init__(reinitialize_per_iter=3, fea_seed_size=1.0, fea_mesh_order=1)

                self.add_surface(
                    self.BSP.initialize_cylinder(r0=12.,
                                                            length=80.,
                                                            seed_size=1.5,
                                                            symmetric=[0, [1]],
                                                            flip=False, maxR=0.1, maxC=1.0, maxFF=0.2))
                
                self.add_surface(
                    self.CPGEO.initialize_Sphere(seed_size=0.8,
                                                 flip=True,
                                                 r0=3.,
                                                 init_location=[-6,0,40.],
                                                 MaxC=0.8))
                
                self.add_surface(
                    self.CPGEO.initialize_Sphere(seed_size=0.8,
                                                flip=True,
                                                r0=5.,
                                                init_location=[0,0,20.],
                                                MaxC=0.8))
                
                self.add_surface(
                    self.CPGEO.initialize_Sphere(seed_size=0.8,
                                                flip=True,
                                                r0=5.,
                                                init_location=[0,0,60.],
                                                MaxC=0.8))
                
                self.add_surface(
                    self.CPGEO.initialize_Sphere(seed_size=0.8,
                                                flip=True,
                                                r0=3.,
                                                init_location=[6,0,40.],
                                                MaxC=0.8))
                


        class FEAParams(morphopt.FEAParams):

            def __init__(self):
                self.rp_dict: dict[str, morphopt.FEAParams.ReferencePointInterface] = {}
                super().__init__()

                

            def define_interface(self):

                # Common BC / RP / Couple
                self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='surface_0_Bottom', index_dof=[0,1,2]))
                self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 0., 80.]), name='RP_head')
                self.add_fea_interface(self.CoupleInterface(rp_name='RP_head', instance_name='final_model', set_nodes_name='surface_0_Head'))

                RP_Rigid2 = self.ReferencePointInterface(rp_location=[0., 0., 20.])
                self.rp_dict['RP_Rigid2'] = RP_Rigid2
                self.add_fea_interface(RP_Rigid2, name='RP_Rigid2')
                self.add_fea_interface(self.CoupleInterface(rp_name='RP_Rigid2', instance_name='final_model', set_nodes_name='surface_2_All'))

                RP_Rigid3 = self.ReferencePointInterface(rp_location=[0., 0., 60.])
                self.rp_dict['RP_Rigid3'] = RP_Rigid3
                self.add_fea_interface(RP_Rigid3, name='RP_Rigid3')
                self.add_fea_interface(self.CoupleInterface(rp_name='RP_Rigid3', instance_name='final_model', set_nodes_name='surface_3_All'))

                RP_Rigid4 = self.ReferencePointInterface(rp_location=[0., 0., 40.])
                self.rp_dict['RP_Rigid4'] = RP_Rigid4
                self.add_fea_interface(RP_Rigid4, name='RP_Rigid4')
                self.add_fea_interface(self.CoupleInterface(rp_name='RP_Rigid4', instance_name='final_model', set_nodes_name='surface_4_All'))

                self.add_fea_interface(self.PressureInterface(instance_name='final_model', surface_name='surface_1_All'),
                                        name='pressure_1')
                
                self.add_fea_interface(self.ConcentratedMomentInterface(rp_name='RP_head'),
                                        name='moment_1')

            def define_steps(self):
                self.set_step_num(6)
                self.set_step_params(0, "pressure_1", [0.1])
                self.set_step_params(0, "moment_1", [0.0, 0.0, 0.0])

                self.set_step_params(1, "pressure_1", [0.0])
                self.set_step_params(1, "moment_1", [100., 0.0, 0.0])
                
                self.set_step_params(2, "pressure_1", [0.0])
                self.set_step_params(2, "moment_1", [-100., 0.0, 0.0])

                self.set_step_params(3, "pressure_1", [0.0])
                self.set_step_params(3, "moment_1", [0.0, 0.0, 100.])
                
                self.set_step_params(4, "pressure_1", [0.0])
                self.set_step_params(4, "moment_1", [0.0, 0.0, -100.])

                self.set_step_params(5, "pressure_1", [0.0])
                self.set_step_params(5, "moment_1", [0.0, -100.0, 0.0])

            def reinitialize(self, iteration, *args, **kwargs):
                super().reinitialize(iteration, *args, **kwargs)

                # find the geometry center of each surface
                center_list = []
                for i in range(morphopt.controller.params.geometry.num_surface):
                    center_list.append(morphopt.controller.params.geometry.surface_list[i].control_points.mean(dim=1).tolist())

                self.rp_dict['RP_Rigid2'].rp_location = center_list[2]
                self.rp_dict['RP_Rigid3'].rp_location = center_list[3]
                self.rp_dict['RP_Rigid4'].rp_location = center_list[4]

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

                shape_derivative = self.objectivefuncs.ShapeDerivativeDisplacement()
                self.add_objective_function(shape_derivative)
                self.add_constraints(
                    self.objectivefuncs.Fairness(surfaces=params.geometry, sensitivity=shape_derivative))
                self.add_constraints(
                    self.objectivefuncs.Distance(min_distance=
                                                                [[1.8, 2.5, 1.4, 1.4, 1.4],
                                                                [2.5, 2.0, 1.4, 1.4, 1.4],
                                                                [1.4, 1.4, 1.4, 1.4, 1.4],
                                                                [1.4, 1.4, 1.4, 1.4, 1.4],
                                                                [1.4, 1.4, 1.4, 1.4, 1.4]],))
                self.add_constraints(
                    self.objectivefuncs.boundarys.Cylinder(radius=12., height=77., bottom=3.))

                self.if_update = [True, True, True, True, True]
if __name__ == '__main__':
    morphopt.start_optimization(device='cuda')
