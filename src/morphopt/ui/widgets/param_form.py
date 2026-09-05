"""Generic inline parameter form editing a plain ``params`` dict.

Used by the structured updater editor and other "pick an item + tweak its
parameters" panels.  All edits are written straight into the passed dict
(auto-apply) and emit a change signal.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QComboBox, QCheckBox, QSpinBox,
    QPushButton, QHBoxLayout, QFileDialog,
)

from ..model.schemas import fld, clone_defaults
from .values import parse_vec_text, parse_mat, DOF_LABELS


def _text_of(value) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(_text_of(v) for v in value)
    return str(value)


class ParamForm(QWidget):
    """Compact form of field specs editing a live ``params`` dict."""

    changed = Signal(str)   # key

    def __init__(self, params: dict, fields, extra_choices=None, parent=None):
        super().__init__(parent)
        self.params = params
        self.fields = list(fields)
        self.extra_choices = extra_choices or {}
        self._form = QFormLayout(self)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._form.setVerticalSpacing(3)
        self._controls = {}
        self._dof_groups: dict[str, list[QCheckBox]] = {}
        self._rebuild()

    def _rebuild(self) -> None:
        for f in self.fields:
            key = f["key"]
            value = self.params.get(key, f["default"])
            self._add(f, value)

    # ------------------------------------------------------------ fields
    def _add(self, f: dict, cur) -> None:
        key = f["key"]
        typ = f["type"]
        label = f["label"]
        if typ == "bool":
            w = QCheckBox(label)
            w.setChecked(bool(cur))
            w.toggled.connect(lambda v, k=key: self._set(k, bool(v)))
            self._form.addRow(w)
            return
        if typ == "int":
            w = QSpinBox()
            lo = f.get("min")
            hi = f.get("max")
            w.setRange(int(lo) if lo is not None else -10**6,
                       int(hi) if hi is not None else 10**6)
            w.setValue(int(cur) if cur is not None else 0)
            w.valueChanged.connect(lambda v, k=key: self._set(k, int(v)))
            self._form.addRow(label, w)
            return
        if typ == "combo":
            w = QComboBox()
            w.setEditable(True)
            items = list(f.get("choices") or []) + list(self.extra_choices.get(key) or [])
            for it in items:
                w.addItem(str(it))
            w.setCurrentText(str(cur) if cur is not None else "")
            w.editTextChanged.connect(lambda t, k=key: self._set(k, str(t)))
            self._form.addRow(label, w)
            return
        if typ == "file":
            edit = QLineEdit(str(cur or ""))
            btn = QPushButton("…")
            btn.setFixedWidth(28)
            btn.clicked.connect(lambda: self._browse(edit, key))
            lay = QHBoxLayout()
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(edit, 1)
            lay.addWidget(btn)
            edit.editingFinished.connect(lambda k=key: self._set(k, edit.text()))
            self._form.addRow(label, self._host(lay))
            return
        if typ == "dofs":
            host = QWidget()
            h = QHBoxLayout(host)
            h.setContentsMargins(0, 0, 0, 0)
            n = int(f.get("size", 6))
            current = set(int(x) for x in (cur or []))
            boxes: list[QCheckBox] = []
            for i in range(n):
                cb = QCheckBox(DOF_LABELS.get(i, str(i)))
                cb.setChecked(i in current)
                cb.toggled.connect(lambda _=False, k=key: self._sync_dofs(k))
                h.addWidget(cb)
                boxes.append(cb)
            h.addStretch(1)
            self._dof_groups[key] = boxes
            self._form.addRow(label, host)
            return
        # line-edit typed fields
        w = QLineEdit()
        if typ == "float":
            from PySide6.QtGui import QDoubleValidator
            w.setValidator(QDoubleValidator())
            w.setText(str(cur) if cur is not None else "")
            w.editingFinished.connect(lambda k=key: self._set(k, _to_float(w.text())))
        elif typ in ("mat", "vecN", "vec3", "vec6", "vec2d"):
            w.setText(_text_of(cur) if cur is not None else "")
            keep_int = bool(f.get("ints", False))
            w.editingFinished.connect(
                lambda k=key: self._set(k, parse_mat(w.text()) if typ == "mat"
                                        else parse_vec_text(w.text(), ints=keep_int)))
        else:  # str / text
            w.setText(str(cur) if cur is not None else "")
            w.editingFinished.connect(lambda k=key: self._set(k, w.text()))
        self._form.addRow(label, w)

    def _host(self, lay) -> QWidget:
        w = QWidget()
        w.setLayout(lay)
        return w

    def _browse(self, edit: QLineEdit, key: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择文件", edit.text() or ".")
        if path:
            edit.setText(path)
            self._set(key, path)

    def _set(self, key: str, value) -> None:
        self.params[key] = value
        self.changed.emit(key)

    def _sync_dofs(self, key: str) -> None:
        boxes = self._dof_groups.get(key, [])
        vals = sorted(i for i, cb in enumerate(boxes) if cb.isChecked())
        self._set(key, vals)


def _to_float(text: str):
    try:
        return float(text)
    except ValueError:
        return text
