"""SIMP topology-optimization scheme template (fixed mesh + density field).

Mirrors the structure of ``myjobs/ral2026fea/beamsimp.py`` / ``examples/gripper.py``:
the mesh is fixed (``FixedGeometryINP``), the design variables live in a B-spline
SIMP density field (``SIMP_BSPFieldMaterials``), updated by ``UpdaterMaterials``.
"""

from __future__ import annotations

from ..model.problem import Node
from ..model import schemas as S
from .base import SchemeTemplate


class SIMPTemplate(SchemeTemplate):
    scheme = "simp"
    label = S.SCHEME_LABELS["simp"]

    BASES = {
        "controller": "morphopt.Controller",
        "params": "morphopt.simp.Params",
        "geometry": "morphopt.simp.FixedGeometryINP",  # used as GeometryParams base
        "fea": "morphopt.simp.FEAParams",
        "material": "morphopt.simp.SIMP_BSPFieldMaterials",
        "objective": "morphopt.simp.ObjectiveFunction",
        "solver": "morphopt.simp.SIMPSolver",
        "updaters": "morphopt.simp.Updaters",
        "updater_mat": "morphopt.simp.UpdaterMaterials",
    }

    def default_objective_slot(self) -> str:
        # strain-energy / compliance objective on the first load step
        return (
            "RGC = self.fe.assembly._GC2RGC(self.fe_results[0].GC)\n"
            "return self.fe.assembly.get_instance('final_model').potential_energy(RGC=RGC)\n"
        )

    def default_metrics_slot(self) -> str:
        return "return []\n"

    def build_root(self) -> Node:
        root = Node("problem")

        # geometry = fixed mesh ---------------------------------------------
        geo = Node("geometry", name="Geometry (fixed mesh)")
        geo.params.update(mesh_file="", _apply_surface_constraints="pass\n")
        root.add_child(geo)

        # loads -------------------------------------------------------------
        loads = Node("loads", name="Loads")
        bc = self.new_interface_node("BoundaryCondition")
        bc.name = "bc_fix"
        bc.params.update(instance_name="final_model", set_nodes_name="fix", index_dof=[0, 1, 2])
        rp = self.new_interface_node("ReferencePoint")
        rp.name = "RP_load"
        rp.params.update(rp_location=[0.0, 0.0, 10.0])
        cp = self.new_interface_node("Couple")
        cp.name = "couple_load"
        cp.params.update(rp_name="RP_load", instance_name="final_model", set_nodes_name="loadedge")
        fo = self.new_interface_node("ConcentratedForce")
        fo.name = "force_1"
        fo.params.update(rp_name="RP_load")
        for n in (bc, rp, cp, fo):
            loads.add_child(n)
        root.add_child(loads)

        # steps -------------------------------------------------------------
        steps = Node("steps", name="Load steps")
        steps.params.update(num_steps=1, step_values=[{"force_1": [0.0, 0.0, -1e-1]}])
        root.add_child(steps)

        # materials (the SIMP design field) ---------------------------------
        mat = self.new_material_node()
        mat.params.update(mumax=10.0, kappamax=100.0, simp_ratio_min=1e-7,
                          density=1.08e-9, initial_ratio=0.5, bounding_box=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                          simp_field_resolution=0.5, degree=2, voidpenalfactor=1e-2,
                          materialpenalty=8.0, elementname="C3D8")
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

        # updater (material only) -------------------------------------------
        upd = Node("updater", name="Updater")
        upd.params["geometry"] = None
        upd.params["materials"] = {
            "max_step_iter": 100,
            "if_update": True,
            "objective_functions": [
                {"type": "Sensitivity", "params": {"normalize_gradient": False}},
                {"type": "DensityFieldMinimize", "params": {"scale": 1e-7}},
            ],
            "constraints": [
                {"type": "MinValue", "params": {"xmin": -15.0, "threshold": 0.0, "p": 2}},
                {"type": "MaxValue", "params": {"xmax": 15.0, "threshold": 0.0, "p": 2}},
                {"type": "VolFrac", "params": {"volfrac_min": 0.4, "volfrac_max": 0.6,
                                               "penalty": 1e6, "element_name": "C3D8"}},
            ],
            "code": "",
        }
        root.add_child(upd)

        return root
