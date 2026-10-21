"""Shared schema form for live node fields and updater parameter dictionaries."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QWidget,
)

from ..application.values import field_text, parse_field
from ..i18n import localized_message, tr
from ..theme import theme_manager
from .file_dialogs import choose_directory, choose_open_file
from .values import DOF_LABELS, combo_value, display_choice


class ParamForm(QWidget):
    """Render a schema and write directly to its bound source; no value copy."""

    changed = Signal(str)

    def __init__(
        self,
        params: dict | None,
        fields,
        extra_choices=None,
        parent=None,
        helper_names=(),
        *,
        read: Callable[[str, object], object] | None = None,
        write: Callable[[str, object], bool | None] | None = None,
        choice_label: Callable[[str, object], str] = display_choice,
    ):
        super().__init__(parent)
        self.params = params
        self.helper_names = set(helper_names)
        self._choice_label = choice_label
        if params is None:
            if read is None or write is None:
                raise TypeError(
                    localized_message(
                        "ui.errors.param_form.bind_a_parameter_dictionary_or_provide_both_field_callbacks"
                    )
                )
            self._read, self._write = read, write
        else:
            self._read = read or params.get
            self._write = write or params.__setitem__
        self.specs = tuple(fields)
        self.controls: dict[str, QWidget] = {}
        self.dof_groups: dict[str, list[QCheckBox]] = {}
        self._form = QFormLayout(self)
        self._form.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._form.setVerticalSpacing(6)
        builders = {
            "bool": self._checkbox,
            "combo": self._combo,
            "file": self._path,
            "dir": self._path,
            "dofs": self._dofs,
            "text": self._text,
            "code": self._text,
        }
        for spec in self.specs:
            key = spec.key
            value = self._read(key, spec.new_default())
            choices = list(
                dict.fromkeys(
                    [*(spec.choices or []), *((extra_choices or {}).get(key) or [])]
                )
            )
            if spec.type == "combo" and spec.default == "" and "" not in choices:
                choices.insert(0, "")
            widget = builders.get(spec.type, self._line)(spec, value, choices)
            label = QLabel(tr(spec.label_key))
            help_text = tr(spec.doc_key) if spec.doc_key else ""
            label.setToolTip(
                "\n".join(
                    filter(
                        None,
                        (
                            tr("ui.common.parameter_key", parameter=key),
                            help_text,
                        ),
                    )
                )
            )
            widget.setToolTip(label.toolTip())
            self._form.addRow(label, widget)

    def refresh_choices(self, choices: dict) -> None:
        for spec in self.specs:
            if spec.type != "combo":
                continue
            key = spec.key
            combo = self.controls[key]
            current = self._read(key, spec.new_default())
            items = list(
                dict.fromkeys([*(spec.choices or []), *(choices.get(key) or [])])
            )
            if spec.default == "" and "" not in items:
                items.insert(0, "")
            labels = [self._choice_label(key, value) for value in items]
            if [
                (combo.itemText(i), combo.itemData(i)) for i in range(combo.count())
            ] == list(zip(labels, items)):
                continue
            combo.blockSignals(True)
            try:
                combo.clear()
                for label, value in zip(labels, items):
                    combo.addItem(label, value)
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

    def refresh_values(self) -> None:
        """Read canonical values without committing data or interrupting typing."""
        for spec in self.specs:
            key = spec.key
            control = self.controls[key]
            if control.hasFocus() or any(
                child.hasFocus() for child in control.findChildren(QWidget)
            ):
                continue
            value = self._read(key, spec.new_default())
            if key in self.dof_groups:
                for index, checkbox in enumerate(self.dof_groups[key]):
                    with QSignalBlocker(checkbox):
                        checkbox.setChecked(index in (value or []))
                continue
            with QSignalBlocker(control):
                if isinstance(control, QComboBox):
                    index = control.findData(value)
                    control.setCurrentIndex(index)
                    if index < 0:
                        control.setEditText(field_text(value))
                elif isinstance(control, QCheckBox):
                    control.setChecked(bool(value))
                elif isinstance(control, QLineEdit):
                    text = field_text(value)
                    if control.text() != text:
                        control.setText(text)
                elif isinstance(control, QPlainTextEdit):
                    text = str(value or "")
                    if control.toPlainText() != text:
                        control.setPlainText(text)

    def _line(self, spec, value, choices):
        key = spec.key
        edit = QLineEdit(field_text(value))
        edit.setReadOnly(bool(spec.read_only))
        edit.editingFinished.connect(
            lambda: self._commit(key, parse_field(edit.text(), spec, self.helper_names))
        )
        self.controls[key] = edit
        return edit

    def _checkbox(self, spec, value, choices):
        key = spec.key
        checkbox = QCheckBox()
        checkbox.setChecked(bool(value))
        checkbox.setEnabled(not spec.read_only)
        checkbox.toggled.connect(lambda checked: self._commit(key, checked))
        self.controls[key] = checkbox
        return checkbox

    def _combo(self, spec, value, choices):
        key = spec.key
        combo = QComboBox()
        combo.setEditable(True)
        for choice in choices:
            combo.addItem(self._choice_label(key, choice), choice)
        index = combo.findData(value)
        combo.setCurrentIndex(index)
        if index < 0:
            combo.setEditText(field_text(value))
        combo.setEnabled(not spec.read_only)
        combo.currentTextChanged.connect(
            lambda _text: self._commit(key, combo_value(combo))
        )
        self.controls[key] = combo
        return combo

    def _text(self, spec, value, choices):
        key = spec.key
        edit = QPlainTextEdit(str(value or ""))
        edit.setMinimumHeight(
            theme_manager.palette.layout.widgets.multiline_field_minimum_height
        )
        edit.setReadOnly(bool(spec.read_only))
        edit.textChanged.connect(lambda: self._commit(key, edit.toPlainText()))
        self.controls[key] = edit
        return edit

    def _path(self, spec, value, choices):
        key = spec.key
        host = QWidget()
        layout = QHBoxLayout(host)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        edit = QLineEdit(str(value or ""))
        edit.setReadOnly(bool(spec.read_only))
        button = QPushButton("…")
        button.setFixedWidth(theme_manager.palette.layout.widgets.path_button_width)
        button.clicked.connect(lambda: self._browse(key, spec.type, edit))
        edit.editingFinished.connect(lambda: self._commit(key, edit.text()))
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        self.controls[key] = edit
        return host

    def _browse(self, key: str, kind: str, edit: QLineEdit) -> None:
        start = edit.text() or "."
        if kind == "dir":
            path = choose_directory(
                self, tr("ui.widgets.editor.select_directory"), start
            )
        else:
            path = choose_open_file(
                self,
                tr("ui.widgets.editor.select_file"),
                start,
                tr("ui.files.mesh_and_geometry"),
            )
        if path:
            edit.setText(path)
            self._commit(key, path)

    def _dofs(self, spec, value, choices):
        key = spec.key
        host = QWidget()
        layout = QHBoxLayout(host)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        current = set(int(index) for index in (value or []))
        boxes = []
        for index in range(int(spec.size)):
            checkbox = QCheckBox(DOF_LABELS.get(index, str(index)))
            checkbox.setChecked(index in current)
            checkbox.toggled.connect(
                lambda _checked: self._commit(
                    key,
                    [i for i, box in enumerate(boxes) if box.isChecked()],
                )
            )
            boxes.append(checkbox)
            layout.addWidget(checkbox)
        layout.addStretch(1)
        self.dof_groups[key] = boxes
        self.controls[key] = host
        return host
