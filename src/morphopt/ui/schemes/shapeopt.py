"""Shape-optimization scheme template (mirrors examples/bendingactuator.py)."""

from __future__ import annotations

from ..model.problem import Node, ProblemDefinition
from ..model import schemas as S
from .base import SchemeTemplate


class ShapeoptTemplate(SchemeTemplate):
    scheme = "shapeopt"
    label = S.SCHEME_LABELS["shapeopt"]

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

    def build_root(self) -> Node:
        root = Node("problem")

        # geometry ----------------------------------------------------------
        geo = Node("geometry", name="Geometry")
        geo.params.update({
            "fea_seed_size": 1.0,
            "mesh_order": 1,
            "reinitialize_per_iter": 5,
        })
        # code slot: symmetry constraint inside GeometryParams
        geo.params["_apply_surface_constraints"] = (
            "# Mirror symmetry on the outer surface (index 0).\n"
            "a: ThisController.Params.GeometryParams.BSP = self.surface_list[0]\n"
            "cp0 = a._cps.reshape(a.model.size[0], a.model.size[1], 3)\n"
            "import torch\n"
            "cp0[:, :, 0] = (cp0[:, :, 0] + torch.flip(cp0[:, :, 0], dims=[1])) / 2\n"
            "cp0[:, :, 1] = (cp0[:, :, 1] - torch.flip(cp0[:, :, 1], dims=[1])) / 2\n"
            "cp0[:, :, 2] = (cp0[:, :, 2] + torch.flip(cp0[:, :, 2], dims=[1])) / 2\n"
        )
        # outer boundary (surface index 0)
        outer = self.new_surface_node("bsp_cylinder", 0)
        outer.params.update(r0=8.0, length=80.0, seed_size=0.8,
                            degree=3, maxR=0.2, maxC=1.5, maxFF=0.2, perturbation_L=10.0)
        # inner cavity (surface index 1)
        inner = self.new_surface_node("bsp_cylinder", 1)
        inner.params.update(r0=4.0, length=74.0, seed_size=0.8,
                            init_location=[0.0, 0.0, 3.0],
                            maxR=0.2, maxC=1.5, maxFF=0.2, perturbation_L=10.0)
        geo.add_child(outer)
        geo.add_child(inner)
        root.add_child(geo)

        # loads -------------------------------------------------------------
        loads = Node("loads", name="Loads")
        bc = self.new_interface_node("BoundaryCondition")
        bc.name = "bc_fix"
        bc.params.update(instance_name="final_model", set_nodes_name="surface_0_Bottom",
                         index_dof=[0, 1, 2])
        rp = self.new_interface_node("ReferencePoint")
        rp.name = "RP_head"
        rp.params.update(rp_location=[0.0, 0.0, 80.0])
        cp = self.new_interface_node("Couple")
        cp.name = "couple_head"
        cp.params.update(rp_name="RP_head", instance_name="final_model",
                         set_nodes_name="surface_0_Head")
        pr = self.new_interface_node("Pressure")
        pr.name = "pressure_1"
        pr.params.update(instance_name="final_model", surface_name="surface_1_All")
        for n in (bc, rp, cp, pr):
            loads.add_child(n)
        root.add_child(loads)

        # steps -------------------------------------------------------------
        steps = Node("steps", name="Load steps")
        steps.params.update(
            num_steps=1,
            step_values=[{"pressure_1": [0.06]}],
        )
        root.add_child(steps)

        # materials ---------------------------------------------------------
        mat = self.new_material_node()
        mat.params.update(mu=0.482, kappa=4.8, density=1.08e-9)
        root.add_child(mat)

        # objective ---------------------------------------------------------
        obj = Node("objective", name="Objective Function")
        obj.params.update(
            jacobian_needed=[],
            _objective_function=self.default_objective_slot(),
            _get_metrics=self.default_metrics_slot(),
        )
        root.add_child(obj)

        # solver ------------------------------------------------------------
        solver = Node("solver", name="Solver")
        solver.params.update(num_process=4, gpus=[], task_index_list=[])
        root.add_child(solver)

        # updater -----------------------------------------------------------
        upd = Node("updater", name="Updater")
        upd.params["geometry"] = {
            "max_step_iter": 50,
            "if_update": [True, True],
            "objective_functions": [
                {"type": "ShapeDerivative", "params": {}},
            ],
            "constraints": [
                {"type": "Fairness", "params": {}},
                {"type": "Distance", "params": {"min_distance": [[2.5, 2.5], [2.5, 2.5]]}},
                {"type": "Cylinder", "params": {"radius": 10.0, "height": 80.0, "bottom": 0.0}},
            ],
            "code": "",
        }
        upd.params["materials"] = None
        root.add_child(upd)

        return root
