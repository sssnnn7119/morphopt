"""Choose the saved iteration from which optimization should continue."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

from ..i18n import tr
from ..theme import theme_manager


class ContinueDialog(QDialog):
    """Choose the persisted iteration from which a result should resume."""

    def __init__(self, max_step: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('ui.widgets.run_dialogs.continue_optimization'))
        self.setMinimumWidth(theme_manager.palette.layout.widgets.continue_dialog_minimum_width)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                tr('ui.widgets.run_dialogs.the_result_has_reached_step_value_choose_where_to_resume', value_0=max_step)
            )
        )
        self.last_step = QRadioButton(
            tr('ui.widgets.run_dialogs.resume_from_the_last_step')
        )
        self.last_step.setChecked(True)
        self.chosen_step = QRadioButton(
            tr('ui.widgets.run_dialogs.resume_from_a_chosen_step')
        )
        self.step = QSpinBox()
        self.step.setRange(1, max(1, max_step))
        self.step.setValue(max(1, max_step))
        self.step.setEnabled(False)
        self.last_step.toggled.connect(
            lambda selected: self.step.setEnabled(not selected)
        )

        step_row = QHBoxLayout()
        step_row.addWidget(self.chosen_step)
        step_row.addWidget(self.step)
        layout.addWidget(self.last_step)
        layout.addLayout(step_row)

        buttons = QHBoxLayout()
        accept = QPushButton(tr('ui.widgets.run_dialogs.continue'))
        accept.clicked.connect(self.accept)
        cancel = QPushButton(tr('ui.widgets.run_dialogs.cancel'))
        cancel.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(accept)
        layout.addLayout(buttons)

    def target_iteration(self) -> int | None:
        return self.step.value() if self.chosen_step.isChecked() else None
