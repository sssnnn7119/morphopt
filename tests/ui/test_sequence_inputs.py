"""Structured lists and named case parameters preserve their kernel ordering."""

import pytest
from PySide6.QtWidgets import QApplication

from morphopt.ui.application import ProblemLibrary, ProblemSession
from morphopt.ui.application.editing import LoadCaseSession
from morphopt.ui.application.validation import DefinitionValidation
from morphopt.ui.i18n import LocalizationManager, tr
from morphopt.ui.model import registry as R
from morphopt.ui.model.fields import field_defaults
from morphopt.ui.model.problem import FEAComponentNode, HelperVariableNode, InstanceNode, LoadCaseNode
from morphopt.ui.widgets.load_cases import LoadCaseEditor
from morphopt.ui.widgets.param_form import ParamForm
from morphopt.ui.widgets.sequence_input import SequenceInput


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


VECTOR_FIELDS = [
    field
    for catalog in (R.SURFACE_TYPES, R.LOAD_TYPES, R.MATERIAL_TYPES, R.SURFACE_SYMMETRY_CONSTRAINTS)
    for node in catalog.values()
    for field in node.fields
    if field.type.startswith("vec") and not field.hidden
] + list(InstanceNode.fields)


@pytest.mark.parametrize("field", VECTOR_FIELDS, ids=lambda f: f"{f.key}-{f.type}")
def test_every_vector_field_uses_individual_inputs(app, field):
    form = ParamForm(field_defaults([field]), [field])
    control = form.controls[field.key]
    assert isinstance(control, SequenceInput)
    assert len(control.edits) == len(field.new_default())
    assert all(edit.accessibleName() for edit in control.edits)
    if field.components:
        assert [edit.accessibleName() for edit in control.edits] == [tr(key) for key in field.components]
    form.close()


def test_vector_edits_preserve_order_constants_and_external_refresh(app):
    field = R.SURFACE_SYMMETRY_CONSTRAINTS["BspRelation"].fields[0]
    params = {"pose": [1, 2, 3, 4, 5, 6]}
    form = ParamForm(params, [field], helper_names=["offset"])
    control = form.controls["pose"]
    changes = []
    form.changed.connect(changes.append)
    control.edits[2].setText("offset")
    control.edits[2].editingFinished.emit()
    assert params["pose"] == [1.0, 2.0, "offset", 4.0, 5.0, 6.0]
    assert changes == ["pose"]
    params["pose"] = [6, 5, 4, 3, 2, 1]
    form.refresh_values()
    assert control.value() == [6, 5, 4, 3, 2, 1]
    assert changes == ["pose"]
    form.close()


def test_whole_vector_constant_remains_a_reference_until_explicitly_changed(app):
    field = InstanceNode.fields[0]
    params = {field.key: "ORIGIN"}
    form = ParamForm(params, [field], helper_names=["ORIGIN"])
    control = form.controls[field.key]
    assert control.value() == "ORIGIN"
    assert not control.body.isEnabled()
    assert params[field.key] == "ORIGIN"
    control.reference.setCurrentIndex(0)
    assert params[field.key] == [0.0, 0.0, 0.0]
    assert control.body.isEnabled()
    form.close()


def test_variable_length_material_and_face_lists_support_add_edit_remove(app):
    for field, expected in (
        (next(f for f in R.MATERIAL_TYPES["HomogeneousMaterial"].fields if f.key == "alpha"), 3.5),
        (next(f for f in R.SURFACE_TYPES["brep_surface"].fields if f.key == "design_faces"), "face_7"),
    ):
        params = {field.key: []}
        form = ParamForm(params, [field])
        control = form.controls[field.key]
        control.add_button.click()
        control.edits[0].setText(str(expected))
        control.edits[0].editingFinished.emit()
        control.add_button.click()
        assert params[field.key][0] == expected
        control._remove(1)
        assert params[field.key] == [expected]
        control._remove(0)
        assert params[field.key] == []
        form.close()


@pytest.fixture
def case_problem():
    problem = ProblemLibrary.create("shapeopt")
    ground = FEAComponentNode.create("SpringToGround", name="ground", rp_name="RP_1")
    between = FEAComponentNode.create("SpringBetweenRPs", name="link", rp_name1="RP_1", rp_name2="RP_1")
    for load in (ground, between):
        problem.loads.add_component(load)
    problem.steps.step_values = {
        "rest": {ground: [2.0, 0.5, 1.0, 2.0, 3.0], between: [4.0, 5.0]},
        "active": {ground: [8.0, 1.5, 11.0, 12.0, 13.0], between: [14.0, 15.0]},
    }
    for term in [*problem.objective.objective_terms, *problem.objective.metrics_terms]:
        if "step_name" in term:
            term["step_name"] = "rest"
    return problem, ground, between


def case_editor(problem):
    from morphopt.ui.widgets.definition_actions import DefinitionActions

    actions = DefinitionActions()
    actions.set_problem(problem)
    editor = LoadCaseEditor(actions)
    actions.selectionRequested.connect(lambda node: editor.edit_node(
        problem.steps, problem, node if isinstance(node, LoadCaseNode) else None,
    ))
    editor.edit_node(problem.steps, problem)
    return editor, actions


