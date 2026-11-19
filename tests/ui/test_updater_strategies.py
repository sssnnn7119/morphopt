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
from morphopt.ui.model.strategies import strategy_config, strategy_specs
from morphopt.ui.i18n import tr
from morphopt.ui.widgets.updater_editor import UpdaterEditor, UpdaterStrategyEditor


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_updater_device_selector_distinguishes_default_from_cpu(app, monkeypatch):
    monkeypatch.setattr(
        "morphopt.ui.widgets.updater_editor.detect_devices", lambda: ["cpu", "cuda:0"],
    )
    problem = ProblemLibrary.create_blank()
    problem.device = "cuda:0"
    editor = UpdaterEditor()
    changes = []
    editor.changed.connect(changes.append)
    editor.edit_node(problem.updater, problem)
    assert editor._device.currentText() == tr("ui.widgets.updater_editor.default_device")
    assert problem.updater_device is None
    assert not changes

    editor._device.setCurrentText("cpu")
    assert problem.updater_device == "cpu"
    editor._device.setCurrentIndex(0)
    assert problem.updater_device is None
    assert len(changes) == 2

    problem.device = "cuda:1"
    editor.edit_node(problem.updater, problem)
    assert editor._device.currentIndex() == 0
    assert problem.updater_device is None
    assert len(changes) == 2

    problem.updater_device = "cuda:9"
    editor.edit_node(problem.updater, problem)
    assert editor._device.currentText() == "cuda:9"
    assert problem.updater_device == "cuda:9"
    assert len(changes) == 2
    editor.close()


@pytest.mark.parametrize("device", [None, "cpu", "cuda:1"])
def test_updater_device_round_trip_preserves_runtime_default(tmp_path, device):
    problem = ProblemLibrary.create("shapeopt")
    problem.device = "cuda:0"
    problem.updater_device = device
    saved = ProblemLibrary.save(problem, tmp_path / "device.morph")
    restored = ProblemLibrary.load(saved)
    assert restored.updater_device == device
    namespace = {"__name__": "test_updater_device"}
    exec(ProblemSession(restored).source(), namespace)
    updater = namespace["ThisController"].Updater(None)
    assert updater._device == device


def test_adaptive_defaults_apply_the_same_mild_early_relaxation_in_ui_and_kernel():
    policy = morphopt.UpdaterBoundaryPart.strategies.AdaptiveShapeUpdate()
    config = strategy_config("geometry", "AdaptiveShapeUpdate")
    assert config["params"]["initial_tolerance"] == policy.initial_tolerance == 0.05
    assert config["params"]["final_tolerance"] == policy.final_tolerance == 0.0


@pytest.mark.parametrize("base", [morphopt.UpdaterBoundaryPart, morphopt.UpdaterOffsetBoundaryPart])
def test_geometry_kernel_defaults_to_independent_adaptive_weights(base):
    first, second = base(), base()
    assert isinstance(first.update_strategy, base.strategies.AdaptiveShapeUpdate)
    assert first.update_strategy is not second.update_strategy
    selected = base.strategies.FixedUpdate(2.5)
    assert base(update_strategy=selected).update_strategy is selected


@pytest.mark.parametrize("omit_strategy", [False, True])
def test_geometry_default_matches_the_form_and_generated_script(app, omit_strategy):
    problem = ProblemLibrary.create("shapeopt")
    config = problem.updater.geometry[0]
    if omit_strategy:
        config.pop("update_strategy")
    selector = UpdaterStrategyEditor(config, "geometry", problem)
    assert selector.selector.currentData() == "AdaptiveShapeUpdate"
    namespace = {"__name__": "default_strategy_test"}
    exec(ProblemSession(problem).source(), namespace)
    updater = namespace["ThisController"].Updater.UpdaterBoundaryPart()
    assert isinstance(updater.update_strategy, morphopt.UpdaterBoundaryPart.strategies.AdaptiveShapeUpdate)
    assert ("update_strategy" in config) is not omit_strategy
    selector.close()


@pytest.mark.parametrize("group,base", [
    ("geometry", morphopt.UpdaterBoundaryPart),
    ("geometry", morphopt.UpdaterOffsetBoundaryPart),
    ("materials", morphopt.UpdaterSIMPMaterial),
])
def test_strategy_fields_match_backend_defaults(group, base):
    for name, spec in strategy_specs(group).items():
        constructor = getattr(base.strategies, name)
        defaults = field_defaults(spec.fields)
        assert defaults == {
            name: parameter.default
            for name, parameter in inspect.signature(constructor).parameters.items()
        }
        policy = constructor(**defaults)
        assert all(getattr(policy, key) == value for key, value in defaults.items())


