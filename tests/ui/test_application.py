from __future__ import annotations

import ast
from pathlib import Path

from morphopt.ui.application import (
    EditorKind,
    OptimizationRunSession,
    ProblemLibrary,
    ProblemSession,
    ResultSession,
    RunMode,
    route_editor,
)
from morphopt.ui import launcher
from morphopt.ui.model.problem import InstanceNode
from morphopt.ui.schemes.base import get_template
from morphopt.ui.application.fields import fields_for_node


def test_domain_packages_expose_only_concrete_components() -> None:
    import morphopt.shapeopt as shapeopt
    import morphopt.simp as simp

    assert shapeopt.__all__ == [
        "BoundaryPart", "UpdaterBoundaryPart", "BaseSurfaceConstraints",
        "SurfaceRelationConstraint", "BspSurfaceRelationConstraint",
        "CPGEOSurfaceRelationConstraint",
    ]
    assert simp.__all__ == ["SIMP_BSPFieldMaterials", "UpdaterSIMPMaterial"]
    assert not hasattr(shapeopt, "Params")
    assert not hasattr(shapeopt, "ObjectiveFunction")
    assert not hasattr(simp, "Solver")
    assert not hasattr(simp, "SIMPSolver")


def test_every_template_generates_compilable_source() -> None:
    for template in ProblemLibrary.templates():
        problem = ProblemLibrary.create(template.scheme)
        source = ProblemSession(problem).source()
        compile(source, f"<{template.scheme}>", "exec")


def test_templates_are_starters_and_generated_models_use_core_classes() -> None:
    for template in ProblemLibrary.templates():
        assert set(template.available_material_types()) == {
            "HomogeneousMaterial",
            "SIMP_BSPFieldMaterials",
        }
        source = ProblemSession(ProblemLibrary.create(template.scheme)).source()
        assert "class ObjectiveFunction(morphopt.ObjectiveFunction):" in source
        assert "class Params(morphopt.Params):" in source
        assert "class Solver(morphopt.Solver):" in source
        assert "class Updater(morphopt.Updaters):" in source


def test_shape_starter_can_combine_a_simp_material_and_updater() -> None:
    problem = ProblemLibrary.create("shapeopt")
    part = problem.parts()[0]
    density = get_template(problem.scheme).make_material("SIMP_BSPFieldMaterials")
    density.name = "density"
    problem.add_material(density)
    assert density.part is None
    assert density.part_name == ""
    assert problem.set_material_part(density, part)
    problem.add_material_updater(density)

    source = ProblemSession(problem).source()

    assert "morphopt.SIMP_BSPFieldMaterials" in source
    assert "morphopt.UpdaterSIMPMaterial" in source
    assert "morphopt.simp." not in source
    assert "morphopt.shapeopt." not in source
    compile(source, "<shape-plus-simp>", "exec")


def test_simp_material_has_no_internal_mapping_code_slot() -> None:
    problem = ProblemLibrary.create("simp")
    material = problem.material_nodes()[0]

    _fields, code_slots, _choices = fields_for_node(material, problem)

    assert "_map_bsp_designfield" not in code_slots
    assert "_map_bsp_designfield" not in material.to_dict()["params"]


def test_problem_session_updates_definition_metadata() -> None:
    session = ProblemSession(ProblemLibrary.create("shapeopt"))

    assert session.set_label("renamed")
    assert session.problem.label == "renamed"
    assert session.problem.root.name == "renamed"
    assert session.set_result_folder("results/new")
    assert session.set_device("cpu") is False


def test_renaming_a_part_updates_only_its_default_instance() -> None:
    problem = ProblemLibrary.create("shapeopt")
    part = problem.parts()[0]
    default = part.instances[0]
    custom = problem.add_instance(part, InstanceNode(name="body_observer"))
    pressure = next(
        component
        for component in problem.fea_components()
        if component.type == "Pressure"
    )
    assert problem.set_component_reference(pressure, "instance_name", custom)

    assert problem.rename_definition(part, "shape_body")

    assert part.name == "shape_body"
    assert part.assembly_name == "shape_body"
    assert default.name == "shape_body-1"
    assert custom.name == "body_observer"
    assert pressure.instance is custom
    assert all(
        component.instance in {default, custom}
        for component in problem.fea_components()
        if component.instance is not None
    )
    assert problem.material_nodes()[0].part_name == "shape_body"
    assert problem.updater is not None
    assert problem.config_part_node(problem.updater.geometry[0]) is part


def test_renaming_an_assembly_part_updates_its_default_instance_and_loads() -> None:
    problem = ProblemLibrary.create("shapeopt")
    part = problem.parts()[0]
    default = part.instances[0]

    assert problem.rename_part(part, "flexible_body")

    assert part.name == "body"
    assert part.assembly_name == "flexible_body"
    assert default.name == "flexible_body-1"
    assert problem.material_nodes()[0].part_name == "flexible_body"
    assert all(
        component.instance is default
        for component in problem.fea_components()
        if component.instance is not None
    )
    assert problem.updater is not None
    assert problem.config_part_node(problem.updater.geometry[0]) is part


