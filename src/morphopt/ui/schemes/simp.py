"""SIMP topology-optimization scheme template (fixed mesh + density field).

Mirrors the structure of ``myjobs/ral2026fea/beamsimp.py`` / ``examples/gripper.py``:
the mesh is fixed (``FixedGeometryINP``), the design variables live in a B-spline
SIMP density field (``SIMP_BSPFieldMaterials``), updated by ``UpdaterMaterials``.
"""

from __future__ import annotations

from ..model.problem import Node, ProblemNode
from ..model import schemas as S
from .base import SchemeTemplate


class SIMPTemplate(SchemeTemplate):
    scheme = "simp"
    label = "拓扑/材料场优化 (simp)"
    label_en = "Topology / material-field optimization (simp)"
    MATERIAL_TYPE = "SIMP_BSPFieldMaterials"
    geometry_title = "Geometry (fixed mesh)"

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
        root = ProblemNode()

        # geometry: fixed mesh, no designable surface ------------------------
        root.add_section(self.make_geometry())

        # loads: fix the mesh, couple the loading RP to a node edge ----------
        loads = self.make_loads()
        loads.add_interface(self.make_interface(
            "BoundaryCondition", "bc_fix",
            instance_name="final_model", set_nodes_name="fix", index_dof=[0, 1, 2]))
        loads.add_interface(self.make_interface(
            "ReferencePoint", "RP_load", rp_location=[0.0, 0.0, 10.0]))
        loads.add_interface(self.make_interface(
            "Couple", "couple_load",
            rp_name="RP_load", instance_name="final_model",
            set_nodes_name="loadedge"))
        loads.add_interface(self.make_interface(
            "ConcentratedForce", "force_1", rp_name="RP_load"))
        root.add_section(loads)

        # steps: single load step carrying the tip force ---------------------
        root.add_section(self.make_steps(1, [{"force_1": [0.0, 0.0, -1e-1]}]))

        # material: the SIMP B-spline density design field -------------------
        root.add_section(self.make_material(
            mumax=10.0, kappamax=100.0, simp_ratio_min=1e-7,
            density=1.08e-9, initial_ratio=0.5,
            bounding_box=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            simp_field_resolution=0.5, degree=2, voidpenalfactor=1e-2,
            materialpenalty=8.0, elementname="C3D8"))

        # objective + solver -------------------------------------------------
        root.add_section(self.make_objective())
        root.add_section(self.make_solver(num_process=1))

        # updater: material-field optimiser only -----------------------------
        root.add_section(self.make_updater(
            geometry=None,
            materials=S.materials_updater_config(
                max_step_iter=50,
                if_update=True,
                objective_functions=(S.updater_objective("Sensitivity"),
                                     S.updater_objective("DensityFieldMinimize")),
                constraints=(S.updater_constraint("MinValue"),
                             S.updater_constraint("MaxValue"),
                             S.updater_constraint("VolFrac",
                                                  volfrac_min=0.4, volfrac_max=0.6,
                                                  penalty=1e6, element_name="C3D8")),
            ),
        ))

        return root
