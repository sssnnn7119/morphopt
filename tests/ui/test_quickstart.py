"""Quickstart dialog startup and model-generation smoke tests."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QDialog

from morphopt.constants import CONSTANT
from morphopt.ui.application import ProblemLibrary
from morphopt.ui.application.quickstart import QuickstartOptions
from morphopt.ui.model.chamberlayout import ChamberLayer
from morphopt.ui.widgets.quickstart import QuickstartDialog


@pytest.fixture
def dialog():
    app = QApplication.instance() or QApplication([])
    widget = QuickstartDialog(ProblemLibrary.create_blank())
    widget.show()
    app.processEvents()
    yield widget
    widget.close()


def enter_number(spin, text):
    edit = spin.lineEdit()
    edit.setFocus()
    edit.selectAll()
    QTest.keyClicks(edit, text)
    assert text in edit.text()
    QTest.keyClick(edit, Qt.Key.Key_Tab)
    QApplication.processEvents()


def test_total_length_accepts_keyboard_input_and_reaches_the_generated_model(dialog):
    length = dialog.fields["total_length"]
    assert not length.isReadOnly()
    enter_number(length, "160.5")
    assert length.value() == 160.5
    assert dialog.options().total_length == pytest.approx(160.5)
    assert dialog.preview.options.total_length == pytest.approx(160.5)
    assert dialog.create_button.isEnabled(), dialog.error.text()
    dialog._create()
    restored = QuickstartOptions.from_problem(dialog.problem)
    assert restored.total_length == pytest.approx(160.5)


def test_create_button_commits_a_pending_length_edit(dialog):
    edit = dialog.fields["total_length"].lineEdit()
    edit.setFocus()
    edit.selectAll()
    QTest.keyClicks(edit, "145.5")
    QTest.mouseClick(dialog.create_button, Qt.MouseButton.LeftButton)
    assert dialog.result() == QDialog.DialogCode.Accepted, dialog.error.text()
    assert QuickstartOptions.from_problem(dialog.problem).total_length == pytest.approx(145.5)


def test_total_length_scales_layers_and_individual_layers_update_the_total(dialog):
    layers = dialog.layers_editor
    layers.set_layers([ChamberLayer(length=30), ChamberLayer(length=50, phase_degrees=45)])
    layers.changed.emit()
    channel_editor = layers.table.cellWidget(1, 7)
    dialog.fields["total_length"].setValue(160)
    assert [layer.length for layer in layers.layers()] == pytest.approx([60, 100])
    assert layers.layers()[1].phase_degrees == 45
    assert layers.table.cellWidget(1, 7) is channel_editor
    layers.table.item(0, 0).setText("70.5")
    assert dialog.fields["total_length"].value() == 170.5
    assert dialog.options().total_length == 170.5


def test_method_switch_keeps_each_geometry_length_independent(dialog):
    method = dialog.fields["method"]
    # This length matches the other method's default; switching must not reset it.
    shape_length = CONSTANT.UI.QUICKSTART.DEFAULT.SIMP_LENGTH
    dialog.fields["total_length"].setValue(shape_length)
    method.setCurrentIndex(method.findData("simp"))
    enter_number(dialog.fields["length"], "125.5")
    for _ in range(2):
        method.setCurrentIndex(method.findData("shapeopt"))
        assert dialog.options().total_length == shape_length
        assert dialog.fields["total_length"].value() == shape_length
        method.setCurrentIndex(method.findData("simp"))
        assert dialog.options().total_length == 125.5
        assert dialog.fields["length"].value() == 125.5


def test_invalid_layer_can_be_corrected_before_resizing_total(dialog):
    cell = dialog.layers_editor.table.item(0, 0)
    cell.setText("")
    dialog.fields["total_length"].setValue(120)
    assert not dialog.create_button.isEnabled()
    assert dialog.error.text()
    cell.setText("80")
    enter_number(dialog.fields["total_length"], "120")
    assert dialog.options().total_length == 120
    assert dialog.create_button.isEnabled(), dialog.error.text()


def test_all_quickstart_numeric_fields_allow_editing_and_commit_complete_input(dialog):
    controls = dialog.findChildren(QAbstractSpinBox)
    assert controls
    assert all(not control.isReadOnly() for control in controls)
    assert all(not control.keyboardTracking() for control in controls)


def test_pressure_decimal_input_preserves_its_editor_and_load_case(dialog):
    objectives = dialog.objectives_editor
    pressure = objectives.pressures.fields[1]
    enter_number(pressure, "85.5")
    assert objectives.pressures.fields[1] is pressure
    assert dialog.options().objectives[0].pressures_kpa[1] == 85.5


def test_workspace_numeric_inputs_are_committed_without_resetting(dialog):
    objectives = dialog.objectives_editor
    objectives.kind.setCurrentIndex(objectives.kind.findData("workspace_plane"))
    enter_number(objectives.workspace_pressure, "125.5")
    enter_number(objectives.workspace_order, "4")
    options = dialog.options()
    assert options.objectives[0].workspace_pressure_kpa == 125.5
    assert options.objectives[0].gauss_order == 4
    assert dialog.create_button.isEnabled(), dialog.error.text()


def test_quickstart_builds_fields_and_generates_shape_problem():
    app = QApplication.instance() or QApplication([])
    dialog = QuickstartDialog(ProblemLibrary.create_blank())

    assert dialog.create_button.isEnabled()
    assert dialog.fields["mu"].decimals() == (
        CONSTANT.UI.QUICKSTART.WIDGET.NUMERIC_FIELD_DECIMALS.MATERIAL
    )
    assert dialog.fields["volume_fraction"].decimals() == (
        CONSTANT.UI.QUICKSTART.WIDGET.NUMERIC_FIELD_DECIMALS.VOLUME_FRACTION
    )
    assert dialog.objectives_editor.workspace_pressure.singleStep() == (
        CONSTANT.UI.QUICKSTART.WIDGET.NUMERIC_FIELD_STEP.PRESSURE_KPA
    )

    method = dialog.fields["method"]
    method.setCurrentIndex(method.findData("simp"))
    app.processEvents()
    assert dialog.create_button.isEnabled(), dialog.error.text()

    method.setCurrentIndex(method.findData("shapeopt"))
    app.processEvents()
    assert dialog.create_button.isEnabled(), dialog.error.text()

    dialog._create()

    assert dialog.result() == QDialog.DialogCode.Accepted, dialog.error.text()
    assert dialog.problem is not None