def test_case_interfaces_edit_named_values_and_reuse_common_cards(app, case_problem, tmp_path):
    problem, ground, between = case_problem
    editor, actions = case_editor(problem)
    rest = LoadCaseNode(problem, "rest")
    active = LoadCaseNode(problem, "active")
    ProblemSession(problem).synchronize()
    assert problem.steps.step_values["rest"] is rest.values
    assert LoadCaseNode(problem, "rest") == rest
    assert len(editor._item_groups) == 2
    properties = editor._node_editors[rest][0]
    fields = properties._controls
    assert f"{ground.name}.stiffness" in fields
    fields[f"{ground.name}.anchor_y"].setText("7.5")
    fields[f"{ground.name}.anchor_y"].editingFinished.emit()
    assert problem.steps.step_values["rest"][ground] == [2, 0.5, 1, 7.5, 3]
    assert problem.steps.step_values["active"][ground] == [8, 1.5, 11, 12, 13]
    assert problem.steps.step_values["rest"][between] == [4, 5]
    editor.edit_node(problem.steps, problem, active)
    assert editor._focus == active
    assert editor._item_groups[active].property("collectionSelected")
    actions.move_load_case(active, -1)
    assert list(problem.steps.step_values) == ["active", "rest"]
    properties = editor._node_editors[active][0]
    properties._name_edit.setText("pressurized")
    properties._name_edit.editingFinished.emit()
    assert list(problem.steps.step_values) == ["pressurized", "rest"]
    assert active.name == "pressurized"
    path = ProblemLibrary.save(problem, tmp_path / "cases.morph")
    restored = ProblemLibrary.load(path, issues=[])
    restored_ground = next(load for load in restored.amplitude_components() if load.name == ground.name)
    assert restored.steps.step_values["rest"][restored_ground] == [2, 0.5, 1, 7.5, 3]
    assert "SpringToGround" in ProblemSession(restored).source()
    editor.close()


def test_case_interface_actions_can_delete_the_last_case(app, case_problem):
    problem, _, _ = case_problem
    problem.objective.objective_terms = []
    problem.objective.metrics_terms = []
    problem.steps.step_values = {}
    editor, actions = case_editor(problem)
    assert not editor._item_groups
    actions.add_load_case()
    assert len(editor._item_groups) == 1
    node = next(iter(editor._item_groups))
    assert node.name in problem.steps.step_values
    actions.remove_load_case(node)
    assert problem.steps.step_values == {}
    assert not editor._item_groups
    editor.close()


def test_case_parameters_accept_registered_constants_only(case_problem):
    problem, ground, _ = case_problem
    problem.helper_variables.append(HelperVariableNode(name="spring_k", params={"value": "10.0"}))
    session = LoadCaseSession(problem.steps, problem)
    assert session.set_parameter("rest", ground, "stiffness", "spring_k")
    assert not session.set_parameter("rest", ground, "anchor_x", "unknown")
    assert problem.steps.step_values["rest"][ground] == ["spring_k", 0.5, 1, 2, 3]


@pytest.mark.parametrize("delete_objectives", [False, True])
def test_case_interface_delete_keeps_reference_cleanup_choices(app, case_problem, monkeypatch, delete_objectives):
    from PySide6.QtWidgets import QMessageBox

    problem, ground, _ = case_problem
    editor, actions = case_editor(problem)
    terms = list(problem.objective.objective_terms)
    reply = QMessageBox.StandardButton.Yes if delete_objectives else QMessageBox.StandardButton.No
    monkeypatch.setattr(QMessageBox, "exec", lambda self: reply)
    actions.remove_load_case(LoadCaseNode(problem, "rest"))
    assert "rest" not in problem.steps.step_values
    assert ground in problem.amplitude_components()
    if delete_objectives:
        assert all(term not in problem.objective.objective_terms for term in terms)
    else:
        assert problem.objective.objective_terms == terms
        assert all(term.get("step_name") != "rest" for term in terms)
    editor.close()


def test_invalid_load_values_mark_their_own_case_interface(app, case_problem):
    from morphopt.ui.widgets.model_tree import ModelTree, _ERROR_ROLE

    problem, ground, _ = case_problem
    problem.steps.step_values["rest"][ground][0] = "undefined_stiffness"
    tree = ModelTree()
    tree.set_problem(problem)
    rest = tree._node_item[LoadCaseNode(problem, "rest")]
    active = tree._node_item[LoadCaseNode(problem, "active")]
    assert rest.data(0, _ERROR_ROLE)
    assert not active.data(0, _ERROR_ROLE)
    tree.close()


def test_load_scalar_metadata_and_translations_cover_every_parameter():
    manager = LocalizationManager()
    for locale in ("en-US", "zh-CN"):
        messages = manager.load_locale(locale)
        for node in R.LOAD_TYPES.values():
            assert len(node.value_fields) == node.num_values
            assert all(field.label_key in messages for field in node.value_fields)
        assert all(key in messages for field in VECTOR_FIELDS for key in field.components)


def test_named_design_faces_are_valid_string_list_values():
    problem = ProblemLibrary.create("shapeopt")
    field = next(f for f in R.SURFACE_TYPES["brep_surface"].fields if f.key == "design_faces")
    validation = DefinitionValidation(problem)
    validation.field(problem, field, ["face_0", "face_7"])
    assert not validation.errors


def test_quickstart_channels_have_one_input_per_cavity(app):
    from morphopt.ui.model.chamberlayout import ChamberLayer
    from morphopt.ui.widgets.quickstart import ChamberLayersEditor

    editor = ChamberLayersEditor([ChamberLayer(chambers=3, pressure_channels=[1, 1, 2])])
    channels = editor.table.cellWidget(0, 7)
    assert isinstance(channels, SequenceInput)
    assert len(channels.edits) == 3
    channels.edits[1].setText("3")
    channels.edits[1].editingFinished.emit()
    assert editor.layers()[0].pressure_channels == [1, 3, 2]
    editor.table.item(0, 1).setText("4")
    assert len(editor.table.cellWidget(0, 7).edits) == 4
    assert editor.layers()[0].pressure_channels == [1, 3, 2, 4]
    editor.close()
