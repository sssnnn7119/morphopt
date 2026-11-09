"""Penalty targets use reference-point DoFs or instance node directions."""

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication, QComboBox

from morphopt.ui.application import ProblemLibrary
from morphopt.ui.application.editing import set_node_field
from morphopt.ui.application.fields import fields_for_node, penalty_targets
from morphopt.ui.application.validation import DefinitionValidation
from morphopt.ui.codegen.generator import render_component_call
from morphopt.ui.model.problem import FEAComponentNode
from morphopt.ui.presentation.labels import display_choice
from morphopt.ui.widgets.editor import PropertyEditor
from morphopt.ui.widgets.definition_actions import DefinitionActions
from morphopt.ui.widgets.definition_manager import DefinitionManagerEditor


@pytest.fixture
def definition():
    problem = ProblemLibrary.create("shapeopt")
    penalty = FEAComponentNode.create("PenaltyDoF", name="lock_1")
    problem.loads.add_component(penalty)
    return problem, penalty


def test_object_options_follow_assembly_category_and_exclude_self(definition):
    problem, penalty = definition
    targets = penalty_targets(problem, penalty)
    assert set(targets.values()) == {"rp", "instance"}
    assert penalty.name not in targets
    assert all(name in targets for name in problem.instance_names())
    assert all(targets[name] == "rp" for name in problem.reference_point_names())
    for category in ("instance", "rp", "load", "constraint", "boundary"):
        penalty.obj_type = category
        assert penalty_targets(problem, penalty) == {
            name: kind for name, kind in targets.items() if kind == category
        }


def test_switching_category_clears_invalid_target_and_resets_dof(definition):
    problem, penalty = definition
    penalty.obj_name = problem.instance_names()[0]
    penalty.s = 15
    assert set_node_field(penalty, "obj_type", "rp", problem)
    assert penalty.obj_name == ""
    assert penalty.s == 0
    rp = problem.reference_point_names()[0]
    assert set_node_field(penalty, "obj_name", rp, problem)
    penalty.s = 4
    assert set_node_field(penalty, "obj_type", "auto", problem)
    assert penalty.obj_name == rp
    assert penalty.s == 4


def test_reference_point_has_six_named_dof_choices_and_roundtrips(definition, tmp_path):
    problem, penalty = definition
    penalty.obj_name = problem.reference_point_names()[0]
    penalty.s = 4
    fields, _, choices = fields_for_node(penalty, problem)
    dof = next(field for field in fields if field.key == "s")
    assert dof.type == "combo"
    assert not dof.editable
    assert dof.choices == tuple(range(6))
    assert "Ry" in display_choice("s", penalty.s)
    assert penalty.obj_name in choices["obj_name"]
    restored = ProblemLibrary.load(ProblemLibrary.save(problem, tmp_path / "penalty.morph"), issues=[])
    loaded = next(load for load in restored.fea_components() if load.name == penalty.name)
    assert loaded.obj_name == penalty.obj_name
    assert loaded.s == 4
    assert "s=4" in render_component_call(loaded)


def test_instance_node_and_direction_share_one_serialized_dof(definition, tmp_path):
    problem, penalty = definition
    penalty.obj_type = "instance"
    penalty.obj_name = problem.instance_names()[0]
    penalty.s = 17
    fields, _, _ = fields_for_node(penalty, problem)
    assert [field.key for field in fields] == ["obj_type", "obj_name", "node_index", "direction"]
    assert penalty.get_field("node_index") == 5
    assert penalty.get_field("direction") == 2
    assert set_node_field(penalty, "node_index", 4, problem)
    assert penalty.s == 14
    assert set_node_field(penalty, "direction", 1, problem)
    assert penalty.s == 13
    assert not set_node_field(penalty, "node_index", -1, problem)
    assert not set_node_field(penalty, "direction", 3, problem)
    assert penalty.s == 13
    params = penalty.to_dict()["params"]
    assert "node_index" not in params and "direction" not in params
    restored = ProblemLibrary.load(ProblemLibrary.save(problem, tmp_path / "instance.morph"), issues=[])
    loaded = next(load for load in restored.fea_components() if load.name == penalty.name)
    assert (loaded.node_index, loaded.direction) == (4, 1)
    assert "s=13" in render_component_call(loaded)


def test_instance_editor_separates_node_index_from_direction(definition):
    app = QApplication.instance() or QApplication([])
    problem, penalty = definition
    penalty.obj_type = "instance"
    penalty.obj_name = problem.instance_names()[0]
    editor = PropertyEditor()
    editor.edit_node(penalty, completion_problem=problem)
    assert "s" not in editor._controls
    node = editor._controls["node_index"]
    node.setText("5")
    node.editingFinished.emit()
    direction = editor._controls["direction"]
    assert not direction.isEditable()
    assert [direction.itemData(i) for i in range(direction.count())] == [0, 1, 2]
    assert all(axis in direction.itemText(i) for i, axis in enumerate("XYZ"))
    direction.setCurrentIndex(direction.findData(2))
    assert penalty.s == 17
    editor.close()
    app.processEvents()


