
import morphopt

class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder='/home/song/文档/code/morphopt/.temp', 
                         opt_label='EXAMPLE')
        
    class ObjectiveFunction(morphopt.ObjectiveFunction):
        def __init__(self):
            super().__init__()

        def objective_function(self):
            return self.fe_results[0].GC[-2]

        def get_metrics(self):
            return [self.fe_results[0].GC[-2]]

    class Params(morphopt.Params):
        class GeometryParams(morphopt.GeometryParams):

            def __init__(self):

                super().__init__(fea_seed_size=2.5, reinitialize_per_iter=5, mesh_order=2)

                self.add_surface(
                    self.BSP.initialize_cylinder(r0=8.,
                                                    length=80.,
                                                    seed_size=1.0,
                                                    symmetric=[1, [1]],
                                                    flip=False, maxR=0.1, maxC=1.0, maxFF=0.2, perturbation_L=12.))
                
                self.add_surface(
                    self.BSP.initialize_cylinder(r0=4.,
                                                    length=74.,
                                                    seed_size=1.0,
                                                    symmetric=[1, [1]],
                                                    init_location=[0, 0, 3],
                                                    flip=True, maxR=0.1, maxC=1.0, maxFF=0.2, perturbation_L=12.))
                
                # self.add_surface(
                #     self.CPGEO.initialize_Sphere(seed_size=1.0,
                #                                 flip=True,
                #                                 r0=4.,
                #                                 init_location=[0., 0., 40.],
                #                                 MaxC=1.5,
                #     ))

            def apply_surface_constraints(self) -> None:
                """
                Apply the constraints (e.g. the symmetric constraint) of the surfaces.
                """
                a: ThisController.Params.GeometryParams.BSP = self.surface_list[0]
                cp0 = a._cps.reshape(a.model.size[0], a.model.size[1], 3)
                import torch
                cp0[:, :, 0] = (cp0[:, :, 0] + torch.flip(cp0[:, :, 0], dims=[1])) / 2
                cp0[:, :, 1] = (cp0[:, :, 1] - torch.flip(cp0[:, :, 1], dims=[1])) / 2
                cp0[:, :, 2] = (cp0[:, :, 2] + torch.flip(cp0[:, :, 2], dims=[1])) / 2


        class FEAParams(morphopt.FEAParams):
            
            def __init__(self):
                super().__init__()

            def define_interface(self):
                # Common BC / RP / Couple
                self.add_fea_interface(self.BoundaryConditionInterface(instance_name='final_model', set_nodes_name='surface_0_Bottom', index_dof=[0,1,2]))
                self.add_fea_interface(self.ReferencePointInterface(rp_location=[0., 0., 80.]), name='RP_head')
                self.add_fea_interface(self.CoupleInterface(rp_name='RP_head', instance_name='final_model', set_nodes_name='surface_0_Head'))

                self.add_fea_interface(self.PressureInterface(instance_name='final_model', surface_name='surface_1_All'),
                                        name='pressure_1')

            def define_steps(self):
                self.set_step_num(1)
                self.set_step_params(0, "pressure_1", [0.06])
                

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
            super().__init__(surfaces=self.UpdaterGeometries(params=params),
                            loads=None, *args, **kwargs)

        class UpdaterGeometries(morphopt.UpdaterGeometries):
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
                                                                [[2.5, 2.5],
                                                                [2.5, 2.5]]))
                self.add_constraints(
                    self.objectivefuncs.boundarys.Cylinder(radius=12., height=80., bottom=0.))

    
if __name__ == '__main__':

    morphopt.start_optimization(device='cuda:0', restart_per_iteration=10)
