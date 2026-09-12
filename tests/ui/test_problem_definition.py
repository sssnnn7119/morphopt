"""Regression tests for UI problem-tree invariants.

These tests intentionally exercise the model aggregate without importing Qt.
They protect the cross-node references that are easy to break when adding a
new tree editing entry point.
"""

import unittest
from pathlib import Path
import tempfile

import numpy as np
import torch
import torchfea

from morphopt.ui.codegen.generator import generate_source
from morphopt.ui.model.problem import ProblemDefinition
from morphopt.ui.model.schemas import INTERFACE_TYPES
from morphopt.ui.schemes.base import get_template
from morphopt.optcore.modelparams.geometry import (
    inspect_model, load_geometry_assembly)


def _codesign_problem():
    return get_template("codesign").create_problem("tree-invariants")


def _distance_matrix(problem):
    geometry_config = problem.updater.geometry_config()
    distance = next(
        item for item in geometry_config["constraints"]
        if item["type"] == "Distance"
    )
    return distance["params"]["min_distance"]


class ProblemDefinitionMutationTests(unittest.TestCase):
    @staticmethod
    def _write_torchfea_model(directory: str) -> Path:
        part = torchfea.Part(torch.tensor([
            [0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0], [0.0, 0.0, 1.0],
        ]))
        part.add_element(torchfea.elements.C3D4(
            elems_index=torch.tensor([0]),
            elems=torch.tensor([[0, 1, 2, 3]])), name="C3D4")
        part.add_node_set("fixed_nodes", np.array([0, 1, 2]))
        part.add_element_set("design_cells", np.array([0]))
        part.add_surface_set("loaded_surface", [(np.array([0]), 0)])
        part.exterior_surface = "loaded_surface"
        assembly = torchfea.Assembly()
        assembly.add_part(part, "body")
        second_part = torchfea.Serializable._deserialize(part._serialize())
        assembly.add_part(second_part, "frame")
        assembly.add_instance(torchfea.Instance("body"), "body-1")
        assembly.add_instance(
            torchfea.Instance("frame", translation=[2.0, 0.0, 0.0]),
            "frame-1")
        # Analysis-layer data may exist in a saved TorchFEA model, but the
        # MorphOpt geometry bridge must discard it.
        assembly.add_reference_point(
            torchfea.ReferencePoint([0.0, 0.0, 0.0]), "source-only-rp")
        controller = torchfea.FEAController()
        controller.assembly = assembly
        path = Path(directory) / "assembly.npz"
        controller.save_model(str(path), if_save_source_code=False)
        return path

    def test_simp_torchfea_model_has_no_preset_load_dependencies(self):
        problem = get_template("simp").create_problem("imported-domain")

        self.assertEqual(problem.geometry.model_directory, "")
        self.assertEqual(problem.geometry.model_filename, "")
        self.assertEqual(problem.interfaces(), [])
        self.assertEqual(problem.steps.step_values, [{}])
        boundary = get_template("simp").make_interface("BoundaryCondition")
        pressure = get_template("simp").make_interface("Pressure")
        self.assertEqual(boundary.instance_name, "")
        self.assertEqual(boundary.set_nodes_name, "")
        self.assertEqual(pressure.instance_name, "")
        self.assertEqual(pressure.surface_name, "")

        source = generate_source(problem)
        self.assertIn("morphopt.simp.FixedGeometryTorchFEA", source)
        self.assertIn("model_directory=''", source)
        self.assertNotIn("FixedGeometryINP", source)
        self.assertNotIn("loadedge", source)
        self.assertNotIn("bc_fix", source)
        compile(source, "<empty-imported-domain>", "exec")

    def test_simp_import_reads_assembly_names_and_strips_analysis_objects(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_torchfea_model(directory)
            problem = get_template("simp").create_problem("linked-assembly")
            problem.geometry.model_directory = directory
            problem.geometry.model_filename = path.name
            problem.material.part_name = "body"

            summary = inspect_model(directory, path.name)
            self.assertEqual([part.name for part in summary.parts],
                             ["body", "frame"])
            self.assertEqual(
                summary.part_for_instance("body-1").node_sets,
                ("fixed_nodes",))
            self.assertEqual(
                summary.part_for_instance("body-1").surface_sets,
                ("loaded_surface",))
            self.assertEqual(
                summary.part_for_instance("body-1").element_sets,
                ("design_cells",))
            self.assertEqual(problem.instance_names(), ["body-1", "frame-1"])
            self.assertEqual(problem.surface_set_names("body-1"),
                             ["loaded_surface"])

            boundary = get_template("simp").make_interface(
                "BoundaryCondition", "clamp", instance_name="body-1",
                set_nodes_name="fixed_nodes")
            problem.add_interface(boundary)

            restored = ProblemDefinition.from_dict(problem.to_dict())
            self.assertEqual(restored.geometry.model_filename, "assembly.npz")
            source = generate_source(restored)
            self.assertIn("FixedGeometryTorchFEA", source)
            self.assertIn("model_filename='assembly.npz'", source)
            compile(source, "<linked-assembly>", "exec")

            clean = load_geometry_assembly(directory, path.name)
            self.assertEqual(list(clean._parts), ["body", "frame"])
            self.assertEqual(list(clean._instances), ["body-1", "frame-1"])
            self.assertEqual(len(clean._loads), 0)
            self.assertEqual(len(clean._boundarys), 0)
            self.assertEqual(len(clean._constraints), 0)
            self.assertEqual(len(clean._reference_points), 0)

            boundary.set_nodes_name = "missing"
            with self.assertRaisesRegex(ValueError, "unknown set_nodes_name"):
                generate_source(problem)

    def test_default_schemes_round_trip_and_generate_valid_python(self):
        for scheme in ("shapeopt", "simp", "codesign"):
            with self.subTest(scheme=scheme):
                original = get_template(scheme).create_problem("round-trip")
                restored = ProblemDefinition.from_dict(original.to_dict())

                self.assertEqual(type(restored.root).__name__, "ProblemNode")
                self.assertEqual(restored.to_dict(), original.to_dict())
                compile(generate_source(restored), f"<{scheme}-generated>", "exec")

    def test_surface_equality_is_a_geometry_constraint_item(self):
        for scheme in ("shapeopt", "codesign"):
            with self.subTest(scheme=scheme):
                problem = get_template(scheme).create_problem("equality")
                config = problem.updater.geometry_config()
                equality = next(
                    item for item in config["equality_constraints"]
                    if item["type"] == "MirrorSymmetry"
                )
                self.assertTrue(equality["params"]["code"].strip())
                self.assertEqual(config["constraints"][0]["type"], "Fairness")
                source = generate_source(problem)
                self.assertIn("def apply_surface_constraints(self):", source)
                # The hard projection is emitted on GeometryParams, not
                # incorrectly registered as a penalty constraint.
                self.assertNotIn("SurfaceEquality", source)
                self.assertNotIn("MirrorSymmetry", source)
                compile(source, f"<{scheme}-equality>", "exec")

    def test_multiple_equality_templates_are_composed_in_order(self):
        problem = get_template("shapeopt").create_problem("equality-composition")
        config = problem.updater.geometry_config()
        config["equality_constraints"].append({
            "type": "SurfaceEquality",
            "params": {"code": "self.extra_constraint_marker = True"},
        })
        source = generate_source(problem)
        self.assertLess(
            source.index("cp0 ="),
            source.index("self.extra_constraint_marker = True"),
        )
        compile(source, "<equality-composition>", "exec")

    def test_surface_mutations_keep_updater_state_in_surface_order(self):
        problem = _codesign_problem()
        original_outer, original_inner = problem.surfaces()

        copied_outer = problem.clone_surface(original_outer)

        self.assertEqual(problem.surfaces(), [original_outer, copied_outer, original_inner])
        self.assertEqual([surface.flip for surface in problem.surfaces()], [False, True, True])
        self.assertEqual(problem.updater.geometry_config()["if_update"], [False, True, True])
        self.assertEqual(_distance_matrix(problem), [
            [0.0, 2.5, 0.0],
            [2.5, 2.5, 2.5],
            [0.0, 2.5, 2.5],
        ])

        self.assertTrue(problem.move_surface(original_inner, -1))
        self.assertEqual(problem.surfaces(), [original_outer, original_inner, copied_outer])
        self.assertEqual(_distance_matrix(problem), [
            [0.0, 0.0, 2.5],
            [0.0, 2.5, 2.5],
            [2.5, 2.5, 2.5],
        ])

        problem.remove_surface(original_inner)

        self.assertEqual(problem.surfaces(), [original_outer, copied_outer])
        self.assertEqual(problem.updater.geometry_config()["if_update"], [False, True])
        self.assertEqual(_distance_matrix(problem), [[0.0, 2.5], [2.5, 2.5]])

    def test_interface_rename_and_remove_cascade_references(self):
        problem = _codesign_problem()
        pressure = next(
            interface for interface in problem.interfaces()
            if interface.name == "pressure_1"
        )
        problem.steps.step_values[1][pressure.name] = [0.1]
        problem.objective.jacobian_needed = [pressure.name, "other_reference"]

        self.assertTrue(problem.rename_interface(pressure, "pressure_main"))
        self.assertNotIn("pressure_1", problem.steps.step_values[1])
        self.assertEqual(problem.steps.step_values[1]["pressure_main"], [0.1])
        self.assertEqual(problem.objective.jacobian_needed,
                         ["pressure_main", "other_reference"])

        duplicate_name = problem.interfaces()[0].name
        self.assertFalse(problem.rename_interface(pressure, duplicate_name))
        self.assertEqual(pressure.name, "pressure_main")

        problem.remove_interface(pressure)
        self.assertNotIn("pressure_main", [item.name for item in problem.interfaces()])
        self.assertNotIn("pressure_main", problem.steps.step_values[1])
        self.assertEqual(problem.objective.jacobian_needed, ["other_reference"])

    def test_amplitude_interfaces_match_load_step_matrix_columns(self):
        """Only interfaces with values can be selected for Jacobians."""
        for scheme in ("shapeopt", "simp", "codesign"):
            with self.subTest(scheme=scheme):
                problem = get_template(scheme).create_problem("amplitudes")
                expected = [
                    interface.name for interface in problem.interfaces()
                    if INTERFACE_TYPES[interface.interface_type]["num_values"] > 0
                ]
                self.assertEqual(
                    [interface.name for interface in problem.amplitude_interfaces()],
                    expected,
                )

    def test_template_parameter_choices_come_from_problem_model(self):
        codesign = _codesign_problem()
        self.assertEqual(codesign.instance_names(), ["final_model"])
        self.assertEqual(codesign.reference_point_names(), ["RP_head"])
        self.assertEqual(codesign.element_names(), ["C3D4", "C3D6"])

    def test_all_objective_snippets_generate_valid_python(self):
        """Every selectable snippet can be completed into a generated code slot."""
        for scheme in ("shapeopt", "simp", "codesign"):
            template = get_template(scheme)
            for snippet in template.objective_code_snippets():
                with self.subTest(scheme=scheme, snippet=snippet.key):
                    problem = template.create_problem("preset")
                    source = snippet.render() + "return 0\n"
                    problem.objective.set_field("_objective_function", source)
                    problem.objective.set_field("_get_metrics", "return []\n")
                    compile(generate_source(problem), f"<{scheme}-{snippet.key}>",
                            "exec")