def test_selected_node_direction_is_the_only_penalized_mesh_coordinate(definition):
    from types import SimpleNamespace

    import torch
    import torchfea
    from torchfea.model.loads.penalty_dof import Penalty_DoF

    problem, penalty = definition
    penalty.obj_name = problem.instance_names()[0]
    penalty.obj_type = "instance"
    penalty.set_field("node_index", 5)
    penalty.set_field("direction", 2)
    assembly = torchfea.Assembly()
    assembly._instances[penalty.obj_name] = SimpleNamespace(_RGC_index=0)
    assembly._RGC_size = [(8, 3), (0,)]
    assembly._RGC_list_indexStart = [0, 24, 24]
    load = Penalty_DoF(penalty.obj_name, penalty.s, target=3.0, k=2.0, obj_type="instance")
    load.set_RGC_index(1)
    load.initialize(assembly)
    coordinates = torch.zeros((8, 3), dtype=torch.float64, requires_grad=True)
    gradient = torch.autograd.grad(-load.get_potential_energy([coordinates]), coordinates)[0]
    assert gradient.nonzero().tolist() == [[5, 2]]
    assert float(gradient[5, 2]) == pytest.approx(-6.0)


def test_property_editor_uses_noneditable_object_and_dof_selectors(definition):
    app = QApplication.instance() or QApplication([])
    problem, penalty = definition
    penalty.obj_type = "rp"
    editor = PropertyEditor()
    editor.edit_node(penalty, completion_problem=problem)
    objects = editor._controls["obj_name"]
    assert isinstance(objects, QComboBox)
    assert not objects.isEditable()
    assert "Select" in objects.currentText()
    rp = problem.reference_point_names()[0]
    objects.setCurrentIndex(objects.findData(rp))
    assert penalty.obj_name == rp
    editor.edit_node(penalty, completion_problem=problem)
    dof = editor._controls["s"]
    assert isinstance(dof, QComboBox)
    assert not dof.isEditable()
    dof.setCurrentIndex(dof.findData(4))
    assert penalty.s == 4
    editor.close()
    app.processEvents()


def test_validation_checks_selected_category_and_reference_point_dof(definition):
    problem, penalty = definition
    penalty.obj_type = "rp"
    penalty.obj_name = problem.reference_point_names()[0]
    valid = DefinitionValidation(problem)
    valid.node(penalty)
    assert id(penalty) not in valid.errors
    penalty.s = 7
    invalid_dof = DefinitionValidation(problem)
    invalid_dof.node(penalty)
    assert id(penalty) in invalid_dof.errors
    penalty.s = 0
    penalty.obj_type = "instance"
    invalid_target = DefinitionValidation(problem)
    invalid_target.node(penalty)
    assert id(penalty) in invalid_target.errors


@pytest.mark.parametrize("font_scale", [1.0, 1.6])
def test_embedded_form_stays_visible_after_reference_point_selection(definition, font_scale):
    app = QApplication.instance() or QApplication([])
    problem, penalty = definition
    actions = DefinitionActions()
    actions.set_problem(problem)
    manager = DefinitionManagerEditor("loads", actions)
    manager.edit_node(problem.loads, problem, penalty)
    manager.changed.connect(lambda _node: manager.edit_node(problem.loads, problem, penalty))
    manager.resize(650, 400)
    manager.show()
    app.processEvents()
    try:
        editor = manager._node_editors[penalty][0]
        # Switching targets rebuilds reference DoFs or instance node directions.
        for target in (
            problem.reference_point_names()[0],
            problem.instance_names()[0],
            problem.reference_point_names()[0],
        ):
            objects = editor._controls["obj_name"]
            objects.setCurrentIndex(objects.findData(target))
            app.processEvents()
            app.processEvents()
            assert penalty.obj_name == target
            for control in (editor._name_edit, *editor._controls.values()):
                bounds = QRect(control.mapTo(editor, QPoint()), control.size())
                assert editor.contentsRect().contains(bounds)
                assert control.height() >= control.minimumSizeHint().height()
        # Font changes must update the same shared layout without a cached height.
        font = manager.font()
        font.setPointSizeF(font.pointSizeF() * font_scale)
        manager.setFont(font)
        app.processEvents()
        app.processEvents()
        for control in editor._controls.values():
            bounds = QRect(control.mapTo(editor, QPoint()), control.size())
            assert editor.contentsRect().contains(bounds)
        scroll = manager._scroll
        assert scroll.verticalScrollBar().maximum() > 0
        scroll.ensureWidgetVisible(editor._controls["s"])
        app.processEvents()
        control = editor._controls["s"]
        bounds = QRect(control.mapTo(scroll.viewport(), QPoint()), control.size())
        assert scroll.viewport().rect().contains(bounds)
    finally:
        manager.close()
        manager.deleteLater()
        app.processEvents()
