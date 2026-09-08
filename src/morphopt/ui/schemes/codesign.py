"""Co-design scheme template: shape + SIMP material + offset shell.

Mirrors ``myjobs/codesign/stiffness_bend.py``: an outer (usually frozen) BSP
cylinder, a designable inner cavity (CPGEO/BSP) whose offset shell carries the
pressure load, an interior SIMP density field and a separate homogeneous shell
material.
"""

from __future__ import annotations

from ..model.problem import Node, ProblemNode
from ..model import schemas as S
from .base import SchemeTemplate


class CodesignTemplate(SchemeTemplate):
    scheme = "codesign"
    label = "协同设计优化 (codesign)"
    label_en = "Co-design optimization (codesign)"
    MATERIAL_TYPE = "CodesignMaterials"
    geometry_title = "Geometry (+ offset shell)"

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
        # Minimal valid scalar placeholder for the pressurised load step.
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
        root = ProblemNode()

        # geometry: frozen outer cylinder (0) + designable inner cavity (1) --
        geometry = self.make_geometry()
        geometry.add_surface(self.make_surface(
            "bsp_cylinder", 0,
            r0=10.0, length=100.0, seed_size=1.0, degree=3,
            maxR=0.1, maxC=1.0, maxFF=0.2, perturbation_L=-1.0))
        geometry.add_surface(self.make_surface(
            "cpgeo_sphere", 1,
            r0=7.0, seed_size=1.5,
            init_location=[0.0, 0.0, 50.0], MaxC=1.5))
        root.add_section(geometry)

        # loads: pressure acts on the offset-shell face surface_1_offset -----
        loads = self.make_loads()
        loads.add_interface(self.make_interface(
            "BoundaryCondition", "bc_fix",
            instance_name="final_model", set_nodes_name="surface_0_Bottom",
            index_dof=[0, 1, 2]))
        loads.add_interface(self.make_interface(
            "ReferencePoint", "RP_head", rp_location=[0.0, 0.0, 100.0]))
        loads.add_interface(self.make_interface(
            "Couple", "couple_head",
            rp_name="RP_head", instance_name="final_model",
            set_nodes_name="surface_0_Head"))
        loads.add_interface(self.make_interface(
            "Pressure", "pressure_1",
            instance_name="final_model", surface_name="surface_1_offset"))
        root.add_section(loads)

        # steps: un-pressurised reference (0) then pressurised (1) -----------
        root.add_section(self.make_steps(2, [{}, {"pressure_1": [0.1]}]))

        # material: SIMP solid core + homogeneous offset shell ---------------
        root.add_section(self.make_material(
            mumax=4.5, kappamax=45.0, simp_ratio_min=1e-4,
            density=1.08e-9, initial_ratio=0.5,
            bounding_box=[-10.0, 10.0, -10.0, 10.0, 0.0, 100.0],
            simp_field_resolution=1.0, degree=3, voidpenalfactor=1e-1,
            elementname="C3D4",
            shell_mu=0.48, shell_kappa=4.8, shell_density=1.08e-9,
            shell_elementname="C3D6"))

        # objective + solver -------------------------------------------------
        root.add_section(self.make_objective())
        root.add_section(self.make_solver(num_process=1))

        # updater: shape geometry AND material co-optimised ------------------
        root.add_section(self.make_updater(
            geometry=S.geometry_updater_config(
                max_step_iter=50,
                if_update=[False, True],           # keep the outer surface frozen
                objective_functions=(S.updater_objective("ShapeDerivative"),),
                constraints=(S.updater_constraint("Fairness"),
                             S.updater_constraint(
                                 "Distance",
                                 min_distance=[[0.0, 0.0], [0.0, 2.5]]),
                             S.updater_constraint("Cylinder",
                                                  radius=9.0, height=97.0, bottom=3.0),
                             S.updater_constraint("InwardCurvatureRadius"),
                             S.updater_constraint("OffsetSurfaceMinThickness"),
                             S.updater_constraint("VolumeMaximization")),
            ),
            materials=S.materials_updater_config(
                max_step_iter=50,
                if_update=True,
                objective_functions=(S.updater_objective("Sensitivity"),),
                constraints=(S.updater_constraint(
                                 "VolFrac",
                                 volfrac_min=0.0, volfrac_max=0.7,
                                 penalty=1e4, element_name="C3D4"),
                             S.updater_constraint("MinValue"),
                             S.updater_constraint("MaxValue")),
            ),
        ))

        return root
