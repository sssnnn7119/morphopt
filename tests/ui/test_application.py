from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

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
from morphopt.ui.application.runs import RunSourceKind


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
    config = problem.add_material_updater(density)
    volume = next(item for item in config["constraints"] if item["type"] == "VolFrac")
    volume["params"]["elementname"] = "C3D4"

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


def test_renaming_a_part_preserves_all_instance_names() -> None:
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
    assert default.name == "body-1"
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


def test_part_rename_entry_point_preserves_instance_names_and_loads() -> None:
    problem = ProblemLibrary.create("shapeopt")
    part = problem.parts()[0]
    default = part.instances[0]

    assert problem.rename_part(part, "flexible_body")

    assert part.name == "flexible_body"
    assert part.assembly_name == "flexible_body"
    assert default.name == "body-1"
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
    case_name = next(iter(problem.steps.step_values))
    assert pressure in problem.steps.step_values[case_name]
    assert problem.updater is not None
    assert "part_name" not in problem.updater.geometry[0]
    assert problem.config_part_node(problem.updater.geometry[0]) is problem.parts()[0]
    problem.set_jacobian_components([pressure])
    assert problem.objective is not None
    assert problem.objective.jacobian_needed == [pressure]

    assert problem.rename_definition(pressure, "actuation_pressure")
    assert problem.rename_definition(reference_point, "actuation_rp")

    assert pressure in problem.steps.step_values[case_name]
    assert problem.objective.jacobian_needed == [pressure]
    assert couple.reference_point is reference_point
    persisted = problem.to_dict()
    steps = persisted["root"]["children"][2]["params"]["step_values"]
    assert "actuation_pressure" in steps[case_name]
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


def test_result_session_reads_named_cases_in_recorded_order(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    ProblemLibrary.export_python(
        ProblemLibrary.create_blank(), scripts / "MAIN_SCRIPT_FOR_RESTART.py"
    )
    folder = tmp_path / "log" / "femodel&results"
    folder.mkdir(parents=True)
    (folder / "load_cases.json").write_text(json.dumps(["actuation", "baseline"]))
    session = ResultSession()
    assert session.bind(str(tmp_path))
    assert session.deformation_cases() == ("actuation", "baseline")


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


@pytest.mark.parametrize('saved', ['no_folder', 'no_history', 'no_restart_script'])
def test_stopping_without_a_saved_restart_does_not_enable_continuation(tmp_path, monkeypatch, saved):
    session = OptimizationRunSession()
    session.process = object()
    if saved != 'no_folder':
        session.folder = str(tmp_path)
        if saved == 'no_history':
            scripts = tmp_path / 'scripts'
            scripts.mkdir()
            (scripts / 'MAIN_SCRIPT_FOR_RESTART.py').touch()
        else:
            log = tmp_path / 'log'
            log.mkdir()
            (log / 'history_record.csv').write_text('iteration,objective\n1,1.0\n')
    stopped = []
    monkeypatch.setattr(launcher, 'stop_job', stopped.append)
    process = session.process
    session.stop()
    assert stopped == [process]
    assert not session.active
    assert session.source is None
    session.stop()
    assert stopped == [process]


def test_stop_discovers_a_result_created_during_shutdown(tmp_path, monkeypatch):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    (scripts / 'MAIN_SCRIPT_FOR_RESTART.py').touch()
    log = tmp_path / 'log'
    log.mkdir()
    (log / 'history_record.csv').write_text('iteration,objective\n1,1.0\n')
    session = OptimizationRunSession()
    session.process = object()
    session.mode = RunMode.FRESH
    # Before shutdown the worker has not made its result visible yet.
    candidates = iter([None, str(tmp_path)])
    monkeypatch.setattr(launcher, 'latest_result_dir', lambda *_args: next(candidates))
    monkeypatch.setattr(launcher, 'stop_job', lambda _process: None)
    session.stop()
    assert session.folder == str(tmp_path)
    assert session.last_iteration == 1
    assert session.source.kind is RunSourceKind.CONTINUE
    assert session.source.path == str(tmp_path)


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
