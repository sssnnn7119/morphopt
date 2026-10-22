"""Deletion choices for objective terms and their named load cases."""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

from ..i18n import tr


def confirm_case_cleanup(parent: QWidget, cases: list[str]) -> bool | None:
    """Return delete/keep, or None when the user cancels the whole operation."""
    if not cases:
        return False
    dialog = QMessageBox(parent)
    dialog.setIcon(QMessageBox.Icon.Question)
    dialog.setWindowTitle(tr("ui.load_cases.cleanup_title"))
    dialog.setText(tr("ui.load_cases.cleanup_question", count=len(cases)))
    dialog.setDetailedText("\n".join(cases))
    dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
    dialog.button(QMessageBox.StandardButton.Yes).setText(tr("ui.load_cases.delete_cases"))
    dialog.button(QMessageBox.StandardButton.No).setText(tr("ui.load_cases.keep_cases"))
    dialog.setDefaultButton(QMessageBox.StandardButton.No)
    reply = dialog.exec()
    if reply not in (QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No):
        return None
    return reply == QMessageBox.StandardButton.Yes
