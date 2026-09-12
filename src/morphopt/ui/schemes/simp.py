"""SIMP topology optimization from a TorchFEA-authored fixed Assembly.

Mirrors the structure of ``myjobs/ral2026fea/beamsimp.py`` / ``examples/gripper.py``:
the imported mesh is fixed, the design variables live in a B-spline
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
    geometry_title = "Initial geometry (TorchFEA Assembly)"

    BASES = {
        "controller": "morphopt.Controller",
        "params": "morphopt.simp.Params",
        "geometry": "morphopt.simp.FixedGeometryTorchFEA",
        "fea": "morphopt.simp.FEAParams",
        "material": "morphopt.simp.SIMP_BSPFieldMaterials",
        "objective": "morphopt.simp.ObjectiveFunction",
        "solver": "morphopt.simp.SIMPSolver",
        "updaters": "morphopt.simp.Updaters",
        "updater_mat": "morphopt.simp.UpdaterMaterials",
    }

    def make_interface(self, interface_type: str, name=None,
                       **overrides):
        """Create an interface without conventional model-selection names."""
        spec = S.INTERFACE_TYPES.get(interface_type, {})
        for field in spec.get("params", []):
            if field["key"] in {
                "instance_name", "instance_name1", "instance_name2",
                "surface_name", "surface_name1", "surface_name2",
                "set_nodes_name",
            }:
                overrides.setdefault(field["key"], "")
        return super().make_interface(interface_type, name=name, **overrides)

    def default_objective_slot(self) -> str:
        # Total strain energy / compliance of every imported instance.
        return (
            "RGC = self.fe.assembly._GC2RGC(self.fe_results[0].GC)\n"
            "return sum(instance.potential_energy(RGC=RGC)\n"
            "           for instance in self.fe.assembly._instances.values())\n"
        )

    def default_metrics_slot(self) -> str:
        return "return []\n"

    def default_map_bsp_designfield(self) -> str:
        """Use the backend material class's standard spatial field mapping."""
        return "return nodes\n"

    def build_root(self) -> Node:
        root = ProblemNode()

        # The selected TorchFEA file supplies Parts, Instances and their sets.
        # Loads and constraints remain entirely user-defined in MorphOpt.
        root.add_section(self.make_geometry(
            model_directory="",
            model_filename="",
        ))

        # No default named faces, boundaries or loads: the user defines all
        # problem-specific dependencies explicitly.
        root.add_section(self.make_loads())

        root.add_section(self.make_steps(1, [{}]))

        # material: the SIMP B-spline density design field -------------------
        root.add_section(self.make_material(
            part_name="",
            mumax=10.0, kappamax=100.0, simp_ratio_min=1e-7,
            density=1.08e-9, initial_ratio=0.5,
            bounding_box=[0.0, 20.0, 0.0, 10.0, 0.0, 5.0],
            simp_field_resolution=0.5, degree=2, voidpenalfactor=1e-2,
            materialpenalty=8.0, elementname="C3D4"))

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
                                                  penalty=1e6, element_name="C3D4")),
            ),
        ))

        return root
