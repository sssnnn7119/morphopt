"""Design-intent Quickstart dialog; detailed model editing stays in Workbench."""

from __future__ import annotations

from copy import deepcopy

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...constants import CONSTANT
from ..application.quickstart import (
    GOALS,
    ObjectiveDraft,
    QuickstartOptions,
    available_objectives,
    build_quickstart,
    select_workspace_channels,
)
from ..codegen.generator import generate_source
from ..i18n import tr
from ..model.chamberlayout import ChamberLayer
from ..presentation.labels import quickstart_summary
from ..theme import theme_manager
from ..visualization.geometry import InitialDesignGeometry
from .collection_controls import ActionButton, CollectionHeader, ItemActions
from .file_dialogs import choose_directory


class ChamberLayersEditor(QWidget):
    """Rows define serial layers; cavity count and arrangement define parallelism."""

    changed = Signal()

    def __init__(self, layers, parent=None):
        super().__init__(parent)
        self._loading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        header = CollectionHeader("", self._add)
        self.add_button = header.add_button
        self.add_button.setToolTip(tr("ui.widgets.quickstart.add_layer"))
        self.row_actions = ItemActions(-1, 0, self._remove, self._move)
        header.actions.addWidget(self.row_actions)
        layout.addWidget(header)
        hint = QLabel(
            tr(
                "ui.widgets.quickstart.layers_run_from_base_to_tip_along_z_equal_channel_numbers_share_pressure"
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                tr("ui.widgets.quickstart.length_mm_30b65866"),
                tr("ui.widgets.quickstart.cavities"),
                tr("ui.widgets.quickstart.arrangement"),
                tr("ui.widgets.quickstart.radius_mm"),
                tr("ui.widgets.quickstart.center_mm"),
                tr("ui.widgets.quickstart.shape"),
                tr("ui.widgets.quickstart.phase"),
                tr("ui.widgets.quickstart.channels"),
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setMinimumHeight(
            theme_manager.palette.layout.quickstart.layer_table_minimum_height
        )
        self.table.cellChanged.connect(self._cell_changed)
        self.table.itemSelectionChanged.connect(self._update_actions)
        layout.addWidget(self.table)
        self.set_layers(layers or [ChamberLayer()])

    def set_layers(self, layers):
        self._loading = True
        self.table.setRowCount(0)
        for layer in layers:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                f"{layer.length:g}",
                str(layer.chambers),
                layer.arrangement,
                f"{layer.radius:g}",
                f"{layer.center_radius:g}",
                layer.shape,
                f"{layer.phase_degrees:g}",
                ",".join(
                    map(
                        str,
                        layer.pressure_channels,
                    )
                ),
            ]
            for column, value in enumerate(values):
                if column in (2, 5):
                    combo = QComboBox()
                    choices = (
                        [
                            ("ring", tr("ui.widgets.quickstart.ring")),
                            ("line", tr("ui.widgets.quickstart.line")),
                        ]
                        if column == 2
                        else [
                            ("cylinder", tr("ui.widgets.quickstart.cylinder")),
                            ("sphere", tr("ui.widgets.quickstart.sphere")),
                        ]
                    )
                    for key, caption in choices:
                        combo.addItem(caption, key)
                    combo.setCurrentIndex(combo.findData(value))
                    combo.currentIndexChanged.connect(lambda *_: self.changed.emit())
                    self.table.setCellWidget(row, column, combo)
                else:
                    self.table.setItem(row, column, QTableWidgetItem(value))
        self._loading = False
        self._update_actions()

    def _update_actions(self) -> None:
        count = self.table.rowCount()
        self.row_actions.set_position(
            self.table.currentRow(), count, allow_remove=count > 1
        )
        self.add_button.setEnabled(
            count < CONSTANT.UI.QUICKSTART.LIMITS.LAYER_MAX_COUNT
        )

    def layers(self):
        layers = []
        try:
            for row in range(self.table.rowCount()):
                value = lambda column: self.table.item(row, column).text().strip()
                layers.append(
                    ChamberLayer(
                        length=float(value(0)),
                        chambers=int(value(1)),
                        arrangement=self.table.cellWidget(row, 2).currentData(),
                        radius=float(value(3)),
                        center_radius=float(value(4)),
                        shape=self.table.cellWidget(row, 5).currentData(),
                        phase_degrees=float(value(6)),
                        pressure_channels=[int(c.strip()) for c in value(7).split(",")],
                    )
                )
        except ValueError as exc:
            raise ValueError(
                tr(
                    "ui.widgets.quickstart.enter_valid_layer_parameters_separate_channel_numbers_with_commas"
                )
            ) from exc
        return layers

    def _cell_changed(self, row, column):
        if self._loading:
            return
        if column == 1:
            try:
                count = int(self.table.item(row, 1).text())
                channels = [int(c) for c in self.table.item(row, 7).text().split(",")]
            except ValueError:
                self.changed.emit()
                return
            if (
                channels == list(range(1, len(channels) + 1))
                and 1 <= count <= CONSTANT.UI.QUICKSTART.LIMITS.CHAMBER_MAX_COUNT
            ):
                self._loading = True
                self.table.item(row, 7).setText(
                    ",".join(str(c) for c in range(1, count + 1))
                )
                self._loading = False
        self.changed.emit()

    def _add(self):
        try:
            layers = self.layers()
        except ValueError:
            self.changed.emit()
            return
        if len(layers) < CONSTANT.UI.QUICKSTART.LIMITS.LAYER_MAX_COUNT:
            layers.append(
                ChamberLayer(length=CONSTANT.UI.QUICKSTART.WIDGET.LAYER_ADDED_LENGTH)
            )
            self.set_layers(layers)
            self.table.selectRow(len(layers) - 1)
            self.changed.emit()

    def _remove(self):
        if self.table.rowCount() > 1:
            row = self.table.currentRow()
            self.table.removeRow(row if row >= 0 else self.table.rowCount() - 1)
            self._update_actions()
            self.changed.emit()

    def _move(self, delta):
        row = self.table.currentRow()
        target = row + delta
        if row < 0 or not 0 <= target < self.table.rowCount():
            return
        try:
            layers = self.layers()
        except ValueError:
            self.changed.emit()
            return
        layers[row], layers[target] = layers[target], layers[row]
        self.set_layers(layers)
        self.table.selectRow(target)
        self.changed.emit()


class WorkspaceChannelSelector(QWidget):
    """Select independent pressure channels and show the cavities they drive."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False
        self._required = None
        self._channels = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.list = QListWidget()
        self.list.setMaximumHeight(
            theme_manager.palette.layout.quickstart.workspace_channel_list_maximum_height
        )
        self.list.itemChanged.connect(self._item_changed)
        layout.addWidget(self.list)

    def set_channels(self, members, required=None, selected=()):
        available = sorted(members)
        chosen = [channel for channel in selected if channel in members]
        context_changed = required != self._required or available != self._channels
        if required is not None and context_changed:
            chosen = select_workspace_channels(members, chosen, required)
        self._required = required
        self._channels = available
        self._updating = True
        self.list.clear()
        for channel in available:
            cavities = ", ".join(map(str, members[channel]))
            item = QListWidgetItem(
                tr(
                    "ui.widgets.quickstart.channel_value_chambers_value",
                    value_0=channel,
                    value_1=cavities,
                )
            )
            item.setData(Qt.ItemDataRole.UserRole, channel)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if channel in chosen else Qt.CheckState.Unchecked
            )
            self.list.addItem(item)
        if required is None:
            self.hint.setText(
                tr(
                    "ui.widgets.quickstart.chambers_on_the_same_pressure_channel_move_together"
                )
            )
        else:
            self.hint.setText(
                tr(
                    "ui.widgets.quickstart.select_value_independent_inputs_chambers_on_one_channel_move_together",
                    value_0=required,
                )
            )
        self._updating = False

    def selected_channels(self):
        return [
            self.list.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.list.count())
            if self.list.item(index).checkState() == Qt.CheckState.Checked
        ]

    def _item_changed(self, item):
        if self._updating:
            return
        if (
            self._required is not None
            and item.checkState() == Qt.CheckState.Checked
            and len(self.selected_channels()) > self._required
        ):
            self._updating = True
            item.setCheckState(Qt.CheckState.Unchecked)
            self._updating = False
            return
        self.changed.emit()


class ChannelPressureEditor(QWidget):
    """Edit one explicit pressure value per independent geometry channel."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.form = QFormLayout(self)
        self.form.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self.fields = {}
        self._updating = False

    def set_channels(self, members, pressures):
        self._updating = True
        while self.form.rowCount():
            self.form.removeRow(0)
        self.fields.clear()
        for channel in sorted(members):
            cavities = ", ".join(map(str, members[channel]))
            spin = QDoubleSpinBox()
            spin.setRange(0.0, CONSTANT.UI.QUICKSTART.WIDGET.PRESSURE_MAX_KPA)
            spin.setDecimals(CONSTANT.UI.QUICKSTART.WIDGET.PRESSURE_DECIMALS)
            spin.setSingleStep(
                CONSTANT.UI.QUICKSTART.WIDGET.NUMERIC_FIELD_STEP.PRESSURE_KPA
            )
            spin.setSuffix(" kPa")
            value = pressures.get(channel, pressures.get(str(channel), 0.0))
            spin.setValue(float(value))
            spin.valueChanged.connect(self._value_changed)
            self.fields[channel] = spin
            self.form.addRow(
                QLabel(
                    tr(
                        "ui.widgets.quickstart.channel_value_chambers_value",
                        value_0=channel,
                        value_1=cavities,
                    )
                ),
                spin,
            )
        self._updating = False

    def values(self):
        return {channel: spin.value() for channel, spin in self.fields.items()}

    def _value_changed(self, *_):
        if not self._updating:
            self.changed.emit()


class ObjectiveListEditor(QWidget):
    """Multi-objective editor with a load condition attached to each term."""

    changed = Signal()

    def __init__(self, objectives, method, channel_members, parent=None):
        super().__init__(parent)
        self.draft = ObjectiveDraft(objectives, method, channel_members)
        self._current_index = -1
        self._updating = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        header = CollectionHeader("", self._add)
        self.add_button = header.add_button
        self.add_button.setToolTip(tr("ui.widgets.quickstart.add_objective"))
        self.remove_button = ActionButton(
            tr("ui.common.delete"),
            self._remove,
            danger=True,
            tooltip=tr("ui.widgets.quickstart.remove_objective"),
        )
        header.actions.addWidget(self.remove_button)
        outer.addWidget(header)
        self.list = QListWidget()
        self.list.setMinimumHeight(
            theme_manager.palette.layout.quickstart.objective_list_minimum_height
        )
        self.list.setMaximumHeight(
            theme_manager.palette.layout.quickstart.objective_list_maximum_height
        )
        self.list.currentRowChanged.connect(self._selection_changed)
        outer.addWidget(self.list)

        self.detail = QWidget()
        self.form = QFormLayout(self.detail)
        outer.addWidget(self.detail)
        self.kind = QComboBox()
        self.weight = QDoubleSpinBox()
        self.weight.setRange(
            0.0, CONSTANT.UI.QUICKSTART.WIDGET.OBJECTIVE_WEIGHT_MAXIMUM
        )
        self.weight.setDecimals(CONSTANT.UI.QUICKSTART.WIDGET.OBJECTIVE_WEIGHT_DECIMALS)
        self.weight.setValue(CONSTANT.UI.QUICKSTART.DEFAULT.OBJECTIVE_WEIGHT)
        self.target = QDoubleSpinBox()
        self.target.setRange(
            CONSTANT.UI.QUICKSTART.WIDGET.OBJECTIVE_TARGET_MINIMUM,
            CONSTANT.UI.QUICKSTART.WIDGET.OBJECTIVE_TARGET_MAXIMUM,
        )
        self.target.setDecimals(CONSTANT.UI.QUICKSTART.WIDGET.OBJECTIVE_TARGET_DECIMALS)
        self.force = QDoubleSpinBox()
        self.force.setRange(
            CONSTANT.UI.QUICKSTART.WIDGET.FORCE_MINIMUM,
            CONSTANT.UI.QUICKSTART.WIDGET.FORCE_MAXIMUM,
        )
        self.force.setDecimals(CONSTANT.UI.QUICKSTART.WIDGET.FORCE_DECIMALS)
        self.workspace_pressure = QDoubleSpinBox()
        self.workspace_pressure.setRange(
            CONSTANT.UI.QUICKSTART.WIDGET.WORKSPACE_PRESSURE_MINIMUM,
            CONSTANT.UI.QUICKSTART.WIDGET.WORKSPACE_PRESSURE_MAXIMUM,
        )
        self.workspace_pressure.setDecimals(
            CONSTANT.UI.QUICKSTART.WIDGET.WORKSPACE_PRESSURE_DECIMALS
        )
        self.workspace_pressure.setSingleStep(
            CONSTANT.UI.QUICKSTART.WIDGET.NUMERIC_FIELD_STEP.PRESSURE_KPA
        )
        self.workspace_order = QSpinBox()
        self.workspace_order.setRange(
            CONSTANT.UI.QUICKSTART.LIMITS.WORKSPACE_GAUSS_ORDER_MIN,
            CONSTANT.UI.QUICKSTART.LIMITS.WORKSPACE_GAUSS_ORDER_MAX,
        )
        self.pressures = ChannelPressureEditor()
        self.workspace_inputs = WorkspaceChannelSelector()
        self.kind_caption = self._add_row(
            "kind", tr("ui.widgets.quickstart.objective_type"), self.kind
        )
        self.weight_caption = self._add_row(
            "weight", tr("ui.widgets.quickstart.weight"), self.weight
        )
        self.target_caption = self._add_row(
            "target", tr("ui.widgets.quickstart.target"), self.target
        )
        self.force_caption = self._add_row(
            "force", tr("ui.widgets.quickstart.load_z_n"), self.force
        )
        self.pressure_caption = self._add_row(
            "pressures",
            tr("ui.widgets.quickstart.pressure_load_case"),
            self.pressures,
        )
        self.workspace_caption = self._add_row(
            "workspace_channels",
            tr("ui.widgets.quickstart.workspace_drives"),
            self.workspace_inputs,
        )
        self.workspace_pressure_caption = self._add_row(
            "workspace_pressure",
            tr("ui.widgets.quickstart.workspace_max_pressure_kpa"),
            self.workspace_pressure,
        )
        self.workspace_order_caption = self._add_row(
            "workspace_order",
            tr("ui.widgets.quickstart.boundary_gauss_points_free_axis"),
            self.workspace_order,
        )
        self.workspace_note = QLabel(
            tr(
                "ui.widgets.quickstart.workspace_has_no_manually_selected_load_case_boundary_integration_cases"
            )
        )
        self.workspace_note.setWordWrap(True)
        self.form.addRow(self.workspace_note)

        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.weight.valueChanged.connect(self._details_changed)
        self.target.valueChanged.connect(self._details_changed)
        self.force.valueChanged.connect(self._details_changed)
        self.workspace_pressure.valueChanged.connect(self._details_changed)
        self.workspace_order.valueChanged.connect(self._details_changed)
        self.pressures.changed.connect(self._details_changed)
        self.workspace_inputs.changed.connect(self._details_changed)
        self._refresh_list()
        if self.draft.objectives:
            self.list.setCurrentRow(0)
        self._update_buttons()

    def _add_row(self, key, text, widget):
        caption = QLabel(text)
        self.form.addRow(caption, widget)
        return caption

    def _refresh_list(self):
        self._updating = True
        self.list.clear()
        for objective in self.draft.objectives:
            self.list.addItem(self._objective_label(objective))
        self._updating = False

    def _objective_label(self, objective):
        label = tr(GOALS[objective.kind][0])
        if self.draft.method == "simp" and objective.kind == "bend":
            label = tr("ui.widgets.quickstart.target_tip_deflection")
        return tr("ui.quickstart.objective_title", label=label, weight=objective.weight)

    def _update_list_item(self, row):
        if 0 <= row < len(self.draft.objectives) and self.list.item(row) is not None:
            self.list.item(row).setText(
                self._objective_label(self.draft.objectives[row])
            )

    def _update_buttons(self):
        self.add_button.setEnabled(
            len(self.draft.objectives)
            < CONSTANT.UI.QUICKSTART.LIMITS.OBJECTIVE_MAX_COUNT
        )
        self.remove_button.setEnabled(bool(self.draft.objectives))

    def _save_current(self):
        if not 0 <= self._current_index < len(self.draft.objectives):
            return
        objective = self.draft.objectives[self._current_index]
        objective.kind = self.kind.currentData() or objective.kind
        objective.weight = self.weight.value()
        objective.target = self.target.value()
        objective.force_n = self.force.value()
        objective.pressures_kpa = self.pressures.values()
        objective.workspace_channels = self.workspace_inputs.selected_channels()
        objective.workspace_pressure_kpa = self.workspace_pressure.value()
        objective.gauss_order = self.workspace_order.value()

    def _load_current(self):
        row = self.list.currentRow()
        self._current_index = row
        if not 0 <= row < len(self.draft.objectives):
            self.detail.hide()
            return
        objective = self.draft.objectives[row]
        self._updating = True
        self.kind.clear()
        for kind in available_objectives(self.draft.method):
            label = tr(GOALS[kind][0])
            if self.draft.method == "simp" and kind == "bend":
                label = tr("ui.widgets.quickstart.target_tip_deflection")
            self.kind.addItem(label, kind)
        self.kind.setCurrentIndex(max(0, self.kind.findData(objective.kind)))
        self.weight.setValue(objective.weight)
        self.target.setValue(objective.target)
        self.force.setValue(objective.force_n)
        self.workspace_pressure.setValue(objective.workspace_pressure_kpa)
        self.workspace_order.setValue(objective.gauss_order)
        self.pressures.set_channels(self.draft.members, objective.pressures_kpa)
        dimensions = len(GOALS[objective.kind][1]) if objective.is_workspace else None
        self.workspace_inputs.set_channels(
            self.draft.members, dimensions, objective.workspace_channels
        )
        self._updating = False
        self.detail.show()
        self._set_detail_visibility(objective)
        self._update_buttons()

    def _set_detail_visibility(self, objective):
        workspace = objective.is_workspace
        shape = self.draft.method == "shapeopt"
        target_visible = not workspace and objective.kind != "stiffness"
        target_unit = (
            "°"
            if objective.kind == "twist"
            else "N"
            if objective.kind == "contact"
            else "mm"
        )
        self.target_caption.setText(
            tr("ui.widgets.quickstart.target_value", value_0=target_unit)
        )
        self.target_caption.setVisible(target_visible)
        self.target.setVisible(target_visible)
        self.force_caption.setVisible(not shape)
        self.force.setVisible(not shape)
        self.pressure_caption.setVisible(shape and not workspace)
        self.pressures.setVisible(shape and not workspace)
        self.workspace_caption.setVisible(shape and workspace)
        self.workspace_inputs.setVisible(shape and workspace)
        self.workspace_pressure_caption.setVisible(shape and workspace)
        self.workspace_pressure.setVisible(shape and workspace)
        self.workspace_order_caption.setVisible(shape and workspace)
        self.workspace_order.setVisible(shape and workspace)
        self.workspace_note.setVisible(shape and workspace)

    def _selection_changed(self, row):
        if self._updating:
            return
        self._save_current()
        self._load_current()

    def _kind_changed(self, *_):
        if self._updating:
            return
        self._save_current()
        self._load_current()
        self._update_list_item(self._current_index)
        self._update_buttons()
        self.changed.emit()

    def _details_changed(self, *_):
        if self._updating:
            return
        self._save_current()
        self._update_list_item(self._current_index)
        self._update_buttons()
        self.changed.emit()

    def _add(self):
        if (
            len(self.draft.objectives)
            >= CONSTANT.UI.WIDGETS.MAXIMUM_QUICKSTART_OBJECTIVES
        ):
            return
        self._save_current()
        self.draft.add()
        self._refresh_list()
        self.list.setCurrentRow(len(self.draft.objectives) - 1)
        self._update_buttons()
        self.changed.emit()

    def _remove(self):
        if not 0 <= self.list.currentRow() < len(self.draft.objectives):
            return
        index = self.list.currentRow()
        self._save_current()
        self.draft.remove(index)
        self._current_index = -1
        self._refresh_list()
        self.list.setCurrentRow(min(index, len(self.draft.objectives) - 1))
        self._load_current()
        self._update_buttons()
        self.changed.emit()

    def set_method(self, method):
        if method == self.draft.method:
            return
        self._save_current()
        self.draft.set_method(method)
        self._refresh_list()
        selected = min(max(self._current_index, 0), len(self.draft.objectives) - 1)
        self._updating = True
        self.list.setCurrentRow(selected)
        self._updating = False
        self._load_current()

    def set_geometry_channels(self, members):
        members = {key: list(value) for key, value in members.items()}
        if members == self.draft.members:
            return
        self._save_current()
        self.draft.set_channels(members)
        self._load_current()

    def values(self):
        self._save_current()
        return self.draft.values()


class InitialDesignPreview(QWidget):
    """Orthographic isometric rendering of initial meshes supplied by the kernel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(
            *deepcopy(theme_manager.palette.quickstart_preview.minimum_size)
        )
        self.options = QuickstartOptions()
        self.geometry = None
        unsubscribe = theme_manager.subscribe(self._apply_theme)
        self.destroyed.connect(lambda *_args: unsubscribe())

    def set_options(self, options):
        self.options = options
        try:
            self.geometry = InitialDesignGeometry(options)
        except ValueError:
            self.geometry = None
        self.update()

    def _apply_theme(self, _name: str) -> None:
        self.setMinimumSize(*theme_manager.palette.quickstart_preview.minimum_size)
        if self.geometry is not None:
            self.set_options(self.options)
        else:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(
            self.rect(), QColor(theme_manager.palette.quickstart_preview.background)
        )
        painter.setPen(QColor(theme_manager.palette.quickstart_preview.heading))
        painter.drawText(
            *deepcopy(theme_manager.palette.quickstart_preview.heading_position),
            tr("ui.widgets.quickstart.initial_design_isometric_projection"),
        )
        if self.geometry is not None:
            scale, shift = self.geometry.transform(self.width(), self.height())
            painter.setPen(Qt.PenStyle.NoPen)
            for _depth, points, color, shade, alpha in self.geometry.triangles:
                brush = QColor(color).lighter(shade)
                brush.setAlpha(alpha)
                painter.setBrush(brush)
                uv = scale * points + shift
                painter.drawPolygon(
                    QPolygonF([QPointF(float(x), float(y)) for x, y in uv])
                )
            painter.setPen(
                QPen(
                    QColor(theme_manager.palette.quickstart_preview.edge),
                    theme_manager.palette.quickstart_preview.edge_width,
                )
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for line in self.geometry.lines:
                painter.drawPolyline(
                    QPolygonF(
                        [QPointF(float(x), float(y)) for x, y in scale * line + shift]
                    )
                )
        origin_x, origin_bottom = deepcopy(
            theme_manager.palette.quickstart_preview.axis_origin
        )
        origin = QPointF(origin_x, self.height() - origin_bottom)
        axis_colors = deepcopy(theme_manager.palette.quickstart_preview.axis_colors)
        axis_labels = deepcopy(theme_manager.palette.quickstart_preview.axis_labels)
        for vector, label, color in zip(
            (np.eye(3)[0], np.eye(3)[1], np.eye(3)[2]), axis_labels, axis_colors
        ):
            delta = QPointF(
                float(
                    theme_manager.palette.quickstart_preview.axis_length
                    * vector
                    @ InitialDesignGeometry.horizontal
                ),
                float(
                    theme_manager.palette.quickstart_preview.axis_length
                    * vector
                    @ InitialDesignGeometry.vertical
                ),
            )
            end = origin + delta
            painter.setPen(
                QPen(QColor(color), theme_manager.palette.quickstart_preview.axis_width)
            )
            painter.drawLine(origin, end)
            painter.drawText(end + QPointF(3, -3), label)
        painter.setPen(QColor(theme_manager.palette.quickstart_preview.text))
        caption = tr(
            "ui.widgets.quickstart.length_value_mm", value_0=self.options.total_length
        )
        if self.options.method == "shapeopt":
            caption += tr(
                "ui.widgets.quickstart.value_layers_value_cavities",
                value_0=len(self.options.layers),
                value_1=self.options.chambers,
            )
        caption_inset = deepcopy(theme_manager.palette.quickstart_preview.caption_inset)
        painter.drawText(
            QRectF(
                caption_inset[0],
                self.height() - caption_inset[1],
                self.width() - caption_inset[2],
                caption_inset[3],
            ),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            caption,
        )


class QuickstartDialog(QDialog):
    def __init__(self, problem=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("ui.widgets.quickstart.quickstart"))
        self.resize(*deepcopy(theme_manager.palette.layout.quickstart.dialog_size))
        self.problem = None
        initial = (
            QuickstartOptions.from_problem(problem) if problem else QuickstartOptions()
        )
        if problem:
            initial.result_folder = problem.result_folder
            initial.label = problem.label
        self._loading = True
        self.fields = {}
        self._rows = []
        outer = QVBoxLayout(self)
        title = QLabel(tr("ui.widgets.quickstart.start_with_the_motion_you_want"))
        title.setProperty("textRole", "dialogTitle")
        outer.addWidget(title)
        description = QLabel(
            tr(
                "ui.widgets.quickstart.describe_the_starting_structure_and_goal_to_create_an_editable_optimizat"
            )
        )
        description.setWordWrap(True)
        outer.addWidget(description)
        columns = QHBoxLayout()
        content = QWidget()
        left = QVBoxLayout(content)
        left.setContentsMargins(
            0, 0, theme_manager.palette.layout.quickstart.left_column_right_margin, 0
        )
        task = self._group(left, tr("ui.widgets.quickstart.1_choose_a_design_task"))
        self._combo(
            task,
            "method",
            tr("ui.widgets.quickstart.optimization_method"),
            [
                ("shapeopt", tr("ui.widgets.quickstart.shape_optimization")),
                ("simp", tr("ui.widgets.quickstart.topology_optimization")),
            ],
        )
        geometry = self._group(left, tr("ui.widgets.quickstart.2_define_geometry"))
        self._double(
            geometry,
            "length",
            tr("ui.widgets.quickstart.length_mm"),
            initial.length,
            *deepcopy(CONSTANT.UI.QUICKSTART.WIDGET.FIELDS.LENGTH.RANGE),
        )
        self._double(
            geometry,
            "radius",
            tr("ui.widgets.quickstart.body_radius_mm"),
            initial.radius,
            *deepcopy(CONSTANT.UI.QUICKSTART.WIDGET.FIELDS.RADIUS.RANGE),
            group="shape",
        )
        self.layers_editor = ChamberLayersEditor(initial.layers)
        self.layers_editor.changed.connect(self._refresh)
        layer_caption = QLabel(
            tr("ui.widgets.quickstart.serial_layers_parallel_cavities")
        )
        geometry.addRow(layer_caption)
        geometry.addRow(self.layers_editor)
        self._rows.append(("layers", layer_caption, self.layers_editor, "shape"))
        self._double(
            geometry,
            "wall",
            tr("ui.widgets.quickstart.minimum_wall_mm"),
            initial.wall,
            *deepcopy(CONSTANT.UI.QUICKSTART.WIDGET.FIELDS.WALL.RANGE),
            group="shape",
        )
        self._double(
            geometry,
            "height",
            tr("ui.widgets.quickstart.domain_height_mm"),
            initial.height,
            *deepcopy(CONSTANT.UI.QUICKSTART.WIDGET.FIELDS.HEIGHT.RANGE),
            group="topology",
        )
        self._double(
            geometry,
            "depth",
            tr("ui.widgets.quickstart.domain_depth_mm"),
            initial.depth,
            *deepcopy(CONSTANT.UI.QUICKSTART.WIDGET.FIELDS.DEPTH.RANGE),
            group="topology",
        )
        self._double(
            geometry,
            "mesh_size",
            tr("ui.widgets.quickstart.mesh_size_mm"),
            initial.mesh_size,
            *deepcopy(CONSTANT.UI.QUICKSTART.WIDGET.FIELDS.MESH_SIZE.RANGE),
        )
        self._check(
            geometry,
            "optimize_outer",
            tr("ui.widgets.quickstart.optimize_inner_and_outer_profiles_on_by_default"),
            group="shape",
        )

        material = self._group(left, tr("ui.widgets.quickstart.3_material_properties"))
        self._double(
            material,
            "mu",
            tr("ui.widgets.quickstart.shear_modulus_mpa"),
            initial.mu,
            *deepcopy(CONSTANT.UI.QUICKSTART.WIDGET.FIELDS.MU.RANGE),
        )
        self._double(
            material,
            "kappa",
            tr("ui.widgets.quickstart.bulk_modulus_mpa"),
            initial.kappa,
            *deepcopy(CONSTANT.UI.QUICKSTART.WIDGET.FIELDS.KAPPA.RANGE),
        )

        objective_group = QGroupBox(tr("ui.widgets.quickstart.4_define_objectives"))
        objective_layout = QVBoxLayout(objective_group)
        self.objectives_editor = ObjectiveListEditor(
            initial.objectives, initial.method, initial.channel_members
        )
        self.objectives_editor.changed.connect(self._refresh)
        objective_layout.addWidget(self.objectives_editor)
        left.addWidget(objective_group)

        conditions = self._group(left, tr("ui.widgets.quickstart.5_solve_and_output"))
        self._double(
            conditions,
            "volume_fraction",
            tr("ui.widgets.quickstart.material_fraction"),
            initial.volume_fraction,
            *deepcopy(CONSTANT.UI.QUICKSTART.WIDGET.FIELDS.VOLUME_FRACTION.RANGE),
            group="topology",
        )
        self._line(
            conditions, "label", tr("ui.widgets.quickstart.task_name"), initial.label
        )
        self._line(
            conditions,
            "result_folder",
            tr("ui.widgets.quickstart.result_folder"),
            initial.result_folder,
        )
        folder = QPushButton(tr("ui.widgets.quickstart.choose_output_folder"))
        folder.clicked.connect(self._browse_folder)
        conditions.addRow("", folder)
        left.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setMinimumWidth(
            theme_manager.palette.layout.quickstart.scroll_minimum_width
        )
        columns.addWidget(scroll, 3)
        right = QVBoxLayout()
        self.preview = InitialDesignPreview()
        right.addWidget(self.preview)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setAlignment(Qt.AlignmentFlag.AlignTop)
        right.addWidget(self.summary)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setProperty("textRole", "error")
        right.addWidget(self.error)
        right.addStretch()
        columns.addLayout(right, 2)
        outer.addLayout(columns, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            tr("ui.widgets.quickstart.cancel")
        )
        self.create_button = buttons.addButton(
            tr("ui.widgets.quickstart.create_and_edit"),
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        self.create_button.setDefault(True)
        self.create_button.setProperty("actionRole", "primary")
        self.create_button.setProperty("buttonLayout", "prominent")
        buttons.accepted.connect(self._create)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        values = {
            "method": initial.method,
            "length": initial.length,
            "radius": initial.radius,
            "wall": initial.wall,
            "height": initial.height,
            "depth": initial.depth,
            "volume_fraction": initial.volume_fraction,
            "mesh_size": initial.mesh_size,
            "mu": initial.mu,
            "kappa": initial.kappa,
            "optimize_outer": initial.optimize_outer,
            "label": initial.label,
            "result_folder": initial.result_folder,
        }
        for key, value in values.items():
            widget = self.fields.get(key)
            if isinstance(widget, QComboBox):
                widget.setCurrentIndex(widget.findData(value))
            elif isinstance(widget, QLineEdit):
                widget.setText(value)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(value)
            elif widget is not None:
                widget.setValue(value)
        self._loading = False
        self.fields["method"].currentIndexChanged.connect(self._method_changed)
        self._refresh()

    @staticmethod
    def _group(layout, title):
        box = QGroupBox(title)
        form = QFormLayout(box)
        layout.addWidget(box)
        return form

    def _row(self, form, key, label, widget, group=None):
        caption = QLabel(label)
        form.addRow(caption, widget)
        self.fields[key] = widget
        self._rows.append((key, caption, widget, group))
        if isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(self._refresh)
        elif isinstance(widget, QCheckBox):
            widget.toggled.connect(self._refresh)
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(self._refresh)
        elif isinstance(widget, WorkspaceChannelSelector):
            widget.changed.connect(self._refresh)
        else:
            widget.valueChanged.connect(self._refresh)

    def _double(self, form, key, label, value, minimum, maximum, group=None):
        field = QDoubleSpinBox()
        decimals = CONSTANT.UI.QUICKSTART.WIDGET.NUMERIC_FIELD_DECIMALS
        if key in ("mu", "kappa"):
            field.setDecimals(decimals.MATERIAL)
        elif key == "volume_fraction":
            field.setDecimals(decimals.VOLUME_FRACTION)
        else:
            field.setDecimals(decimals.DEFAULT)
        field.setRange(minimum, maximum)
        steps = CONSTANT.UI.QUICKSTART.WIDGET.NUMERIC_FIELD_STEP
        if key == "length":
            field.setSingleStep(steps.LENGTH)
        elif key == "pressure_kpa":
            field.setSingleStep(steps.PRESSURE_KPA)
        elif key == "volume_fraction":
            field.setSingleStep(steps.VOLUME_FRACTION)
        else:
            field.setSingleStep(steps.GEOMETRY)
        field.setValue(value)
        field.setKeyboardTracking(False)
        self._row(form, key, label, field, group)

    def _integer(self, form, key, label, value, minimum, maximum, group=None):
        field = QSpinBox()
        field.setRange(minimum, maximum)
        field.setValue(value)
        self._row(form, key, label, field, group)

    def _combo(self, form, key, label, choices, group=None):
        field = QComboBox()
        for value, caption in choices:
            field.addItem(caption, value)
        self._row(form, key, label, field, group)

    def _check(self, form, key, label, group=None):
        field = QCheckBox()
        self._row(form, key, label, field, group)

    def _line(self, form, key, label, value):
        self._row(form, key, label, QLineEdit(value))

    def options(self):
        values = {}
        for key, widget in self.fields.items():
            if isinstance(widget, QComboBox):
                values[key] = widget.currentData()
            elif isinstance(widget, QLineEdit):
                values[key] = widget.text()
            elif isinstance(widget, QCheckBox):
                values[key] = widget.isChecked()
            else:
                values[key] = widget.value()
        values["layers"] = (
            self.layers_editor.layers() if values["method"] == "shapeopt" else []
        )
        values["objectives"] = self.objectives_editor.values()
        return QuickstartOptions(**values)

    def _method_changed(self):
        method = self.fields["method"].currentData()
        self.objectives_editor.set_method(method)
        shape_length = CONSTANT.UI.QUICKSTART.DEFAULT.LENGTH
        simp_length = CONSTANT.UI.QUICKSTART.DEFAULT.SIMP_LENGTH
        if self.fields["length"].value() in (simp_length, shape_length):
            self.fields["length"].setValue(
                simp_length if method == "simp" else shape_length
            )
        shape_material = (
            CONSTANT.UI.QUICKSTART.DEFAULT.MATERIAL_MU,
            CONSTANT.UI.QUICKSTART.DEFAULT.MATERIAL_KAPPA,
        )
        simp_material = (
            CONSTANT.UI.QUICKSTART.DEFAULT.SIMP_MU,
            CONSTANT.UI.QUICKSTART.DEFAULT.SIMP_KAPPA,
        )
        current_material = (self.fields["mu"].value(), self.fields["kappa"].value())
        if current_material in (shape_material, simp_material):
            selected = simp_material if method == "simp" else shape_material
            self.fields["mu"].setValue(selected[0])
            self.fields["kappa"].setValue(selected[1])
        self._refresh()

    def _refresh(self, *args):
        if self._loading:
            return
        try:
            self.objectives_editor.set_method(self.fields["method"].currentData())
            o = self.options()
        except ValueError as exc:
            self.error.setText(str(exc))
            self.create_button.setEnabled(False)
            return
        if o.method == "shapeopt":
            self.objectives_editor.set_geometry_channels(o.channel_members)
            o.objectives = self.objectives_editor.values()
        shape = o.method == "shapeopt"
        for key, caption, widget, group in self._rows:
            visible = (
                group is None
                or group == "shape"
                and shape
                or group == "topology"
                and not shape
            )
            if key == "length":
                caption.setText(
                    tr("ui.widgets.quickstart.total_length_mm")
                    if shape
                    else tr("ui.widgets.quickstart.domain_length_mm")
                )
            caption.setVisible(visible)
            widget.setVisible(visible)
        self.fields["length"].setReadOnly(shape)
        self.fields["length"].setMaximum(
            CONSTANT.UI.QUICKSTART.WIDGET.SHAPE_LENGTH_MAXIMUM
            if shape
            else CONSTANT.UI.QUICKSTART.WIDGET.TOPOLOGY_LENGTH_MAXIMUM
        )
        if shape:
            self.fields["length"].blockSignals(True)
            self.fields["length"].setValue(o.total_length)
            self.fields["length"].blockSignals(False)
        self.preview.set_options(o)
        self.summary.setText(quickstart_summary(o))
        try:
            o.validate()
        except ValueError as exc:
            self.error.setText(str(exc))
            self.create_button.setEnabled(False)
        else:
            self.error.clear()
            self.create_button.setEnabled(True)

    def _browse_folder(self):
        directory = choose_directory(
            self,
            tr("ui.widgets.quickstart.output_folder"),
            self.fields["result_folder"].text(),
        )
        if directory:
            self.fields["result_folder"].setText(directory)

    def _create(self):
        try:
            problem = build_quickstart(self.options())
            generate_source(problem)
        except (ValueError, TypeError, KeyError) as exc:
            self.error.setText(str(exc))
            return
        self.problem = problem
        self.accept()
