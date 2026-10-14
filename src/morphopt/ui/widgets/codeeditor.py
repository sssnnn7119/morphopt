"""Lightweight Python code editor with syntax highlighting (body of a slot).

The widget edits the *body* of a method / slot; it is indented by the code
generator when the final module is produced.

Editing behaviour (via the internal :class:`_CodeEdit`):
* ``Tab`` indents with 4 spaces, ``Shift+Tab`` outdents, ``Enter`` starts a new
  line and keeps the current indentation (one extra level after ``:``).
* ``Ctrl+Z`` undo / ``Ctrl+Shift+Z`` (or ``Ctrl+Y``) redo are bound explicitly.
* :meth:`CodeEditor.set_body` does nothing when the text is unchanged, so a
  parent refresh never resets the caret or clears the undo history while the
  user is typing.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..application.editing import HelperCodeSession
    from ..model.problem import Node, ProblemDefinition
    from .definition_actions import DefinitionActions

from PySide6.QtCore import Qt, QStringListModel, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QShortcut, QKeySequence,
    QSyntaxHighlighter, QTextCharFormat,
)
from PySide6.QtWidgets import QCompleter, QPlainTextEdit, QWidget, QVBoxLayout, QLabel

from ..application.completion import CompletionItem, completion_items


class _PythonHighlighter(QSyntaxHighlighter):
    KEYWORDS = (
        "and|as|assert|async|await|break|class|continue|def|del|elif|else|except|"
        "False|finally|for|from|global|if|import|in|is|lambda|None|nonlocal|not|"
        "or|pass|raise|return|True|try|while|with|yield"
    )

    def __init__(self, document):
        super().__init__(document)

        def fmt(color: str, bold: bool = False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Weight.Bold)
            return f

        self._rules = [
            (re.compile(r"\b(%s)\b" % self.KEYWORDS), fmt("#c678dd", True)),
            (re.compile(r"\b(?:self|super)\b"), fmt("#e5c07b")),
            (re.compile(r"\b\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?\b"), fmt("#d19a66")),
        ]
        self._string_re = re.compile(r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\')')
        self._comment_re = re.compile(r"#[^\n]*")
        self._f_string = fmt("#98c379")
        self._f_comment = fmt("#5c6370")
        self._f_decorator = fmt("#e06c75")

    def highlightBlock(self, text: str) -> None:
        # comments first (but not inside strings): naive, good enough
        for m in self._comment_re.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._f_comment)
        for m in self._string_re.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._f_string)
        for regex, f in self._rules:
            for m in regex.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), f)
        dec = re.match(r"(\s*)(@\w+|def |class )(\w*)", text)
        if dec:
            self.setFormat(dec.start(2), dec.end(2) - dec.start(2), self._f_decorator)


class _CodeEdit(QPlainTextEdit):
    """Code editor text area with indentation, undo/redo, and completions."""

    INDENT = "    "  # 4 spaces per level
    focusReceived = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # ensure undo / redo always work, even if native shortcuts are remapped
        QShortcut(QKeySequence.StandardKey.Undo, self, activated=self.undo)
        QShortcut(QKeySequence.StandardKey.Redo, self, activated=self.redo)
        self._completion_slot = ""
        self._completion_problem = None
        self._completion_items: dict[str, CompletionItem] = {}
        self._completion_model = QStringListModel(self)
        self._completer = QCompleter(self._completion_model, self)
        self._completer.setWidget(self)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.activated.connect(self._insert_completion)

    # ----------------------------------------------------------- completion
    def set_completion_context(self, slot_key: str, problem=None) -> None:
        """Set the model code slot whose symbols should be suggested."""
        if (slot_key == self._completion_slot
                and problem is self._completion_problem):
            return
        self._completion_slot = slot_key
        self._completion_problem = problem
        self._hide_completions()

    def _show_completions(self, force: bool = False) -> None:
        if not self._completion_slot:
            return
        prefix = self._completion_prefix()
        if not force and not self._is_member_access() and len(prefix) < 3:
            return
        member_expression = self._member_expression()
        candidates = completion_items(
            self._completion_slot,
            self._completion_problem,
            member_expression=member_expression,
        )
        if member_expression:
            candidates = self._member_candidates(candidates, member_expression)
        self._completion_items = {item.label: item for item in candidates}
        self._completion_model.setStringList(list(self._completion_items))
        self._completer.setCompletionPrefix(prefix)
        if self._completer.completionCount() == 0:
            self._hide_completions()
            return
        popup = self._completer.popup()
        popup.setCurrentIndex(self._completer.completionModel().index(0, 0))
        # ``cursorRect()`` is only a few pixels wide.  Passing it through as
        # the complete-popup geometry can collapse QCompleter to a vertical
        # line on some Qt platform themes, so reserve enough width for the
        # longest visible candidate and its scrollbar.
        popup_width = (
            popup.sizeHintForColumn(0)
            + popup.verticalScrollBar().sizeHint().width()
        )
        popup_rect = self.cursorRect()
        popup_rect.setWidth(max(260, popup_width))
        self._completer.complete(popup_rect)

    def _hide_completions(self) -> None:
        self._completer.popup().hide()

    def _completion_prefix(self) -> str:
        cursor = self.textCursor()
        before_cursor = cursor.block().text()[:cursor.positionInBlock()]
        match = re.search(r"[A-Za-z_]\w*$", before_cursor)
        return match.group(0) if match else ""

    def _is_member_access(self) -> bool:
        return self._member_expression() is not None

    def _member_expression(self) -> str | None:
        """Return the expression left of the current member-access dot."""
        cursor = self.textCursor()
        before_cursor = cursor.block().text()[:cursor.positionInBlock()]
        match = re.search(
            r"([A-Za-z_]\w*(?:\.\w+|\[[^\]]+\])*)\.\s*[A-Za-z_]*$",
            before_cursor,
        )
        return match.group(1) if match else None

    @staticmethod
    def _member_candidates(candidates: list[CompletionItem], expression: str
                           ) -> list[CompletionItem]:
        """Adapt full-path candidates to text inserted after ``expression.``."""
        member_prefix = f"{expression}."
        items: list[CompletionItem] = []
        for item in candidates:
            if item.insert_text.startswith(member_prefix):
                suffix = item.insert_text[len(member_prefix):]
                items.append(CompletionItem(suffix, suffix))
        return items

    def _insert_completion(self, label: str) -> None:
        item = self._completion_items.get(label)
        if item is None:
            return
        prefix = self._completion_prefix()
        cursor = self.textCursor()
        if prefix:
            cursor.movePosition(cursor.MoveOperation.Left,
                                cursor.MoveMode.KeepAnchor, len(prefix))
        cursor.insertText(item.insert_text)
        self.setTextCursor(cursor)

    # ---------------------------------------------------------- key events
    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.focusReceived.emit()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        mods = event.modifiers()
        if self._completer.popup().isVisible() and key in (
                Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Escape,
                Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            event.ignore()
            return
        if (key == Qt.Key.Key_Space
                and mods & Qt.KeyboardModifier.ControlModifier):
            self._show_completions(force=True)
            return
        # Note: on most platforms Shift+Tab arrives as Key_Backtab (not
        # Key_Tab), so we must treat both as Tab / Shift+Tab and consume them,
        # otherwise Qt would fall through to widget focus traversal.
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab) and \
                not (mods & Qt.KeyboardModifier.ControlModifier):
            if (mods & Qt.KeyboardModifier.ShiftModifier) or \
                    key == Qt.Key.Key_Backtab:
                self._unindent()
            else:
                self._indent()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and \
                not (mods & Qt.KeyboardModifier.ControlModifier):
            if not self.textCursor().hasSelection():
                self._newline_with_indent()
                return
        super().keyPressEvent(event)
        if event.text() == ".":
            QTimer.singleShot(0, lambda: self._show_completions(force=True))
        elif event.text().isalnum() or event.text() == "_":
            QTimer.singleShot(0, self._show_completions)
        else:
            self._hide_completions()

    # ---------------------------------------------------------- editing ops
    def _newline_with_indent(self) -> None:
        """Insert a newline and keep the current line's indentation."""
        tc = self.textCursor()
        line = tc.block().text()
        indent = line[: len(line) - len(line.lstrip(" \t"))]
        if line.rstrip().endswith(":"):
            indent += self.INDENT
        tc.beginEditBlock()
        tc.insertText("\n" + indent)
        tc.endEditBlock()

    def _indent(self) -> None:
        tc = self.textCursor()
        if not tc.hasSelection():
            tc.insertText(self.INDENT)
            return
        self._transform_lines(lambda ln: self.INDENT + ln)

    def _unindent(self) -> None:
        tc = self.textCursor()
        if not tc.hasSelection():
            self._unindent_current_line()
            return

        def drop(ln: str) -> str:
            if ln.startswith(self.INDENT):
                return ln[len(self.INDENT):]
            n = len(ln) - len(ln.lstrip(" \t"))
            return ln[n:]
        self._transform_lines(drop)

    def _transform_lines(self, fn) -> None:
        """Apply ``fn`` to every fully-selected line (indent / outdent).

        Each affected line's text is *replaced* by ``fn(line)`` instead of being
        inserted in front of it, so indenting a selection never duplicates it.
        """
        tc = self.textCursor()
        doc = tc.document()
        start = doc.findBlock(tc.selectionStart())
        end = doc.findBlock(tc.selectionEnd())
        if end.position() == tc.selectionEnd() and end is not start:
            end = end.previous()
            if end is None:
                return
        cur = QPlainTextEdit.textCursor(self)
        cur.beginEditBlock()
        block = start
        while True:
            # select the whole line (minus its trailing newline) and replace it
            cur.setPosition(block.position())
            cur.setPosition(block.position() + block.length() - 1,
                            cur.MoveMode.KeepAnchor)
            cur.insertText(fn(block.text()))
            if block == end:
                break
            block = block.next()
            if block is None:
                break
        cur.endEditBlock()
        # keep the (shifted) selection so repeated Tab keeps working
        new_sel = self.textCursor()
        new_sel.setPosition(start.position())
        new_sel.setPosition(end.position() + end.length() - 1,
                            new_sel.MoveMode.KeepAnchor)
        self.setTextCursor(new_sel)

    def _unindent_current_line(self) -> None:
        """Remove up to one indent level at the caret of the current line."""
        tc = self.textCursor()
        block = tc.block()
        text = block.text()
        n = len(text) - len(text.lstrip(" \t"))
        if n == 0:
            return
        remove = min(len(self.INDENT), n)
        tc.beginEditBlock()
        tc.setPosition(block.position())
        tc.setPosition(block.position() + remove, tc.MoveMode.KeepAnchor)
        tc.removeSelectedText()
        tc.endEditBlock()


