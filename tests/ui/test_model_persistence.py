"""Current model format is explicit and does not migrate retired fields."""

import pytest

from morphopt.ui.application import ProblemLibrary, ProblemSession
from morphopt.ui.model.problem import Node, ProblemDefinition


def test_unknown_node_kind_is_rejected():
    with pytest.raises(ValueError, match="Unknown model node kind"):
        Node.from_dict({"kind": "old_geometry"})


def test_unknown_node_fields_are_rejected():
    with pytest.raises(ValueError, match="Unknown fields"):
        Node.from_dict({"kind": "part", "params": {"type": "CADPart", "retired_field": 2}})


def test_retired_updater_code_is_rejected():
    with pytest.raises(ValueError, match="Raw updater code"):
        Node.from_dict({"kind": "updater", "params": {"materials": [{"code": "pass"}]}})


def test_unknown_format_version_is_rejected():
    data = ProblemLibrary.create("shapeopt").to_dict()
    data["version"] = 1
    with pytest.raises(ValueError, match="Unsupported .morph version"):
        ProblemDefinition.from_dict(data)


def test_definition_requires_helper_groups():
    data = ProblemLibrary.create("shapeopt").to_dict()
    del data["helper_variables"]
    with pytest.raises(KeyError, match="helper_variables"):
        ProblemDefinition.from_dict(data)


def test_numeric_text_remains_text_in_generated_source():
    problem = ProblemLibrary.create("shapeopt")
    problem.label = "123"
    assert "opt_label='123'" in ProblemSession(problem).source()


def test_unknown_updater_item_is_not_silently_dropped():
    problem = ProblemLibrary.create("shapeopt")
    problem.updater.geometry[0]["constraints"].append({"type": "RetiredConstraint"})
    with pytest.raises(ValueError, match="Unknown updater constraints type"):
        ProblemSession(problem).source()


def load_definition_file(tmp_path, data):
    import json

    path = tmp_path / "definition.morph"
    path.write_text(json.dumps(data), encoding="utf-8")
    issues = []
    return ProblemLibrary.load(path, issues=issues), issues


@pytest.mark.parametrize("item_type", ["BspRelation", "CPGEORelation"])
def test_file_import_preserves_related_surface_index(tmp_path, item_type):
    data = ProblemLibrary.create("shapeopt").to_dict()
    updater = next(node for node in data["root"]["children"] if node["kind"] == "updater")
    relation = {
        "type": item_type,
        "surface_index": 1,
        "related_surface_index": 0,
        "params": {"pose": [0.0, 0.0, 0.0, 0.0, 0.0, 2.0943951023931953]},
    }
    updater["params"]["geometry"][0]["symmetry_constraints"] = [relation]
    problem, issues = load_definition_file(tmp_path, data)
    assert problem.updater.geometry[0]["symmetry_constraints"] == [relation]
    assert not issues
    saved = ProblemLibrary.save(problem, tmp_path / "roundtrip.morph")
    assert ProblemLibrary.load(saved, issues=[]).updater.geometry[0]["symmetry_constraints"] == [relation]


def test_file_import_defaults_missing_fields_and_ignores_unknown_content(tmp_path):
    data = ProblemLibrary.create("shapeopt").to_dict()
    data["version"] = 100
    data["future_setting"] = {"anything": 123}
    for key in ("helper_code", "helper_variables", "helper_functions"):
        del data[key]
    geometry = next(node for node in data["root"]["children"] if node["kind"] == "geometry")
    part = geometry["children"][0]
    part["params"]["fea_seed_size"] = 2.75
    part["params"]["retired_field"] = True
    geometry["children"].append({"kind": "future_geometry", "name": "unsupported"})
    geometry["children"].append({"kind": "part", "params": {"type": "FuturePart"}})
    problem, issues = load_definition_file(tmp_path, data)
    assert problem.parts()[0].fea_seed_size == 2.75
    assert len(problem.parts()) == 1
    assert problem.helper_code == ""
    assert not problem.helper_variables
    assert not problem.helper_functions
    assert {"ui.import.version", "ui.import.ignored_fields", "ui.import.default_fields",
            "ui.import.skipped"} <= {issue.key for issue in issues}
    saved = ProblemLibrary.save(problem, tmp_path / "normalized.morph")
    restored_issues = []
    restored = ProblemLibrary.load(saved, issues=restored_issues)
    assert not restored_issues
    assert restored.to_dict() == problem.to_dict()


def test_file_import_projects_nested_updater_terms_and_strategy_parameters(tmp_path):
    data = ProblemLibrary.create("shapeopt").to_dict()
    updater = next(node for node in data["root"]["children"] if node["kind"] == "updater")
    config = updater["params"]["geometry"][0]
    config["code"] = "retired raw updater body"
    config["constraints"] = [
        {"type": "Fairness", "params": {"retired_parameter": 100}},
        {"type": "FuturePenalty", "params": {"x": 10}},
    ]
    config["constraint_weight_strategy"] = {
        "type": "AdaptiveShapeWeights", "params": {"initial_tolerance": 0.1, "old_schedule": 50},
        "unsupported_option": True,
    }
    del config["max_step_length"]
    problem, issues = load_definition_file(tmp_path, data)
    restored = problem.updater.geometry[0]
    assert "code" not in restored
    assert restored["constraints"] == [{"type": "Fairness", "params": {"max_curvature": 1.0}}]
    policy = restored["constraint_weight_strategy"]
    assert policy["params"]["initial_tolerance"] == 0.1
    assert policy["params"]["violation_tolerance"] == 0.1
    assert "old_schedule" not in policy["params"]
    assert restored["max_step_length"] > 0
    assert issues


