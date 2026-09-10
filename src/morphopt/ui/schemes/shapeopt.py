"""Shape-optimization scheme template (mirrors examples/bendingactuator.py)."""

from __future__ import annotations

from ..model.problem import Node, ProblemNode
from ..model import schemas as S
from .base import SchemeTemplate


class ShapeoptTemplate(SchemeTemplate):
    scheme = "shapeopt"
    label = "形状优化 (shapeopt)"
    label_en = "Shape optimization (shapeopt)"
    MATERIAL_TYPE = "HomogeneousMaterial"

    # class-name mapping consumed by the code generator
    BASES = {
        "controller": "morphopt.Controller",
        "params": "morphopt.shapeopt.Params",
        "geometry": "morphopt.shapeopt.GeometryParams",
        "fea": "morphopt.shapeopt.FEAParams",
        "material": "morphopt.shapeopt.HomogeneousMaterial",
        "objective": "morphopt.shapeopt.ObjectiveFunction",
        "solver": "morphopt.shapeopt.Solver",
        "updaters": "morphopt.shapeopt.Updaters",
        "updater_geom": "morphopt.shapeopt.UpdaterGeometries",
    }

    def default_apply_surface_constraints(self) -> str:
        # Mirror symmetry on the outer surface (index 0) inside GeometryParams.
        return (
            "# Mirror symmetry on the outer surface (index 0).\n"
            "a: ThisController.Params.GeometryParams.BSP = self.surface_list[0]\n"
            "cp0 = a._cps.reshape(a.model.size[0], a.model.size[1], 3)\n"
            "import torch\n"
            "cp0[:, :, 0] = (cp0[:, :, 0] + torch.flip(cp0[:, :, 0], dims=[1])) / 2\n"
            "cp0[:, :, 1] = (cp0[:, :, 1] - torch.flip(cp0[:, :, 1], dims=[1])) / 2\n"
            "cp0[:, :, 2] = (cp0[:, :, 2] + torch.flip(cp0[:, :, 2], dims=[1])) / 2\n"
        )

    def build_root(self) -> Node:
        root = ProblemNode()

        # geometry: outer cylinder (index 0) + inner cavity (index 1) --------
        geometry = self.make_geometry(fea_seed_size=1.0)
        geometry.add_surface(self.make_surface(
            "bsp_cylinder", 0,
            r0=8.0, length=80.0, seed_size=0.8, degree=3,
            maxR=0.2, maxC=1.5, maxFF=0.2, perturbation_L=10.0))
        geometry.add_surface(self.make_surface(
            "bsp_cylinder", 1,
            r0=4.0, length=74.0, seed_size=0.8,
            init_location=[0.0, 0.0, 3.0],
            maxR=0.2, maxC=1.5, maxFF=0.2, perturbation_L=10.0))
        root.add_section(geometry)

        # loads: fix the base, couple the head to a RP, pressurise the cavity
        loads = self.make_loads()
        loads.add_interface(self.make_interface(
            "BoundaryCondition", "bc_fix",
            instance_name="final_model", set_nodes_name="surface_0_Bottom",
            index_dof=[0, 1, 2]))
        loads.add_interface(self.make_interface(
            "ReferencePoint", "RP_head", rp_location=[0.0, 0.0, 80.0]))
        loads.add_interface(self.make_interface(
            "Couple", "couple_head",
            rp_name="RP_head", instance_name="final_model",
            set_nodes_name="surface_0_Head"))
        loads.add_interface(self.make_interface(
            "Pressure", "pressure_1",
            instance_name="final_model", surface_name="surface_1_All"))
        root.add_section(loads)

        # steps: single pressurised load step --------------------------------
        root.add_section(self.make_steps(1, [{"pressure_1": [0.06]}]))

        # material: homogeneous hyperelastic --------------------------------
        root.add_section(self.make_material(mu=0.482, kappa=4.8, density=1.08e-9))

        # objective + solver -------------------------------------------------
        root.add_section(self.make_objective())
        root.add_section(self.make_solver(num_process=4))

        # updater: shape-geometry optimiser only -----------------------------
        root.add_section(self.make_updater(
            geometry=S.geometry_updater_config(
                max_step_iter=50,
                if_update=[True, True],          # both surfaces move
                objective_functions=(S.updater_objective("ShapeDerivative"),),
                equality_constraints=(S.equality_constraint(
                                          "MirrorSymmetry",
                                          code=self.default_apply_surface_constraints()),),
                constraints=(S.updater_constraint("Fairness"),
                             S.updater_constraint("Distance"),
                             S.updater_constraint("Cylinder")),
            ),
            materials=None,
        ))

        return root
