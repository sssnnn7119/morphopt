import morphopt


class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(
            path_result_folder="/run/media/song/缓存/results/",
            opt_label="BendingActuator",
        )

    class ObjectiveFunction(morphopt.shapeopt.ObjectiveFunction):
        def __init__(self):
            super().__init__()

        def objective_function(self):
            return self.fe_results[0].GC[-2]

        def get_metrics(self):
            return [self.fe_results[0].GC[-2]]

    class Params(morphopt.shapeopt.Params):
        class GeometryParams(morphopt.shapeopt.GeometryParams):
            def __init__(self):
                super().__init__(
                    fea_seed_size=2.0, reinitialize_per_iter=5, mesh_order=2
                )

                self.add_surface(
                    self.BSP.initialize_cylinder(
                        r0=12.0,
                        length=80.0,
                        seed_size=0.8,
                        symmetric=[1, [1]],
                        flip=False,
                        maxR=0.2,
                        maxC=1.5,
                        maxFF=0.2,
                        perturbation_L=10.0,
                    )
                )

                self.add_surface(
                    self.CPGEO.initialize_Sphere(
                        seed_size=1.5,
                        flip=True,
                        r0=7.0,
                        init_location=[0.0, 0.0, 40.0],
                        MaxC=1.5,
                    )
                )

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

        class FEAParams(morphopt.shapeopt.FEAParams):
            def __init__(self):
                super().__init__()

            def define_interface(self):
                # Common BC / RP / Couple
                self.add_fea_interface(
                    self.BoundaryConditionInterface(
                        instance_name="final_model",
                        set_nodes_name="surface_0_Bottom",
                        index_dof=[0, 1, 2],
                    )
                )
                self.add_fea_interface(
                    self.ReferencePointInterface(rp_location=[0.0, 0.0, 80.0]),
                    name="RP_head",
                )
                self.add_fea_interface(
                    self.CoupleInterface(
                        rp_name="RP_head",
                        instance_name="final_model",
                        set_nodes_name="surface_0_Head",
                    )
                )

                self.add_fea_interface(
                    self.PressureInterface(
                        instance_name="final_model", surface_name="surface_1_All"
                    ),
                    name="pressure_1",
                )

            def define_steps(self):
                self.set_step_num(1)
                self.set_step_params(0, "pressure_1", [0.06])

        class MaterialParams(morphopt.shapeopt.HomogeneousMaterial):
            def __init__(self):
                super().__init__(
                    mu=0.482,
                    kappa=4.8,
                    density=1.08e-9,
                )

        def __init__(self):
            super().__init__(
                surfaces=self.GeometryParams(),
                feamodel=self.FEAParams(),
                materials=self.MaterialParams(),
            )

    class Solver(morphopt.shapeopt.Solver):
        """
        Solver class for morphopt.
        This class is responsible for solving the finite element analysis (FEA) problem.
        """

        def __init__(self, params: morphopt.shapeopt.Params):

            super().__init__(params=params, available_gpus=["cuda:0"], num_process=1)

    class Updater(morphopt.shapeopt.Updaters):
        """
        Updater class for morphopt.
        This class is responsible for updating the design variables based on the results of the optimization process.
        """

        def __init__(self, params: morphopt.shapeopt.Params, *args, **kwargs):
            super().__init__(
                surfaces=self.UpdaterGeometries(params=params),
                device="cuda:0",
                *args,
                **kwargs,
            )

        class UpdaterGeometries(morphopt.shapeopt.UpdaterGeometries):
            """
            Updater class for morphopt.
            This class is responsible for updating the design variables based on the results of the optimization process.
            """

            def __init__(self, params: morphopt.shapeopt.Params):

                super().__init__(params=params, max_step_iter=200)

                shape_derivative = self.objectivefuncs.ShapeDerivative()
                self.add_objective_function(shape_derivative)
                self.add_constraints(
                    self.objectivefuncs.Fairness(surfaces=params.geometry)
                )
                self.add_constraints(
                    self.objectivefuncs.Distance(min_distance=[[2.5, 2.5], [2.5, 2.5]])
                )
                self.add_constraints(
                    self.objectivefuncs.boundarys.Cylinder(
                        radius=14.0, height=80.0, bottom=0.0
                    )
                )

                self.add_constraints(
                    self.objectivefuncs.VolumeMaximization(
                        geometryparam=self.params_update, surf_idx=1, weight=0.1
                    )
                )


if __name__ == "__main__":
    morphopt.start_optimization(device="cpu", restart_per_iteration=10, no_gui=True)
