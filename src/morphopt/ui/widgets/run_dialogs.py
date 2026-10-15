"""Dialogs used to choose and resume optimization runs."""

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

from ..application import RunSourceKind
from ..i18n import tr
from ...constants import CONSTANT
class ContinueDialog(QDialog):
    """Choose the persisted iteration from which a result should resume."""

    def __init__(self, max_step: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('ui.widgets.run_dialogs.continue_optimization'))
        self.setMinimumWidth(CONSTANT.UI.WIDGETS.CONTINUE_DIALOG_MINIMUM_WIDTH)
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


class SourceDialog(QDialog):
    """Choose the source consumed by the next optimization run."""

    def __init__(self, has_definition: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('ui.widgets.run_dialogs.choose_task_source'))
        self.setMinimumWidth(CONSTANT.UI.WIDGETS.SOURCE_DIALOG_MINIMUM_WIDTH)
        self._chosen: RunSourceKind | None = None
        layout = QVBoxLayout(self)
        caption = QLabel(
            tr('ui.widgets.run_dialogs.choose_the_task_source_for_this_run')
        )
        caption.setStyleSheet("color:#9aa4b2;")
        layout.addWidget(caption)

        options = (
            (
                RunSourceKind.DEFINITION,
                tr('ui.widgets.run_dialogs.optimize_current_definition_fresh'),
                tr('ui.widgets.run_dialogs.use_the_definition_from_the_definition_page_export_py_and_run_from_scrat'),
            ),
            (
                RunSourceKind.PYTHON,
                tr('ui.widgets.run_dialogs.optimize_from_a_definition_script_py'),
                tr('ui.widgets.run_dialogs.pick_an_existing_runnable_py_run_from_scratch_with_its_own_settings'),
            ),
            (
                RunSourceKind.CONTINUE,
                tr('ui.widgets.run_dialogs.continue_an_existing_result'),
                tr('ui.widgets.run_dialogs.pick_an_existing_result_folder_continue_from_the_last_or_a_chosen_step'),
            ),
        )
        for kind, title, description in options:
            if kind is RunSourceKind.DEFINITION and not has_definition:
                continue
            button = QPushButton(title)
            button.setToolTip(description)
            button.setProperty("buttonLayout", "choice")
            button.clicked.connect(
                lambda _checked=False, selected=kind: self._accept(selected)
            )
            layout.addWidget(button)

        if not has_definition:
            note = QLabel(
                tr('ui.widgets.run_dialogs.note_no_definition_received_so_the_current_definition_option_is_unavaila')
            )
            note.setStyleSheet("color:#7f8c8d;")
            layout.addWidget(note)

        cancel = QPushButton(tr('ui.widgets.run_dialogs.cancel'))
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)

    def _accept(self, kind: RunSourceKind) -> None:
        self._chosen = kind
        self.accept()

    def chosen(self) -> RunSourceKind | None:
        return self._chosen