@pytest.mark.parametrize("policy,parameter,setting", [
    ("AdaptiveShapeUpdate", "violation_tolerance", 0.02),
    ("AdaptiveShapeUpdate", "tightening_increment", 0.002),
    ("AdaptiveShapeUpdate", "weight_change_limit", 5.0),
    ("AdaptiveShapeUpdate", "max_solves", 4),
    ("AdaptiveShapeUpdate", "initial_tolerance", 0.3),
])
def test_shape_selection_parameters_round_trip_to_generated_updater(app, tmp_path, policy, parameter, setting):
    problem = ProblemLibrary.create("shapeopt")
    config = problem.updater.geometry[0]
    config["update_strategy"] = strategy_config("geometry", "FixedUpdate")
    editor = UpdaterEditor()
    editor.edit_node(problem.updater, problem)
    changes = []
    editor.changed.connect(changes.append)
    selector = editor.findChild(UpdaterStrategyEditor)
    previous_form = selector.parameters
    selector.selector.setCurrentIndex(selector.selector.findData(policy))
    assert previous_form.isHidden()
    assert config["update_strategy"] == strategy_config("geometry", policy)
    assert set(selector.parameters.controls) == set(config["update_strategy"]["params"])
    control = selector.parameters.controls[parameter]
    control.setText(str(setting))
    control.editingFinished.emit()
    assert config["update_strategy"]["params"][parameter] == setting
    assert len(changes) == 2
    loaded = ProblemLibrary.load(ProblemLibrary.save(problem, tmp_path / "strategy.morph"))
    assert loaded.updater.geometry[0]["update_strategy"] == config["update_strategy"]
    namespace = {"__name__": "strategy_test"}
    exec(ProblemSession(loaded).source(), namespace)
    updater = namespace["ThisController"].Updater.UpdaterBoundaryPart()
    assert type(updater.update_strategy) is getattr(morphopt.shapeopt.strategies, policy)
    assert getattr(updater.update_strategy, parameter) == setting
    editor.close()


def test_material_selector_excludes_shape_policy_and_generates_constant(app):
    problem = ProblemLibrary.create("shapeopt")
    config = materials_updater_config(constraints=())
    selector = UpdaterStrategyEditor(config, "materials", problem)
    assert [selector.selector.itemData(i) for i in range(selector.selector.count())] == [
        "FixedUpdate"
    ]
    value = selector.parameters.controls["value"]
    value.setText("2.5")
    value.editingFinished.emit()
    lines = []
    _emit_nested_updater(lines.append, "MaterialUpdater", "morphopt.UpdaterSIMPMaterial", config, problem)
    namespace = {"morphopt": morphopt}
    exec(dedent("\n".join(lines)), namespace)
    updater = namespace["MaterialUpdater"]()
    assert isinstance(updater.update_strategy, morphopt.strategies.FixedUpdate)
    assert updater.update_strategy.value == 2.5
    selector.close()


def test_strategy_parameter_references_a_custom_constant(app):
    problem = ProblemLibrary.create("shapeopt")
    problem.helper_variables.append(HelperVariableNode(name="penalty_weight", params={"value": "4.5"}))
    config = problem.updater.geometry[0]
    config["update_strategy"] = strategy_config("geometry", "FixedUpdate")
    selector = UpdaterStrategyEditor(config, "geometry", problem)
    value = selector.parameters.controls["value"]
    value.setText("penalty_weight")
    value.editingFinished.emit()
    namespace = {"__name__": "constant_strategy_test"}
    exec(ProblemSession(problem).source(), namespace)
    updater = namespace["ThisController"].Updater.UpdaterBoundaryPart()
    assert updater.update_strategy.value == 4.5
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
    assert list(strategy_specs("geometry")) == [
        "FixedUpdate", "SensitivityShapeUpdate", "AdaptiveShapeUpdate",
    ]
    first, second = geometry_updater_config(), geometry_updater_config()
    first["update_strategy"]["params"]["initial_tolerance"] = 0.3
    assert second["update_strategy"] == strategy_config("geometry", "AdaptiveShapeUpdate")


def test_adaptive_cross_field_validation_marks_the_optimizer():
    problem = ProblemLibrary.create("shapeopt")
    config = problem.updater.geometry[0]
    policy = strategy_config("geometry", "AdaptiveShapeUpdate")
    config["update_strategy"] = policy
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
    config.pop("update_strategy", None)
    selector = UpdaterStrategyEditor(config, "geometry", problem)
    assert "update_strategy" not in config
    selector.selector.setCurrentIndex(selector.selector.findData("AdaptiveShapeUpdate"))
    selector.selector.setCurrentIndex(selector.selector.findData("FixedUpdate"))
    assert config["update_strategy"] == strategy_config("geometry", "FixedUpdate")
    assert set(selector.parameters.controls) == {"value"}
    selector.close()


def test_pointwise_sensitivity_strategy_round_trips_through_ui_and_script(app, tmp_path):
    problem = ProblemLibrary.create("shapeopt")
    config = problem.updater.geometry[0]
    selector = UpdaterStrategyEditor(config, "geometry", problem)
    selector.selector.setCurrentIndex(selector.selector.findData("SensitivityShapeUpdate"))
    assert config["update_strategy"] == {"type": "SensitivityShapeUpdate", "params": {}}
    loaded = ProblemLibrary.load(ProblemLibrary.save(problem, tmp_path / "pointwise.morph"))
    namespace = {"__name__": "pointwise_strategy_test"}
    exec(ProblemSession(loaded).source(), namespace)
    updater = namespace["ThisController"].Updater.UpdaterBoundaryPart()
    assert isinstance(
        updater.update_strategy,
        morphopt.UpdaterBoundaryPart.strategies.SensitivityShapeUpdate,
    )
    selector.close()
