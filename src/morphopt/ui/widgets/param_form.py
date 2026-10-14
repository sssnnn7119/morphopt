"""Shared schema form for live node fields and updater parameter dictionaries."""
from __future__ import annotations

from collections.abc import Callable
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QComboBox, QCheckBox,
    QPushButton, QHBoxLayout, QFileDialog, QLabel, QPlainTextEdit,
)
from ..application.values import field_text, parse_field
from ..i18n import tr
from .values import combo_value, display_choice, DOF_LABELS


class ParamForm(QWidget):
    """Render a schema and write directly to its bound source; no value copy."""
    changed = Signal(str)

    def __init__(self, params: dict | None, fields, extra_choices=None, parent=None,
                 helper_names=(), *, read: Callable[[str, object], object] | None = None, write: Callable[[str, object], bool | None] | None = None):
        super().__init__(parent)
        self.params = params
        self.helper_names = set(helper_names)
        if params is None:
            if read is None or write is None:
                raise TypeError("Bind a parameter dictionary or provide both field callbacks.")
            self._read, self._write = read, write
        else:
            self._read = read or params.get
            self._write = write or params.__setitem__
        self.specs = list(fields)
        self.controls: dict[str, QWidget] = {}
        self.dof_groups: dict[str, list[QCheckBox]] = {}
        self._form = QFormLayout(self)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._form.setVerticalSpacing(6)
        builders = {
            "bool": self._checkbox, "combo": self._combo, "file": self._path,
            "dir": self._path, "dofs": self._dofs, "text": self._text, "code": self._text,
        }
        for spec in self.specs:
            key = spec["key"]
            value = self._read(key, spec["default"])
            choices = list(dict.fromkeys([*(spec.get("choices") or []), *((extra_choices or {}).get(key) or [])]))
            widget = builders.get(spec["type"], self._line)(spec, value, choices)
            label = QLabel(tr(spec["label_key"]))
            label.setToolTip(tr(spec["doc_key"]) if spec.get("doc_key") else "")
            widget.setToolTip(label.toolTip())
            self._form.addRow(label, widget)

    def refresh_choices(self, choices: dict) -> None:
        for spec in self.specs:
            if spec["type"] != "combo":
                continue
            key = spec["key"]
            combo = self.controls[key]
            current = self._read(key, spec["default"])
            items = list(dict.fromkeys([*(spec.get("choices") or []), *(choices.get(key) or [])]))
            combo.blockSignals(True)
            try:
                combo.clear()
                for value in items:
                    combo.addItem(display_choice(key, value), value)
                index = combo.findData(current)
                combo.setCurrentIndex(index)
                if index < 0:
                    combo.setEditText(field_text(current))
            finally:
                combo.blockSignals(False)

    def _commit(self, key, value) -> None:
        if self._write(key, value) is not False:
            self.changed.emit(key)
            return
        control = self.controls[key]
        control.blockSignals(True)
        try:
            value = self._read(key, None)
            if isinstance(control, QComboBox):
                index = control.findData(value)
                control.setCurrentIndex(index)
                if index < 0:
                    control.setEditText(field_text(value))
            elif isinstance(control, QLineEdit):
                control.setText(field_text(value))
        finally:
            control.blockSignals(False)

    def _line(self, spec, value, choices):
        key = spec["key"]
        edit = QLineEdit(field_text(value))
        edit.setReadOnly(bool(spec.get("read_only")))
        edit.editingFinished.connect(lambda: self._commit(key, parse_field(edit.text(), spec, self.helper_names)))
        self.controls[key] = edit
        return edit

    def _checkbox(self, spec, value, choices):
        key = spec["key"]
        checkbox = QCheckBox()
        checkbox.setChecked(bool(value))
        checkbox.setEnabled(not spec.get("read_only", False))
        checkbox.toggled.connect(lambda checked: self._commit(key, checked))
        self.controls[key] = checkbox
        return checkbox

    def _combo(self, spec, value, choices):
        key = spec["key"]
        combo = QComboBox()
        combo.setEditable(True)
        for choice in choices:
            combo.addItem(display_choice(key, choice), choice)
        index = combo.findData(value)
        combo.setCurrentIndex(index)
        if index < 0:
            combo.setEditText(field_text(value))
        combo.setEnabled(not spec.get("read_only", False))
        combo.currentTextChanged.connect(lambda _text: self._commit(key, combo_value(combo)))
        self.controls[key] = combo
        return combo

    def _text(self, spec, value, choices):
        key = spec["key"]
        edit = QPlainTextEdit(str(value or ""))
        edit.setMinimumHeight(120)
        edit.setReadOnly(bool(spec.get("read_only")))
        edit.textChanged.connect(lambda: self._commit(key, edit.toPlainText()))
        self.controls[key] = edit
        return edit

    def _path(self, spec, value, choices):
        key = spec["key"]
        host = QWidget()
        layout = QHBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit(str(value or ""))
        edit.setReadOnly(bool(spec.get("read_only")))
        button = QPushButton("…")
        button.setFixedWidth(28)
        button.clicked.connect(lambda: self._browse(key, spec["type"], edit))
        edit.editingFinished.connect(lambda: self._commit(key, edit.text()))
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        self.controls[key] = edit
        return host

    def _browse(self, key: str, kind: str, edit: QLineEdit) -> None:
        start = edit.text() or "."
        if kind == "dir":
            path = QFileDialog.getExistingDirectory(self, tr('ui.widgets.editor.select_directory'), start)
        else:
            path, _ = QFileDialog.getOpenFileName(
                self,
                tr('ui.widgets.editor.select_file'),
                start,
                "Mesh / geometry (*.inp *.stl *.step *.stp);;All (*)",
            )
        if path:
            edit.setText(path)
            self._commit(key, path)

    def _dofs(self, spec, value, choices):
        key = spec["key"]
        host = QWidget()
        layout = QHBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        current = set(int(index) for index in (value or []))
        boxes = []
        for index in range(int(spec.get("size", 6))):
            checkbox = QCheckBox(DOF_LABELS.get(index, str(index)))
            checkbox.setChecked(index in current)
            checkbox.toggled.connect(lambda _checked: self._commit(
                key,
                [i for i, box in enumerate(boxes) if box.isChecked()],
            ))
            boxes.append(checkbox)
            layout.addWidget(checkbox)
        layout.addStretch(1)
        self.dof_groups[key] = boxes
        self.controls[key] = host
        return host
