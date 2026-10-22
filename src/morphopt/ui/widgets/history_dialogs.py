"""User choices for operation-history capacity."""

from __future__ import annotations

from typing import Literal

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr


class HistoryCapacityDialog(QDialog):
    """Keep the current history until the user chooses clear or expand."""

    def __init__(self, count: int, limit: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.choice: Literal["clear", "expand"] | None = None
        self.setWindowTitle(tr("ui.history.capacity_title"))
        layout = QVBoxLayout(self)
        message = QLabel(tr("ui.history.capacity_message", count=count, limit=limit))
        message.setWordWrap(True)
        layout.addWidget(message)

        form = QFormLayout()
        self.new_limit = QSpinBox()
        self.new_limit.setRange(count + 1, 2_147_483_647)
        self.new_limit.setValue(max(count + 1, limit * 2))
        self.new_limit.setKeyboardTracking(False)
        form.addRow(tr("ui.history.new_limit"), self.new_limit)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        clear = QPushButton(tr("ui.history.clear"))
        clear.clicked.connect(lambda: self._choose("clear"))
        expand = QPushButton(tr("ui.history.expand"))
        expand.clicked.connect(lambda: self._choose("expand"))
        expand.setDefault(True)
        cancel = QPushButton(tr("ui.history.cancel"))
        cancel.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(clear)
        buttons.addWidget(expand)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

    def _choose(self, choice: Literal["clear", "expand"]) -> None:
        if choice == "expand":
            if not self.new_limit.hasAcceptableInput():
                self.new_limit.setFocus()
                self.new_limit.selectAll()
                return
            self.new_limit.interpretText()
        self.choice = choice
        self.accept()
