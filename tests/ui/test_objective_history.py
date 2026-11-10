"""Generated objective contributions and independently selected history curves."""

from types import SimpleNamespace

import numpy as np
import pytest
import torch
from PySide6.QtWidgets import QApplication

from morphopt.optcore.history import History
from morphopt.ui.application import ProblemLibrary, ProblemSession
from morphopt.ui.i18n import tr
from morphopt.ui.presentation.labels import node_title
from morphopt.ui.presentation.navigation import ObjectiveItemTreeNode
from morphopt.ui.widgets.objective_editor import ObjectiveEditor
from morphopt.ui.widgets.observation_pages import MetricsPage


def generated_objective(problem):
    namespace = {"__name__": "objective_history_test"}
    exec(ProblemSession(problem).source(), namespace)
    return namespace["ThisController"].ObjectiveFunction()


def test_user_metrics_precede_weighted_objectives_and_preserve_gradients(tmp_path):
    problem = ProblemLibrary.create_blank()
    problem.helper_code = "import torch"
    problem.objective.objective_terms = [
        {"type": "custom_loss", "weight": 2.0, "body": "return self.response.square()"},
        {"type": "custom_loss", "weight": 3.0, "body": "return -self.response"},
    ]
    problem.objective.metrics_terms = [
        {"type": "custom", "body": "return self.response"},
        {"type": "custom", "body": "return [self.response + 1, self.response + 2]"},
    ]
    objective = generated_objective(problem)
    objective.response = torch.tensor(2.0, requires_grad=True)
    loss = objective.objective_function()
    recorded = objective.get_metrics()
    assert list(recorded) == ["0", "1", "2", "objective_0", "objective_1"]
    metrics = torch.stack(list(recorded.values()))
    torch.testing.assert_close(metrics, torch.tensor([2.0, 3.0, 4.0, 8.0, -6.0]))
    torch.testing.assert_close(loss, metrics[3:].sum())
    torch.testing.assert_close(torch.autograd.grad(loss, objective.response)[0], torch.tensor(5.0))
    history = History()
    history.append(objective=loss, metrics=objective.get_metrics())
    history.save(str(tmp_path))
    restored = History()
    restored.load(str(tmp_path))
    for name, value in zip(recorded, [2., 3., 4., 8., -6.]):
        assert restored.records[0]["metrics"][name] == value


@pytest.mark.parametrize("direction,expected", [("minimize", 6.0), ("maximize", -6.0), ("target", 2.0)])
def test_recorded_displacement_objective_includes_direction_and_target(direction, expected):
    problem = ProblemLibrary.create("shapeopt")
    reference = next(node.name for node in problem.fea_components() if node.type == "ReferencePoint")
    case = next(iter(problem.steps.step_values))
    problem.objective.objective_terms = [{
        "type": "displacement", "weight": 2.0, "reference_point_name": reference,
        "step_name": case, "component": "ux", "direction": direction, "target": 2.0,
    }]
    problem.objective.metrics_terms = []
    objective = generated_objective(problem)
    objective.set_step = lambda case: None
    objective.fe = SimpleNamespace(assembly=SimpleNamespace(
        device="cpu", _GC2RGC=lambda state: state,
        get_reference_point=lambda name: SimpleNamespace(_RGC_index=slice(0, 6)),
    ))
    objective.fe_results = {case: SimpleNamespace(GC=torch.tensor([3., 0., 0., 0., 0., 0.]))}
    assert objective.objective_function().item() == expected
    assert {name: value.item() for name, value in objective.get_metrics().items()} == {"objective_0": expected}


def test_objective_and_metric_tree_and_card_indices_start_at_zero():
    app = QApplication.instance() or QApplication([])
    problem = ProblemLibrary.create_blank()
    problem.objective.objective_terms = [{"type": "custom_loss", "weight": 1.0, "body": "return 1.0"}]
    problem.objective.metrics_terms = [{"type": "custom", "body": "return 2.0"}]
    for category, terms in (("objective", problem.objective.objective_terms), ("metric", problem.objective.metrics_terms)):
        handle = ObjectiveItemTreeNode(problem.objective, category, 0, terms[0])
        label = node_title(problem, handle)
        assert " 0 " in label
    editor = ObjectiveEditor()
    editor.set_problem(problem)
    assert editor._term_cards[0].title().startswith("0.")
    assert editor._metric_cards[0].title().startswith("0.")
    editor.close()


def history(metrics):
    values = np.asarray(metrics, dtype=float)
    result = History()
    for index, objective in enumerate([4., 2.]):
        record = {"objective": objective}
        if index < len(values):
            record["metrics"] = {str(column): value for column, value in enumerate(values[index])}
        result.append(**record)
    return result