def test_renaming_a_material_definition_retargets_its_material_updater() -> None:
    problem = ProblemLibrary.create("simp")
    material = problem.material_nodes()[0]

    assert problem.rename_definition(material, "density_field")

    assert material.name == "density_field"
    assert problem.updater is not None
    assert problem.config_material_node(problem.updater.materials[0]) is material


def test_renaming_a_torchfea_part_definition_preserves_archive_part_and_instances() -> None:
    problem = ProblemLibrary.create("simp")
    part = problem.parts()[0]
    physical_part_name = part.assembly_name
    instance_names = part.instance_names

    assert problem.rename_definition(part, "beam_geometry")

    assert part.name == "beam_geometry"
    assert part.assembly_name == physical_part_name
    assert part.instance_names == instance_names
    compile(ProblemSession(problem).source(), "<renamed-torchfea>", "exec")


def test_cross_node_links_are_objects_and_survive_renames() -> None:
    problem = ProblemLibrary.create("shapeopt")
    pressure = next(
        component
        for component in problem.fea_components()
        if component.type == "Pressure"
    )
    reference_point = next(
        component
        for component in problem.fea_components()
        if component.type == "ReferencePoint"
    )
    couple = next(
        component
        for component in problem.fea_components()
        if component.type == "Couple"
    )

    assert pressure.instance is problem.parts()[0].instances[0]
    assert couple.reference_point is reference_point
    assert problem.steps is not None
    assert pressure in problem.steps.step_values[0]
    assert problem.updater is not None
    assert "part_name" not in problem.updater.geometry[0]
    assert problem.config_part_node(problem.updater.geometry[0]) is problem.parts()[0]
    problem.set_jacobian_components([pressure])
    assert problem.objective is not None
    assert problem.objective.jacobian_needed == [pressure]

    assert problem.rename_definition(pressure, "actuation_pressure")
    assert problem.rename_definition(reference_point, "actuation_rp")

    assert pressure in problem.steps.step_values[0]
    assert problem.objective.jacobian_needed == [pressure]
    assert couple.reference_point is reference_point
    persisted = problem.to_dict()
    steps = persisted["root"]["children"][2]["params"]["step_values"]
    assert "actuation_pressure" in steps[0]
    assert persisted["root"]["children"][4]["params"]["jacobian_needed"] == [
        "actuation_pressure"
    ]


def test_problem_library_round_trip(tmp_path: Path) -> None:
    original = ProblemLibrary.create("shapeopt", label="round_trip")
    path = ProblemLibrary.save(original, tmp_path / "problem")
    restored = ProblemLibrary.load(path)

    assert restored.to_dict() == original.to_dict()


def test_template_instances_do_not_share_mutable_updater_configuration() -> None:
    first = ProblemLibrary.create("shapeopt")
    second = ProblemLibrary.create("shapeopt")

    assert first.updater is not None
    assert second.updater is not None
    first.updater.geometry[0]["max_step_iter"] = 123

    assert second.updater.geometry[0]["max_step_iter"] == 50


def test_editor_routes_are_independent_from_widgets() -> None:
    problem = ProblemLibrary.create("shapeopt")

    assert route_editor(problem.solver).kind is EditorKind.SOLVER
    assert route_editor(problem.steps).kind is EditorKind.STEPS
    assert route_editor(problem.objective).kind is EditorKind.OBJECTIVE
    assert route_editor(None).kind is EditorKind.PROPERTIES


def test_result_session_discovers_deformation_cases(tmp_path: Path) -> None:
    deformation = tmp_path / "log" / "deformation"
    deformation.mkdir(parents=True)
    for name in (
        "task_2_iter_1.stl",
        "task_0_iter_3.stl",
        "task_2_iter_4.stl",
        "unrelated.stl",
    ):
        (deformation / name).touch()

    session = ResultSession()
    session.folder = str(tmp_path)

    assert session.deformation_cases() == (0, 2)


def test_run_session_owns_fresh_process_state(
    tmp_path: Path, monkeypatch
) -> None:
    class Process:
        stdout = None

        @staticmethod
        def poll():
            return None

    process = Process()
    result = tmp_path / "results" / "shapeopt_untitled_T1"
    result.mkdir(parents=True)
    problem = ProblemLibrary.create("shapeopt")

    monkeypatch.setattr(launcher, "run_job", lambda _problem: ("job.py", process))
    monkeypatch.setattr(launcher, "run_root_for", lambda _problem: str(result.parent))
    monkeypatch.setattr(
        launcher, "latest_result_dir", lambda _root, _label: str(result)
    )

    session = OptimizationRunSession()
    assert session.start_definition(problem) is process
    assert session.active
    assert session.mode is RunMode.FRESH
    assert session.discover_folder() == str(result.resolve())


def test_lower_ui_layers_do_not_import_qt_or_widgets() -> None:
    ui_root = Path(__file__).resolve().parents[2] / "src" / "morphopt" / "ui"
    files = [
        *sorted((ui_root / "application").glob("*.py")),
        *sorted((ui_root / "model").glob("*.py")),
    ]
    forbidden = ("PySide6", "morphopt.ui.widgets")

    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
        assert not any(
            module.startswith(prefix)
            for module in modules
            for prefix in forbidden
        ), path
