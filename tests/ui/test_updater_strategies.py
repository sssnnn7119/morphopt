"""Strategy selection must survive persistence and construct the selected policy."""

import inspect
from textwrap import dedent

import pytest
from PySide6.QtWidgets import QApplication

import morphopt
from morphopt.ui.application import ProblemLibrary, ProblemSession
from morphopt.ui.application.validation import DefinitionValidation
from morphopt.ui.codegen.generator import _emit_nested_updater
from morphopt.ui.model.configuration import geometry_updater_config, materials_updater_config
from morphopt.ui.model.fields import field_defaults
from morphopt.ui.model.problem import HelperVariableNode
from morphopt.ui.model.strategies import STRATEGY_CATALOG, strategy_config, strategy_specs
from morphopt.ui.widgets.updater_editor import UpdaterEditor, UpdaterStrategyEditor


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("group,base", [
    ("geometry", morphopt.UpdaterBoundaryPart),
    ("geometry", morphopt.UpdaterOffsetBoundaryPart),
    ("materials", morphopt.UpdaterSIMPMaterial),
])
def test_strategy_fields_match_backend_defaults(group, base):
    for key in STRATEGY_CATALOG:
        for name, spec in strategy_specs(key, group).items():
            constructor = getattr(base.strategies, name)
            defaults = field_defaults(spec.fields)
            assert defaults == {
                name: parameter.default
                for name, parameter in inspect.signature(constructor).parameters.items()
            }
            policy = constructor(**defaults)
            assert all(getattr(policy, key) == value for key, value in defaults.items())


@pytest.mark.parametrize("policy,parameter,setting", [
    ("AdaptiveShapeWeights", "tightening_steps", 20),
    ("AdaptiveShapeWeights", "initial_tolerance", 0.3),
])
def test_shape_selection_parameters_round_trip_to_generated_updater(app, tmp_path, policy, parameter, setting):
    problem = ProblemLibrary.create("shapeopt")
    config = problem.updater.geometry[0]
    editor = UpdaterEditor()
    editor.edit_node(problem.updater, problem)
    changes = []
    editor.changed.connect(changes.append)
    selector = next(
        widget for widget in editor.findChildren(UpdaterStrategyEditor)
        if widget.key == "constraint_weight_strategy"
    )
    previous_form = selector.parameters
    selector.selector.setCurrentIndex(selector.selector.findData(policy))
    assert previous_form.isHidden()
    assert config[selector.key] == strategy_config(selector.key, policy)
    assert set(selector.parameters.controls) == set(config[selector.key]["params"])
    control = selector.parameters.controls[parameter]
    control.setText(str(setting))
    control.editingFinished.emit()
    assert config[selector.key]["params"][parameter] == setting
    assert len(changes) == 2
    loaded = ProblemLibrary.load(ProblemLibrary.save(problem, tmp_path / "strategy.morph"))
    assert loaded.updater.geometry[0][selector.key] == config[selector.key]
    namespace = {"__name__": "strategy_test"}
    exec(ProblemSession(loaded).source(), namespace)
    updater = namespace["ThisController"].Updater.UpdaterBoundaryPart()
    assert isinstance(updater.step_length_strategy, morphopt.strategies.FixedStepLength)
    assert type(updater.constraint_weight_strategy) is getattr(morphopt.shapeopt.strategies, policy)
    assert getattr(updater.constraint_weight_strategy, parameter) == setting
    editor.close()


def test_material_selector_excludes_shape_policy_and_generates_constant(app):
    problem = ProblemLibrary.create("shapeopt")
    config = materials_updater_config(constraints=())
    selector = UpdaterStrategyEditor(config, "constraint_weight_strategy", "materials", problem)
    assert [selector.selector.itemData(i) for i in range(selector.selector.count())] == [
        "ConstantConstraintWeights"
    ]
    value = selector.parameters.controls["value"]
    value.setText("2.5")
    value.editingFinished.emit()
    lines = []
    _emit_nested_updater(lines.append, "MaterialUpdater", "morphopt.UpdaterSIMPMaterial", config, problem)
    namespace = {"morphopt": morphopt}
    exec(dedent("\n".join(lines)), namespace)
    updater = namespace["MaterialUpdater"]()
    assert isinstance(updater.constraint_weight_strategy, morphopt.strategies.ConstantConstraintWeights)
    assert updater.constraint_weight_strategy.value == 2.5
    selector.close()


def test_strategy_parameter_references_a_custom_constant(app):
    problem = ProblemLibrary.create("shapeopt")
    problem.helper_variables.append(HelperVariableNode(name="penalty_weight", params={"value": "4.5"}))
    config = problem.updater.geometry[0]
    selector = UpdaterStrategyEditor(config, "constraint_weight_strategy", "geometry", problem)
    value = selector.parameters.controls["value"]
    value.setText("penalty_weight")
    value.editingFinished.emit()
    namespace = {"__name__": "constant_strategy_test"}
    exec(ProblemSession(problem).source(), namespace)
    updater = namespace["ThisController"].Updater.UpdaterBoundaryPart()
    assert updater.constraint_weight_strategy.value == 4.5
    validation = DefinitionValidation(problem)
    validation.updaters()
    assert id(config) not in validation.errors
    value.setText("unknown_weight")
    value.editingFinished.emit()
    validation = DefinitionValidation(problem)
    validation.updaters()
    assert id(config) in validation.errors
    selector.close()


def test_default_configs_have_independent_strategy_parameters():
    assert list(strategy_specs("constraint_weight_strategy", "geometry")) == [
        "ConstantConstraintWeights", "AdaptiveShapeWeights",
    ]
    first, second = geometry_updater_config(), geometry_updater_config()
    first["constraint_weight_strategy"]["params"]["value"] = 9
    assert second["constraint_weight_strategy"]["params"]["value"] == 1


def test_adaptive_cross_field_validation_marks_the_optimizer():
    problem = ProblemLibrary.create("shapeopt")
    config = problem.updater.geometry[0]
    policy = strategy_config("constraint_weight_strategy", "AdaptiveShapeWeights")
    config["constraint_weight_strategy"] = policy
    validation = DefinitionValidation(problem)
    validation.updaters()
    assert id(config) not in validation.errors
    policy["params"]["final_tolerance"] = 0.3
    validation = DefinitionValidation(problem)
    validation.updaters()
    assert "final_tolerance" in " ".join(validation.errors[id(config)])


def test_selecting_policies_and_opening_existing_config_do_not_insert_defaults(app):
    problem = ProblemLibrary.create("shapeopt")
    config = problem.updater.geometry[0]
    for key in STRATEGY_CATALOG:
        config.pop(key, None)
    selector = UpdaterStrategyEditor(config, "constraint_weight_strategy", "geometry", problem)
    assert "constraint_weight_strategy" not in config
    selector.selector.setCurrentIndex(selector.selector.findData("AdaptiveShapeWeights"))
    selector.selector.setCurrentIndex(selector.selector.findData("ConstantConstraintWeights"))
    assert config[selector.key] == strategy_config(selector.key)
    assert set(selector.parameters.controls) == {"value"}
    selector.close()