def test_curve_selection_is_independent_and_survives_refresh_and_theme():
    app = QApplication.instance() or QApplication([])
    page = MetricsPage()
    data = history([[10.0, -3.0], [20.0, -7.0]])
    page.update_from_history(data, 2)
    assert page.curve_selector.count() == 3
    assert page.curve_selector.itemText(1) == tr("ui.widgets.observation_pages.metric_value", value_0=0)
    np.testing.assert_equal(page.figure.axes[0].lines[0].get_ydata(), [4.0, 2.0])
    page.curve_selector.setCurrentIndex(2)
    axes = page.figure.axes[0]
    assert len(axes.lines) == 1
    np.testing.assert_equal(axes.lines[0].get_ydata(), [-3.0, -7.0])
    page.update_from_history(data, 1)
    page.apply_theme()
    page.apply_language()
    page._font_changed("chart")
    assert page.curve_selector.currentIndex() == 2
    np.testing.assert_equal(page.figure.axes[0].lines[0].get_ydata(), [-3.0, -7.0])
    page.clear()
    assert page.curve_selector.count() == 0
    assert not page.curve_selector.isEnabled()
    page.update_from_history(history([[0.0], [1.0]]), 2)
    assert page.curve_selector.currentIndex() == 0
    page.close()


def test_missing_metric_rows_leave_gaps_in_the_curve():
    app = QApplication.instance() or QApplication([])
    page = MetricsPage()
    page.update_from_history(history([[10.0]]), 2)
    page.curve_selector.setCurrentIndex(1)
    values = page.figure.axes[0].lines[0].get_ydata()
    assert values[0] == 10.0 and np.isnan(values[1])
    page.close()


def test_named_metric_editor_serializes_and_generated_dictionary_names_reach_plot(tmp_path):
    app = QApplication.instance() or QApplication([])
    problem = ProblemLibrary.create_blank()
    problem.objective.objective_terms = [{"type": "custom_loss", "weight": 1., "body": "return 4.0"}]
    problem.objective.metrics_terms = [
        {"type": "custom", "body": "return 2.0"},
        {"type": "custom", "body": "return {'Ry': 3.0, '伸长量': 5.0}"},
    ]
    editor = ObjectiveEditor()
    editor.set_problem(problem)
    field = editor._metric_fields[0]["name"]
    field.setText("tip_displacement")
    field.editingFinished.emit()
    ProblemLibrary.save(problem, tmp_path / "named.morph")
    loaded = ProblemLibrary.load(tmp_path / "named.morph")
    assert loaded.objective.metrics_terms[0]["name"] == "tip_displacement"
    metrics = generated_objective(loaded).get_metrics()
    assert metrics == {"tip_displacement": 2., "Ry": 3., "伸长量": 5., "objective_0": 4.}
    history_data = History()
    history_data.append(objective=4., metrics=metrics)
    history_data.save(str(tmp_path))
    restored = History()
    restored.load(str(tmp_path))
    page = MetricsPage()
    page.update_from_history(restored, 1)
    for index, name in enumerate(metrics):
        label = tr("ui.widgets.observation_pages.metric_value", value_0=name)
        assert page.table.horizontalHeaderItem(index + 2).text() == label
        assert page.curve_selector.itemText(index + 1) == label
    page.curve_selector.setCurrentIndex(3)
    np.testing.assert_equal(page.figure.axes[0].lines[0].get_ydata(), [5.])
    editor.close()
    page.close()


def test_custom_history_fields_appear_without_registering_columns():
    app = QApplication.instance() or QApplication([])
    data = History()
    data.append(objective=4., diagnostics={"residual": 0.1}, vector=[[1., 2.]], status="running")
    data.append(objective=2., diagnostics={"new_value": 3.}, vector=[[2., 4.]], status="finished")
    page = MetricsPage()
    page.update_from_history(data, 2)
    labels = [page.curve_selector.itemText(index) for index in range(page.curve_selector.count())]
    assert "diagnostics.residual" in labels
    assert "diagnostics.new_value" in labels
    assert "vector.0.1" in labels
    assert "status" not in labels
    page.curve_selector.setCurrentIndex(labels.index("diagnostics.residual"))
    values = page.figure.axes[0].lines[0].get_ydata()
    assert values[0] == 0.1 and np.isnan(values[1])
    page.close()


def test_custom_curve_labels_do_not_overwrite_other_series():
    app = QApplication.instance() or QApplication([])
    data = History()
    title = tr("ui.widgets.observation_pages.objective")
    data.append(objective=1., **{title: 2.})
    page = MetricsPage()
    page.update_from_history(data, 1)
    assert page.curve_selector.count() == 2
    page.curve_selector.setCurrentIndex(0)
    np.testing.assert_equal(page.figure.axes[0].lines[0].get_ydata(), [1.])
    page.curve_selector.setCurrentIndex(1)
    np.testing.assert_equal(page.figure.axes[0].lines[0].get_ydata(), [2.])
    page.close()
