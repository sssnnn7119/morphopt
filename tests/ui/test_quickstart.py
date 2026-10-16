"""Quickstart dialog startup and model-generation smoke tests."""

from PySide6.QtWidgets import QApplication, QDialog

from morphopt.constants import CONSTANT
from morphopt.ui.application import ProblemLibrary
from morphopt.ui.widgets.quickstart import QuickstartDialog


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
