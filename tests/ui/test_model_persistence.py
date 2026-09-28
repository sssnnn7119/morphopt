"""Current model format is explicit and does not migrate retired fields."""

import pytest

from morphopt.ui.application import ProblemLibrary, ProblemSession
from morphopt.ui.model.problem import Node, ProblemDefinition


def test_unknown_node_kind_is_rejected():
    with pytest.raises(ValueError, match="Unknown model node kind"):
        Node.from_dict({"kind": "old_geometry"})


def test_unknown_node_fields_are_rejected():
    with pytest.raises(ValueError, match="Unknown fields"):
        Node.from_dict({"kind": "part_interface", "params": {"shell_thickness": 2}})


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
