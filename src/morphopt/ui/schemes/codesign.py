"""Co-design scheme template: shape + SIMP material + offset shell.

Mirrors ``myjobs/codesign/stiffness_bend.py``: an outer (usually frozen) BSP
cylinder, a designable inner cavity (CPGEO/BSP) whose offset shell carries the
pressure load, an interior SIMP density field and a separate homogeneous shell
material.
"""

from __future__ import annotations

from ..model.problem import Node
from ..model import schemas as S
from .base import SchemeTemplate


class CodesignTemplate(SchemeTemplate):
    scheme = "codesign"
    label = S.SCHEME_LABELS["codesign"]

    BASES = {
        "controller": "morphopt.Controller",
        "params": "morphopt.codesign.Params",
        "geometry": "morphopt.codesign.CodesignGeometry",
        "fea": "morphopt.codesign.CodesignFEAParams",
        "material": "morphopt.codesign.CodesignMaterials",
        "objective": "morphopt.codesign.ObjectiveFunction",
        "solver": "morphopt.codesign.Solver",
        "updaters": "morphopt.codesign.Updaters",
        "updater_geom": "morphopt.codesign.UpdaterGeometries",
        "updater_mat": "morphopt.codesign.UpdaterMaterials",
    }

    def default_objective_slot(self) -> str:
        # Tip displacement produced by the pressurised step (step index 1).
        return (
            "return self.fe_results[1].GC[-2] - self.fe_results[0].GC[-2]\n"
        )

    def default_metrics_slot(self) -> str:
        return "return [self.fe_results[1].GC[-2]]\n"

    def default_apply_surface_constraints(self) -> str:
        # mirror symmetry on the (designable) inner cavity surface 1
        return (
            "a: ThisController.Params.GeometryParams.CPGEO = self.surface_list[1]\n"
            "cp0 = a._cps.reshape(a.model.size[0], a.model.size[1], 3)\n"
            "import torch\n"
            "cp0[:, :, 0] = (cp0[:, :, 0] + torch.flip(cp0[:, :, 0], dims=[1])) / 2\n"
            "cp0[:, :, 2] = (cp0[:, :, 2] + torch.flip(cp0[:, :, 2], dims=[1])) / 2\n"
        )

    def default_map_bsp_designfield(self) -> str:
        # Keep material outside the outer radius as void.
        return (
            "# material symmetry / void mask; adjust to the problem.\n"
            "return nodes\n"
        )

    def build_root(self) -> Node:
        root = Node("problem")

        # geometry ----------------------------------------------------------
        geo = Node("geometry", name="Geometry (+ offset shell)")
        geo.params.update({
            "fea_seed_size": 2.5,
            "mesh_order": 2,
            "reinitialize_per_iter": 10,
            "thickness": 2.0,
            "num_layers": 1,
        })
        geo.params["_apply_surface_constraints"] = self.default_apply_surface_constraints()

        outer = self.new_surface_node("bsp_cylinder", 0)
        outer.params.update(r0=10.0, length=100.0, seed_size=1.0,
                            degree=3, maxR=0.1, maxC=1.0, maxFF=0.2, perturbation_L=-1.0)

        inner = self.new_surface_node("cpgeo_sphere", 1)
        inner.params.update(r0=7.0, seed_size=1.5,
                            init_location=[0.0, 0.0, 50.0], MaxC=1.5)
        geo.add_child(outer)
        geo.add_child(inner)
        root.add_child(geo)

        # loads (pressure acts on the offset shell face surface_1_offset) ----
        loads = Node("loads", name="Loads")
        bc = self.new_interface_node("BoundaryCondition")
        bc.name = "bc_fix"
        bc.params.update(instance_name="final_model", set_nodes_name="surface_0_Bottom",
                         index_dof=[0, 1, 2])
        rp = self.new_interface_node("ReferencePoint")
        rp.name = "RP_head"
        rp.params.update(rp_location=[0.0, 0.0, 100.0])
        cp = self.new_interface_node("Couple")
        cp.name = "couple_head"
        cp.params.update(rp_name="RP_head", instance_name="final_model", set_nodes_name="surface_0_Head")
        pr = self.new_interface_node("Pressure")
        pr.name = "pressure_1"
        pr.params.update(instance_name="final_model", surface_name="surface_1_offset")
        for n in (bc, rp, cp, pr):
            loads.add_child(n)
        root.add_child(loads)

        # steps (two steps: un-pressurised reference then pressurised) -------
        steps = Node("steps", name="Load steps")
        steps.params.update(
            num_steps=2,
            step_values=[{}, {"pressure_1": [0.1]}],
        )
        root.add_child(steps)

        # materials ---------------------------------------------------------
        mat = self.new_material_node()
        mat.params.update(mumax=4.5, kappamax=45.0, simp_ratio_min=1e-4,
                          density=1.08e-9, initial_ratio=0.5,
                          bounding_box=[-10.0, 10.0, -10.0, 10.0, 0.0, 100.0],
                          simp_field_resolution=1.0, degree=3, voidpenalfactor=1e-1,
                          elementname="C3D4",
                          shell_mu=0.48, shell_kappa=4.8, shell_density=1.08e-9,
                          shell_elementname="C3D6")
        mat.params["_map_bsp_designfield"] = self.default_map_bsp_designfield()
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
        solver.params.update(num_process=1, gpus=[], task_index_list=[])
        root.add_child(solver)

        # updater (geometry + materials together) ----------------------------
        upd = Node("updater", name="Updater")
        upd.params["geometry"] = {
            "max_step_iter": 50,
            "if_update": [False, True],
            "objective_functions": [
                {"type": "ShapeDerivative", "params": {}},
            ],
            "constraints": [
                {"type": "Fairness", "params": {}},
                {"type": "Distance", "params": {"min_distance": [[0.0, 0.0], [0.0, 2.5]]}},
                {"type": "Cylinder", "params": {"radius": 9.0, "height": 97.0, "bottom": 3.0}},
                {"type": "InwardCurvatureRadius", "params": {}},
                {"type": "OffsetSurfaceMinThickness", "params": {"min_distance": 2.0}},
                {"type": "VolumeMaximization", "params": {"surf_idx": 1, "weight": 1e-2}},
            ],
            "code": "",
        }
        upd.params["materials"] = {
            "max_step_iter": 50,
            "if_update": True,
            "objective_functions": [
                {"type": "Sensitivity", "params": {"normalize_gradient": False}},
            ],
            "constraints": [
                {"type": "VolFrac", "params": {"volfrac_min": 0.0, "volfrac_max": 0.7,
                                               "penalty": 1e4, "element_name": "C3D4"}},
                {"type": "MinValue", "params": {"xmin": -15.0, "threshold": 0.0, "p": 2}},
                {"type": "MaxValue", "params": {"xmax": 15.0, "threshold": 0.0, "p": 2}},
            ],
            "code": "",
        }
        root.add_child(upd)

        return root
