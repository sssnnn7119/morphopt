"""Read-only generated Python source for the synchronized definition."""

from PySide6.QtWidgets import QPlainTextEdit

from ..codegen.generator import generate_source
from ..refresh import RefreshContext


class GeneratedSourceView(QPlainTextEdit):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)

    def refresh_ui(self, context: RefreshContext) -> None:
        try:
            source = generate_source(context.problem)
        except Exception as exc:
            source = f"# code generation failed:\n{exc}"
        if source == self.toPlainText():
            return
        scroll = self.verticalScrollBar().value()
        self.setPlainText(source)
        self.verticalScrollBar().setValue(scroll)
