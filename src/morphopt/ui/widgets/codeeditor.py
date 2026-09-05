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

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QShortcut, QKeySequence,
    QSyntaxHighlighter, QTextCharFormat,
)
from PySide6.QtWidgets import QPlainTextEdit, QWidget, QVBoxLayout, QLabel


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
    """QPlainTextEdit with code-editor friendly Tab / Enter and undo/redo."""

    INDENT = "    "  # 4 spaces per level

    def __init__(self, parent=None):
        super().__init__(parent)
        # ensure undo / redo always work, even if native shortcuts are remapped
        QShortcut(QKeySequence.StandardKey.Undo, self, activated=self.undo)
        QShortcut(QKeySequence.StandardKey.Redo, self, activated=self.redo)

    # ---------------------------------------------------------- key events
    def keyPressEvent(self, event) -> None:
        key = event.key()
        mods = event.modifiers()
        if key == Qt.Key.Key_Tab and not (mods & Qt.KeyboardModifier.ControlModifier):
            if mods & Qt.KeyboardModifier.ShiftModifier:
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
        """Apply ``fn`` to every fully-selected line (indent / outdent)."""
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
            cur.setPosition(block.position())
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
    """Body-of-a-method python editor with a small caption."""

    def __init__(self, title: str = "Code", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        cap = QLabel(title)
        cap.setStyleSheet("color:#7f8c8d; font-size:11px;")
        lay.addWidget(cap)
        self._edit = _CodeEdit(self)
        self._edit.setMinimumHeight(140)
        mono = QFont("DejaVu Sans Mono", 10)
        self._edit.setFont(mono)
        metrics = QFontMetrics(mono)
        self._edit.setTabStopDistance(4 * metrics.horizontalAdvance(" "))
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

    @property
    def edit(self) -> _CodeEdit:
        return self._edit
