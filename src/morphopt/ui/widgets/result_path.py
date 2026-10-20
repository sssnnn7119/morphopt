"""Optimization name with hover and click access to its result directory."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication

from ..i18n import tr
from .elided_label import ElidedLabel


class ResultPathLabel(ElidedLabel):
    """Show the full path on hover and copy it when the name is activated."""

    pathCopied = Signal()

    def __init__(self, parent=None):
        self.folder: str | None = None
        super().__init__(parent=parent)

    def setText(self, text: str) -> None:
        super().setText(text)
        self._update_description()

    def set_folder(self, folder: str | None) -> None:
        self.folder = str(Path(folder).resolve()) if folder else None
        self._update_description()

    def _update_description(self) -> None:
        self.setToolTip(self.folder or tr("ui.workspace.result_path_pending"))
        self.setStatusTip(tr(
            "ui.workspace.copy_result_path" if self.folder else "ui.workspace.result_path_pending"
        ))
        self.setAccessibleDescription(self.toolTip())
        self.setCursor(Qt.CursorShape.PointingHandCursor if self.folder else Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if self.folder else Qt.FocusPolicy.NoFocus)

    def copy_path(self) -> None:
        if self.folder:
            QApplication.clipboard().setText(self.folder)
            self.pathCopied.emit()

    def mouseReleaseEvent(self, event):
        if (self.folder and event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.copy_path()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if self.folder and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.copy_path()
            event.accept()
        else:
            super().keyPressEvent(event)
