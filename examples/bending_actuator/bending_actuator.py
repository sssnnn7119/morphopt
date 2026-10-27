"""脚本与 UI 快速开始共用的气动弯曲优化算例。"""

import morphopt


class ThisController(morphopt.Controller):
    def __init__(self):
        super().__init__(path_result_folder=".results/", opt_label="BendingActuator")

    class ObjectiveFunction(morphopt.ObjectiveFunction):
        def reference_point_motion(self, step_name="load_case_1"):
            morphopt.controller.params.feamodel.process_fea(
                self.fe, step_name=step_name
            )
            assembly = self.fe.assembly
            coordinates = self.fe_results[step_name].GC.to(assembly.device)
            reference_point = assembly.get_reference_point("RP_1")
            return assembly._GC2RGC(coordinates)[reference_point._RGC_index].reshape(-1)

        def objective_function(self):
            return -self.reference_point_motion()[4]

        def get_metrics(self):
            return [self.reference_point_motion()[4].detach().cpu().item()]

    class Params(morphopt.Params):
        class GeometryParams(morphopt.GeometryParams):
            class Actuator(morphopt.BoundaryPart):
                def define_instance(self):
                    self.add_instance(self.part_name, "part1-1", [0.0] * 6)

                def define_surfaces(self):
                    for radius, length, location, flip in [
                        (8.0, 80.0, [0.0, 0.0, 0.0], False),
                        (4.0, 74.0, [0.0, 0.0, 3.0], True),
                    ]:
                        surface = self.BSP.initialize_cylinder(
                            r0=radius,
                            length=length,
                            seed_size=1.0,
                            init_location=location,
                            flip=flip,
                            maxR=0.2,
                            maxC=1.0,
                            maxFF=0.2,
                            perturbation_L=10.0,
                        )
                        surface.is_updatable = True
                        surface.add_constraint(surface.mirror("xz"))
                        self.add_surface_interface(surface)

            def define_interface(self):
                self.add_interface(
                    self.Actuator(fea_seed_size=1.0, mesh_order=1), name="part1"
                )

        class FEAParams(morphopt.FEAParams):
            def define_interface(self):
                self.add_interface(
                    self.BoundaryCondition(
                        instance_name="part1-1",
                        set_nodes_name="surface_0_Bottom",
                        index_dof=[0, 1, 2],
                    ),
                    name="bc_1",
                )
                self.add_interface(
                    self.ReferencePoint(rp_location=[0.0, 0.0, 80.0]), name="RP_1"
                )
                self.add_interface(
                    self.Couple(
                        rp_name="RP_1",
                        instance_name="part1-1",
                        set_nodes_name="surface_0_Head",
                    ),
                    name="couple_1",
                )
                self.add_interface(
                    self.Pressure(
                        instance_name="part1-1", surface_name="surface_1_All"
                    ),
                    name="pressure_1",
                )

            def define_steps(self):
                self.add_step("load_case_1")
                self.set_step_params("load_case_1", "pressure_1", [0.06])

        class MaterialsParams(morphopt.MaterialsParams):
            def define_interface(self):
                self.add_interface(
                    self.HomogeneousMaterial(
                        material_parameters=self.models.NeoHookeanLnJParams(
                            mu=0.482, kappa=4.8
                        ),
                        density=1.08e-9,
                        part_name="part1",
                    ),
                    name="material_1",
                )

        def __init__(self):
            super().__init__(
                geometry=self.GeometryParams(),
                feamodel=self.FEAParams(),
                materials=self.MaterialsParams(),
            )

    class Solver(morphopt.Solver):
        def __init__(self, params):
            super().__init__(params=params, num_process=1, process_devices=["cpu"])

    class Updater(morphopt.Updaters):
        def define_updater(self):
            self.add_geometry_updater(self.Shape(), name="part1")

        class Shape(morphopt.UpdaterBoundaryPart):
            def __init__(self):
                super().__init__(max_step_iter=50)

            def define_objective(self):
                self.add_objective_function(self.objectivefuncs.ShapeDerivative())
                self.add_constraints(self.objectivefuncs.Fairness())
                self.add_constraints(
                    self.objectivefuncs.Distance(min_distance=[[2.5, 2.5], [2.5, 2.5]])
                )
                self.add_constraints(
                    self.objectivefuncs.boundarys.Cylinder(
                        radius=10.0, height=80.0, bottom=0.0
                    )
                )


if __name__ == "__main__":
    morphopt.start_optimization(device="cpu", restart_per_iteration=20)
