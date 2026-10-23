"""CPU example: optimize a cylinder's NURBS side while keeping its rims fixed."""
from __future__ import annotations

from pathlib import Path

import torch
import morphopt

ASSET_PATH = Path(__file__).resolve().parent / "morphopt_assets/brep_face/cylinder.stp"


class ThisController(morphopt.Controller):
    def __init__(self) -> None:
        super().__init__(path_result_folder=".results", opt_label="BREPFace")

    class ObjectiveFunction(morphopt.ObjectiveFunction):
        def objective_function(self) -> torch.Tensor:
            # Pressure compresses the cylinder: minimizing Uz increases compliance.
            return self.fe_results["compression"].GC[-4]

        def get_metrics(self) -> list[torch.Tensor]:
            return [self.fe_results["compression"].GC[-4]]

    class Params(morphopt.Params):
        class GeometryParams(morphopt.GeometryParams):
            class Body(morphopt.BoundaryPart):
                def define_surfaces(self) -> None:
                    boundary = self.BREPSurface(ASSET_PATH, control_point_spacing=0.8)
                    # face_0 is the cylindrical side; face_1/face_2 are end caps.
                    boundary.select_design_faces(["face_0"])
                    boundary.is_updatable = True
                    self.add_surface_interface(boundary)

            def define_interface(self) -> None:
                self.add_interface(self.Body(fea_seed_size=1.2, mesh_order=1), name="body")

        class FEAParams(morphopt.FEAParams):
            def define_interface(self) -> None:
                self.add_interface(self.BoundaryCondition(
                    instance_name="body", set_nodes_name="surface_0_bottom_nodes",
                    index_dof=[0, 1, 2],
                ), name="fixed")
                self.add_interface(self.ReferencePoint(rp_location=[0, 0, 5]), name="tip")
                self.add_interface(self.Couple(
                    rp_name="tip", instance_name="body", set_nodes_name="surface_0_top_nodes",
                ), name="coupling")
                self.add_interface(self.Pressure(
                    instance_name="body", surface_name="surface_0_top",
                ), name="pressure")

            def define_steps(self) -> None:
                self.add_step("compression")
                self.set_step_params("compression", "pressure", [0.05])

        class MaterialsParams(morphopt.MaterialsParams):
            def define_interface(self) -> None:
                self.add_interface(self.HomogeneousMaterial(
                    material_parameters=self.models.NeoHookeanLnJParams(mu=10.0, kappa=100.0),
                    density=1e-9, part_name="body",
                ), name="material")

        def __init__(self) -> None:
            super().__init__(geometry=self.GeometryParams(), feamodel=self.FEAParams(),
                             materials=self.MaterialsParams())

    class Solver(morphopt.Solver):
        def __init__(self, params: morphopt.Params) -> None:
            super().__init__(params=params, available_gpus=[], num_process=1)

    class Updater(morphopt.Updaters):
        class Shape(morphopt.UpdaterBoundaryPart):
            def __init__(self) -> None:
                super().__init__(max_step_iter=3, max_step_length=0.02)

            def define_objective(self) -> None:
                self.add_objective_function(self.objectivefuncs.ShapeDerivative())

        def define_updater(self) -> None:
            self.add_geometry_updater(self.Shape(), name="body")


if __name__ == "__main__":
    morphopt.start_optimization(device="cpu", restart_per_iteration=20)
