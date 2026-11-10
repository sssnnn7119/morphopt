"""Named component inputs for fixed vectors and extensible parameter lists."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from ..application.values import field_text, parse_field
from ..i18n import tr
from ..model.fields import FieldSpec
from ..theme import theme_manager
from .collection_controls import ActionButton, AddButton


class SequenceInput(QWidget):
    """Keep vector order in data while naming each scalar in the interface."""

    changed = Signal(object)

    def __init__(
        self, spec: FieldSpec, value: object, helper_names=(), parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.spec = spec
        self.helper_names = tuple(sorted(helper_names))
        suffix = spec.type.removeprefix("vec")
        self._size = int(suffix) if suffix.isdigit() else None
        self._values: list[object] = []
        self._reference: str | None = None
        self.edits: list[QLineEdit] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        layout.setSpacing(theme_manager.palette.layout.widgets.standard_form_spacing)
        self.reference = QComboBox()
        self.reference.addItem(tr("ui.parameters.by_components"), None)
        for name in self.helper_names:
            self.reference.addItem(name, name)
        self.reference.currentIndexChanged.connect(self._select_reference)
        layout.addWidget(self.reference)
        self.body = QWidget()
        self.grid = QGridLayout(self.body)
        self.grid.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self.grid.setSpacing(theme_manager.palette.layout.widgets.standard_form_spacing)
        layout.addWidget(self.body)
        self.add_button = AddButton(self._add)
        layout.addWidget(self.add_button)
        self.set_value(value)
        self.setEnabled(not spec.read_only)

    def set_value(self, value: object) -> None:
        reference = value if isinstance(value, str) else None
        values = list(value) if isinstance(value, (list, tuple)) else self.spec.new_default()
        if not isinstance(values, list):
            values = []
        if self._size is not None:
            defaults = self.spec.new_default()
            defaults = defaults if isinstance(defaults, list) else [0.0] * self._size
            defaults = [*defaults, *([0.0] * self._size)]
            values = [values[i] if i < len(values) else defaults[i] for i in range(self._size)]
        if values != self._values or not self.edits and values:
            self._values = values
            self._rebuild()
        self._reference = reference
        with QSignalBlocker(self.reference):
            if reference is not None and self.reference.findData(reference) < 0:
                self.reference.addItem(reference, reference)
            self.reference.setCurrentIndex(max(0, self.reference.findData(reference)))
        self.reference.setVisible(bool(self.helper_names) or reference is not None)
        self.body.setEnabled(reference is None)
        self.add_button.setVisible(self._size is None and reference is None)

    def _rebuild(self) -> None:
        while self.grid.count():
            widget = self.grid.takeAt(0).widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self.edits.clear()
        style = theme_manager.palette.layout.widgets
        columns = style.bounds_columns if self.spec.key == "bounding_box" else style.sequence_columns
        columns = min(columns, max(1, len(self._values)))
        for index, value in enumerate(self._values):
            host = QWidget()
            column = QVBoxLayout(host)
            column.setContentsMargins(*theme_manager.palette.layout.zero_margins)
            column.setSpacing(style.standard_form_spacing)
            title = (
                tr(self.spec.components[index]) if index < len(self.spec.components)
                else tr("ui.parameters.item", parameter=tr(self.spec.label_key), index=index)
            )
            label = QLabel(title)
            column.addWidget(label)
            row = QHBoxLayout()
            row.setSpacing(style.standard_form_spacing)
            edit = QLineEdit(field_text(value))
            edit.setMinimumWidth(style.sequence_input_minimum_width)
            edit.setAccessibleName(title)
            label.setBuddy(edit)
            edit.editingFinished.connect(self._commit)
            self.edits.append(edit)
            row.addWidget(edit, 1)
            if self._size is None:
                row.addWidget(ActionButton(
                    "×", lambda i=index: self._remove(i),
                    tooltip=tr("ui.common.delete"), danger=True,
                ))
            column.addLayout(row)
            self.grid.addWidget(host, index // columns, index % columns)
        for column in range(style.sequence_columns):
            self.grid.setColumnStretch(column, int(column < columns))

    def value(self) -> list[object] | str:
        if self._reference is not None:
            return self._reference
        scalar = replace(
            self.spec, type="int" if self.spec.ints else self.spec.item_type,
        )
        return [parse_field(edit.text(), scalar, self.helper_names) for edit in self.edits]

    def _commit(self) -> None:
        if self._reference is not None:
            return
        self._values = self.value()
        self.changed.emit(list(self._values))

    def _select_reference(self) -> None:
        self._reference = self.reference.currentData()
        self.body.setEnabled(self._reference is None)
        self.add_button.setVisible(self._size is None and self._reference is None)
        self.changed.emit(self.value())

    def _add(self) -> None:
        self._values = [*self.value(), "" if self.spec.item_type == "str" else 0.0]
        self._rebuild()
        self.changed.emit(list(self._values))
        self.edits[-1].setFocus()

    def _remove(self, index: int) -> None:
        self._values = list(self.value())
        self._values.pop(index)
        self._rebuild()
        self.changed.emit(list(self._values))
