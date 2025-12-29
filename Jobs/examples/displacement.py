import MorphOpt

class ThisController(MorphOpt.Controller):
    def __init__(self):
        super().__init__(path_result_folder='Z:/Results/', 
                         opt_label='EXAMPLE')
        
    class ObjectiveFunction(MorphOpt.ObjectiveFunction):
        def get_objective(self):
            loss1 = -self.U[0][-2]
            return loss1

    class Params(MorphOpt.Params):
        class GeometryParams(MorphOpt.GeometryParams):

            def __init__(self):

                super().__init__(fea_seed_size=1.5, fea_mesh_order=1, reinitialize_per_iter=5)

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


        class FEAParams(MorphOpt.FEAParams):

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

    class Updater(MorphOpt.Updaters):
        """
        Updater class for MorphOpt.
        This class is responsible for updating the design variables based on the results of the optimization process.
        """

        def __init__(self, params: MorphOpt.Params, *args, **kwargs):
            super().__init__(surfaces=self.UpdaterGeometries(params=params),
                            loads=None, *args, **kwargs)

        class UpdaterGeometries(MorphOpt.UpdaterGeometries):
            """
            Updater class for MorphOpt.
            This class is responsible for updating the design variables based on the results of the optimization process.
            """

            def __init__(self, params: MorphOpt.Params):

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
                    self.objectivefuncs.boundarys.Cylinder(radius=12., height=80., bottom=0.))

    
if __name__ == '__main__':
    MorphOpt.start_optimization(device='cuda:0', restart_per_iteration=4)