def test_file_import_uses_default_policy_for_an_unknown_strategy(tmp_path):
    data = ProblemLibrary.create("shapeopt").to_dict()
    updater = next(node for node in data["root"]["children"] if node["kind"] == "updater")
    updater["params"]["geometry"][0]["constraint_weight_strategy"] = {"type": "FutureStrategy"}
    problem, issues = load_definition_file(tmp_path, data)
    assert problem.updater.geometry[0]["constraint_weight_strategy"] == {
        "type": "ConstantConstraintWeights", "params": {"value": 1.0},
    }
    assert any("FutureStrategy" in str(issue) for issue in issues)


def test_file_import_preserves_custom_updater_terms(tmp_path):
    data = ProblemLibrary.create("shapeopt").to_dict()
    updater = next(node for node in data["root"]["children"] if node["kind"] == "updater")
    updater["params"]["geometry"][0]["constraints"] = [
        {"type": "Custom", "custom_class": "MyPenalty", "params": {}},
    ]
    problem, _ = load_definition_file(tmp_path, data)
    assert problem.updater.geometry[0]["constraints"][0]["custom_class"] == "MyPenalty"


def test_file_import_restores_missing_sections_and_keeps_first_duplicate(tmp_path):
    data = ProblemLibrary.create_blank(label="partial").to_dict()
    data["root"]["children"] = [
        {"kind": "geometry", "name": "first", "params": {}, "children": []},
        {"kind": "geometry", "name": "second", "params": {}, "children": []},
    ]
    problem, issues = load_definition_file(tmp_path, data)
    assert problem.geometry.name == "first"
    assert problem.solver.process_devices == ["cpu"]
    assert set(problem.steps.step_values) == {"load_case_1"}
    assert issues


def test_file_import_filters_objective_terms_and_supplies_term_defaults(tmp_path):
    data = ProblemLibrary.create("shapeopt").to_dict()
    objective = next(node for node in data["root"]["children"] if node["kind"] == "objective")
    objective["params"]["objective_terms"] = [
        {"type": "displacement", "reference_point_name": "RP_1", "component": "ry",
         "step_name": "load_case_1", "future_option": 9},
        {"type": "FutureObjective"},
    ]
    problem, issues = load_definition_file(tmp_path, data)
    assert len(problem.objective.objective_terms) == 1
    term = problem.objective.objective_terms[0]
    assert term["weight"] == 1.0
    assert term["direction"] == "target"
    assert "future_option" not in term
    assert issues


def test_examples_are_current_and_match_their_standard_scripts():
    import ast
    from pathlib import Path

    from morphopt.ui.codegen.assets import collect_python_assets
    from morphopt.ui.codegen.generator import generate_source

    examples = Path(__file__).resolve().parents[2] / "examples"
    definitions = sorted(examples.glob("*/*.morph"))
    assert len(definitions) == 6
    for path in definitions:
        issues = []
        problem = ProblemLibrary.load(path, issues=issues)
        assert not issues, (path, issues)
        paths, assets = collect_python_assets(problem)
        mapped = {key: "assets/" + Path(value).name for key, value in paths.items()}
        expected = generate_source(problem, asset_paths=mapped)
        actual = path.with_suffix(".py").read_text()
        assert ast.dump(ast.parse(actual)) == ast.dump(ast.parse(expected)), path
        namespace = {"__name__": f"example_{path.stem}", "__file__": str(path.with_suffix(".py"))}
        exec(compile(actual, str(path), "exec"), namespace)
        assert "ThisController" in namespace
        for asset in assets.values():
            assert (path.parent / "assets" / asset.name).is_file()


def test_unreadable_json_is_still_an_import_error(tmp_path):
    import json

    path = tmp_path / "broken.morph"
    path.write_text("{invalid json")
    with pytest.raises(json.JSONDecodeError):
        ProblemLibrary.load(path)


def test_file_import_discards_unknown_configuration_class_bindings(tmp_path):
    data = ProblemLibrary.create("shapeopt").to_dict()
    data["class_bindings"] = {"ThisController.FutureModule": "FutureClass"}
    problem, issues = load_definition_file(tmp_path, data)
    assert not problem.class_bindings
    assert any("ThisController.FutureModule" in str(issue) for issue in issues)
    compile(ProblemSession(problem).source(), "<imported>", "exec")


def test_file_import_skips_unreadable_entries_without_losing_known_nodes(tmp_path):
    data = ProblemLibrary.create("shapeopt").to_dict()
    data["root"]["children"].append(42)
    geometry = next(node for node in data["root"]["children"] if isinstance(node, dict) and node["kind"] == "geometry")
    geometry["children"].extend([None, {"kind": "part", "params": {"type": ["invalid"]}}])
    problem, issues = load_definition_file(tmp_path, data)
    assert len(problem.parts()) == 1
    assert any(issue.key == "ui.import.skipped" for issue in issues)


def test_file_import_defaults_a_missing_objective_type(tmp_path):
    data = ProblemLibrary.create_blank().to_dict()
    objective = next(node for node in data["root"]["children"] if node["kind"] == "objective")
    objective["params"]["objective_terms"] = [{"reference_point_name": "tip", "component": "ux"}]
    problem, issues = load_definition_file(tmp_path, data)
    term = problem.objective.objective_terms[0]
    assert term["type"] == "displacement"
    assert term["weight"] == 1.0
    assert issues
