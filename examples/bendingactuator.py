import morphopt


class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder=".results/", opt_label="BendingActuator")

    class ObjectiveFunction(morphopt.shapeopt.ObjectiveFunction):
        def __init__(self):
            super().__init__()

        def objective_function(self):
            return self.fe_results[0].GC[-2]

        def get_metrics(self):
            return [self.fe_results[0].GC[-2]]

    class Params(morphopt.shapeopt.Params):
        class GeometryParams(morphopt.shapeopt.GeometryParams):

            class BoundaryPart(morphopt.shapeopt.BoundaryPartInterface):

                def define_surfaces(self) -> None:
                    """
                    Register this Part's boundary surfaces in index order:
                    surface 0 is the outer boundary, 1.. are cavities.
                    """
                    self.add_surface_interface(
                        self.BSP.initialize_cylinder(
                            r0=8.0,
                            length=80.0,
                            seed_size=0.8,
                            flip=False,
                            maxR=0.2,
                            maxC=1.5,
                            maxFF=0.2,
                            perturbation_L=10.0,
                        )
                    )

                    self.add_surface_interface(
                        self.BSP.initialize_cylinder(
                            r0=4.0,
                            length=74.0,
                            seed_size=0.8,
                            init_location=[0, 0, 3],
                            flip=True,
                            maxR=0.2,
                            maxC=1.5,
                            maxFF=0.2,
                            perturbation_L=10.0,
                        )
                    )

                def apply_surface_constraints(self) -> None:
                    """
                    Apply the constraints (e.g. the surface constraint) of the surfaces.
                    """
                    a = self.surface_interfaces()[0]
                    cp0 = a._cps.reshape(a.model.size[0], a.model.size[1], 3)
                    import torch

                    cp0[:, :, 0] = (cp0[:, :, 0] + torch.flip(cp0[:, :, 0], dims=[1])) / 2
                    cp0[:, :, 1] = (cp0[:, :, 1] - torch.flip(cp0[:, :, 1], dims=[1])) / 2
                    cp0[:, :, 2] = (cp0[:, :, 2] + torch.flip(cp0[:, :, 2], dims=[1])) / 2

            def define_interface(self):

                self.add_interface(
                    self.BoundaryPart(
                        fea_seed_size=1.0,
                        mesh_order=1,
                    ),
                    name='body',
                )

        class FEAParams(morphopt.shapeopt.FEAParams):
            def __init__(self):
                super().__init__()

            def define_interface(self) -> None:
                # Common BC / RP / Couple
                self.add_interface(
                    self.BoundaryConditionInterface(
                        instance_name="body",
                        set_nodes_name="surface_0_Bottom",
                        index_dof=[0, 1, 2],
                    )
                )
                self.add_interface(
                    self.ReferencePointInterface(rp_location=[0.0, 0.0, 80.0]),
                    name="RP_head",
                )
                self.add_interface(
                    self.CoupleInterface(
                        rp_name="RP_head",
                        instance_name="body",
                        set_nodes_name="surface_0_Head",
                    )
                )

                self.add_interface(
                    self.PressureInterface(
                        instance_name="body", surface_name="surface_1_All"
                    ),
                    name="pressure_1",
                )

            def define_steps(self):
                self.set_step_num(1)
                self.set_step_params(0, "pressure_1", [0.06])

        class MaterialsParams(morphopt.shapeopt.MaterialsParams):
            def define_interface(self) -> None:
                self.add_interface(
                    self.HomogeneousMaterial(
                        material_parameters=self.materialmodels.NeoHookeanLnJParams(
                            mu=0.482, kappa=4.8
                        ),
                        density=1.08e-9,
                        part_name="body",
                    ),
                    name="body",
                )

        def __init__(self):
            super().__init__(
                geometry=self.GeometryParams(),
                feamodel=self.FEAParams(),
                materials=self.MaterialsParams(),
            )

    class Solver(morphopt.shapeopt.Solver):
        """
        Solver class for morphopt.
        This class is responsible for solving the finite element analysis (FEA) problem.
        """

        def __init__(self, params: morphopt.shapeopt.Params):

            super().__init__(params=params, available_gpus=["cpu"], num_process=1)

    class Updater(morphopt.shapeopt.Updaters):
        """
        Updater class for morphopt.
        This class is responsible for updating the design variables based on the results of the optimization process.
        """

        def define_updater(self) -> None:
            self.add_geometry_updater(self.UpdaterBoundaryPart(), name='body')


        class UpdaterBoundaryPart(morphopt.shapeopt.UpdaterBoundaryPart):
            """
            Updater class for morphopt.
            This class is responsible for updating the design variables based on the results of the optimization process.
            """

            def __init__(self):

                super().__init__(max_step_iter=200)

            def define_objective(self) -> None:
                shape_derivative = self.objectivefuncs.ShapeDerivative()
                self.add_objective_function(shape_derivative)
                self.add_constraints(
                    self.objectivefuncs.Fairness()
                )
                self.add_constraints(
                    self.objectivefuncs.Distance(min_distance=[[2.5, 2.5], [2.5, 2.5]])
                )
                self.add_constraints(
                    self.objectivefuncs.boundarys.Cylinder(
                        radius=10.0, height=80.0, bottom=0.0
                    )
                )

if __name__ == "__main__":
    morphopt.start_optimization(device="cpu", restart_per_iteration=10)
