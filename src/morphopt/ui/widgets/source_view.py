"""Read-only generated Python source for the synchronized definition."""

from PySide6.QtWidgets import QPlainTextEdit

from ..codegen.generator import generate_source
from ..model.problem import ProblemDefinition
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
        self._pending: ProblemDefinition | None = None

    def refresh_ui(self, context: RefreshContext) -> None:
        """Synchronize the view with the committed definition and refresh context.

        Args:
            context (RefreshContext): Committed definition, active selection, and domain-change
                flags for this UI refresh.
        """
        self._pending = context.problem
        if self.isVisible():
            self._update_source()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._update_source()

    def toPlainText(self) -> str:
        """Return the current script, including pending edits when read off screen."""
        self._update_source()
        return super().toPlainText()

    def _update_source(self) -> None:
        if self._pending is None:
            return
        problem, self._pending = self._pending, None
        try:
            source = generate_source(problem)
        except Exception as exc:
            source = f"# code generation failed:\n{exc}"
        if source == super().toPlainText():
            return
        scroll = self.verticalScrollBar().value()
        self.setPlainText(source)
        self.verticalScrollBar().setValue(scroll)