class CodeEditor(QWidget):
    """Body-of-a-method Python editor with contextual basic completion.

    Completion is activated with ``Ctrl+Space`` or automatically after member
    access / a three-character identifier.  ``completion_context`` is a model
    slot key such as ``"_objective_function"`` or
    ``"apply_surface_constraints"`` (the optional Part-level geometry hook).
    """

    focusReceived = Signal()

    def __init__(self, title: str = "Code", parent=None,
                 completion_context: str = "", completion_problem=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        cap = QLabel(title)
        cap.setStyleSheet("color:#7f8c8d; font-size:11px;")
        lay.addWidget(cap)
        self._edit = _CodeEdit(self)
        self._edit.focusReceived.connect(self.focusReceived)
        self._edit.setMinimumHeight(140)
        mono = QFont("DejaVu Sans Mono", 10)
        self._edit.setFont(mono)
        metrics = QFontMetrics(mono)
        self._edit.setTabStopDistance(4 * metrics.horizontalAdvance(" "))
        self._edit.set_completion_context(completion_context, completion_problem)
        lay.addWidget(self._edit)
        self.highlighter = _PythonHighlighter(self._edit.document())

    # ------------------------------------------------------------- public
    def set_body(self, text: str) -> None:
        # Skip when unchanged so an automatic parent refresh (which feeds back
        # the same text) neither moves the caret nor clears the undo history.
        if self._edit.toPlainText() == text:
            return
        self._edit.setPlainText(text)

    def body(self) -> str:
        return self._edit.toPlainText()

    def set_completion_context(self, slot_key: str, problem=None) -> None:
        """Refresh completion symbols for the current code slot and problem."""
        self._edit.set_completion_context(slot_key, problem)

    def insert_snippet(self, text: str, *, at_cursor: bool = True) -> None:
        """Insert source at the caret, or append it when no editor was active."""
        if not text:
            return
        cursor = self._edit.textCursor()
        if not at_cursor:
            cursor.movePosition(cursor.MoveOperation.End)
        if cursor.positionInBlock() and not cursor.hasSelection():
            text = "\n" + text
        if not text.endswith("\n"):
            text += "\n"
        cursor.beginEditBlock()
        cursor.insertText(text)
        cursor.endEditBlock()
        self._edit.setTextCursor(cursor)
        self._edit.setFocus()

    @property
    def edit(self) -> _CodeEdit:
        return self._edit


class HelperCodeEditor(QWidget):
    """Module code, named variables and function bodies as one focused editor."""
    changed = Signal(object)

    def __init__(self, actions: DefinitionActions, parent=None):
        from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton
        super().__init__(parent)
        self.actions = actions
        self.session: HelperCodeSession | None = None
        self._loading = False
        layout = QVBoxLayout(self)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        buttons = QHBoxLayout()
        self.add_variable = QPushButton()
        self.add_function = QPushButton()
        self.delete = QPushButton()
        self.add_variable.clicked.connect(lambda: actions.add_helper("helper_variable"))
        self.add_function.clicked.connect(lambda: actions.add_helper("helper_function"))
        self.delete.clicked.connect(self._delete)
        for button in (self.add_variable, self.add_function, self.delete):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.name, self.value, self.parameters = QLineEdit(), QLineEdit(), QLineEdit()
        self.name_label, self.value_label, self.parameters_label, self.code_label = QLabel(), QLabel(), QLabel(), QLabel()
        for label, edit in ((self.name_label, self.name), (self.value_label, self.value), (self.parameters_label, self.parameters)):
            layout.addWidget(label)
            layout.addWidget(edit)
            edit.editingFinished.connect(self._save)
        layout.addWidget(self.code_label)
        self.code = CodeEditor("Python")
        self.code.edit.textChanged.connect(self._save)
        layout.addWidget(self.code, 1)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color:#e57373;")
        layout.addWidget(self.error)
        self.apply_language()

    def apply_language(self) -> None:
        from ..i18n import tr
        self.hint.setText(tr('ui.workbench.use_the_free_code_block_for_module_code_variables_have_a_name_and_python'))
        self.add_variable.setText(tr('ui.workbench.add_helper_variable'))
        self.add_function.setText(tr('ui.workbench.add_helper_function'))
        self.delete.setText(tr('ui.workbench.delete_item'))
        for label, key in ((self.name_label, 'name'), (self.value_label, 'value_python_expression'), (self.parameters_label, 'parameters')):
            label.setText(tr(f'ui.workbench.{key}'))
        self.name.setPlaceholderText(tr('ui.workbench.name'))
        self.value.setPlaceholderText(tr('ui.workbench.value_python_expression'))
        self.parameters.setPlaceholderText(tr('ui.workbench.parameters_e_g_x_scale_1'))

    def edit_node(self, node: Node | None, problem: ProblemDefinition) -> None:
        from ..application.editing import HelperCodeSession
        from ..i18n import tr
        if self.session is not None and self.session.node is node and self.session.problem is problem:
            return
        self.session = HelperCodeSession(problem, node)
        kind = node.kind if node is not None else "helper_code"
        editable = kind in {"helper_variable", "helper_function"}
        self.add_variable.setVisible(kind in {"helper_code", "helper_variables_group"})
        self.add_function.setVisible(kind in {"helper_code", "helper_functions_group"})
        self.delete.setVisible(editable)
        for label, widget, visible in (
            (self.name_label, self.name, editable),
            (self.value_label, self.value, kind == "helper_variable"),
            (self.parameters_label, self.parameters, kind == "helper_function"),
            (self.code_label, self.code, kind in {"helper_code_block", "helper_function"}),
        ):
            label.setVisible(visible)
            widget.setVisible(visible)
        self.error.setVisible(kind in {"helper_code_block", "helper_variable", "helper_function"})
        self.code_label.setText(tr('ui.workbench.free_code' if kind == "helper_code_block" else 'ui.workbench.function_body'))
        self._loading = True
        try:
            self.name.setText(node.name if editable else "")
            self.value.setText(node.value if kind == "helper_variable" else "")
            self.parameters.setText(node.parameters if kind == "helper_function" else "")
            self.code.set_body(problem.helper_code if kind == "helper_code_block" else node.body if kind == "helper_function" else "")
        finally:
            self._loading = False
        self._validate()

    def _delete(self) -> None:
        if self.session is not None and self.session.node is not None:
            self.actions.remove_helper(self.session.node)

    def _save(self) -> None:
        if self._loading or self.session is None:
            return
        self.session.save(self.name.text(), self.value.text(), self.parameters.text(), self.code.body())
        self._validate()
        self.changed.emit(self.session.node)

    def _validate(self) -> None:
        from ..i18n import tr
        if self.session is None:
            return
        try:
            self.session.validate()
        except (SyntaxError, ValueError) as exc:
            self.error.setText(tr('ui.workbench.invalid_helper_definition_value', value_0=exc))
        else:
            self.error.clear()
