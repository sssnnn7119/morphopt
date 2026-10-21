"""Single-line toolbar text that shrinks without widening the window."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy


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
