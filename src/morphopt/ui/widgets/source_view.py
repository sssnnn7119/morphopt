"""Read-only generated Python source for the synchronized definition."""

from PySide6.QtWidgets import QPlainTextEdit

from ..codegen.generator import generate_source
from ..refresh import RefreshContext


class GeneratedSourceView(QPlainTextEdit):
    """Display the generated task script as read-only Python source."""
    def __init__(self, parent=None) -> None:
        """Initialize GeneratedSourceView and its configuration state.

        Args:
            parent: Parent Qt widget; None creates a top-level widget.
        """
        super().__init__(parent)
        self.setReadOnly(True)

    def refresh_ui(self, context: RefreshContext) -> None:
        """Synchronize the view with the committed definition and refresh context.

        Args:
            context (RefreshContext): Committed definition, active selection, and domain-change
                flags for this UI refresh.
        """
        try:
            source = generate_source(context.problem)
        except Exception as exc:
            source = f"# code generation failed:\n{exc}"
        if source == self.toPlainText():
            return
        scroll = self.verticalScrollBar().value()
        self.setPlainText(source)
        self.verticalScrollBar().setValue(scroll)
