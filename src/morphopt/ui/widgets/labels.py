"""Single-line toolbar text that shrinks without widening the window."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QLabel, QSizePolicy

from ..i18n import tr


class ElidedLabel(QLabel):
    """Keep full text accessible while fitting the visible text to the toolbar."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = ""
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self.setText(text)

    def text(self) -> str:
        return self._full_text

    def setText(self, text: str) -> None:
        self._full_text = text
        self.setAccessibleName(text)
        self.setToolTip(text)
        self._elide()

    def minimumSizeHint(self):
        size = super().minimumSizeHint()
        size.setWidth(0)
        return size

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def changeEvent(self, event):
        super().changeEvent(event)
        if hasattr(self, "_full_text"):
            self._elide()

    def _elide(self) -> None:
        super().setText(
            self.fontMetrics().elidedText(
                self._full_text,
                Qt.TextElideMode.ElideRight,
                self.contentsRect().width(),
            )
        )


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
        self.setStatusTip(
            tr(
                "ui.workspace.copy_result_path"
                if self.folder
                else "ui.workspace.result_path_pending"
            )
        )
        self.setAccessibleDescription(self.toolTip())
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if self.folder
            else Qt.CursorShape.ArrowCursor
        )
        self.setFocusPolicy(
            Qt.FocusPolicy.StrongFocus if self.folder else Qt.FocusPolicy.NoFocus
        )

    def copy_path(self) -> None:
        if self.folder:
            QApplication.clipboard().setText(self.folder)
            self.pathCopied.emit()

    def mouseReleaseEvent(self, event):
        if (
            self.folder
            and event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.copy_path()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if self.folder and event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
        ):
            self.copy_path()
            event.accept()
        else:
            super().keyPressEvent(event)
