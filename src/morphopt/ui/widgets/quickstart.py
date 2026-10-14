"""Design-intent Quickstart dialog; detailed model editing stays in Workbench."""
from __future__ import annotations

import numpy as np

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QListWidget, QListWidgetItem,
)

from ..application.quickstart import (
    GOALS,
    QuickstartOptions,
    build_quickstart,
    ObjectiveDraft,
    available_objectives,
    select_workspace_channels,
)
from ..model.chamberlayout import ChamberLayer
from ..visualization.geometry import InitialDesignGeometry
from ..application.definitions import ProblemSession
from ..i18n import tr
from ..presentation.labels import quickstart_summary


class ChamberLayersEditor(QWidget):
    """Rows define serial layers; cavity count and arrangement define parallelism."""
    changed = Signal()

    def __init__(self, layers, parent=None):
        super().__init__(parent)
        self._loading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        hint = QLabel(tr('ui.widgets.quickstart.layers_run_from_base_to_tip_along_z_equal_channel_numbers_share_pressure'))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            tr('ui.widgets.quickstart.length_mm_30b65866'), tr('ui.widgets.quickstart.cavities'), tr('ui.widgets.quickstart.arrangement'),
            tr('ui.widgets.quickstart.radius_mm'), tr('ui.widgets.quickstart.center_mm'), tr('ui.widgets.quickstart.shape'),
            tr('ui.widgets.quickstart.phase'), tr('ui.widgets.quickstart.channels')])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setMinimumHeight(155)
        self.table.cellChanged.connect(self._cell_changed)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        for label, callback in [(tr('ui.widgets.quickstart.add_layer'), self._add), (tr('ui.widgets.quickstart.remove_layer'), self._remove),
                                (tr('ui.widgets.quickstart.move_up'), lambda: self._move(-1)), (tr('ui.widgets.quickstart.move_down'), lambda: self._move(1))]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.set_layers(layers or [ChamberLayer()])

    def set_layers(self, layers):
        self._loading = True
        self.table.setRowCount(0)
        for layer in layers:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [f"{layer.length:g}", str(layer.chambers), layer.arrangement, f"{layer.radius:g}",
                      f"{layer.center_radius:g}", layer.shape, f"{layer.phase_degrees:g}", ",".join(map(
                          str,
                          layer.pressure_channels,
                      ))]
            for column, value in enumerate(values):
                if column in (2, 5):
                    combo = QComboBox()
                    choices = [("ring", tr('ui.widgets.quickstart.ring')), ("line", tr('ui.widgets.quickstart.line'))] if column == 2 else [("cylinder", tr('ui.widgets.quickstart.cylinder')), ("sphere", tr('ui.widgets.quickstart.sphere'))]
                    for key, caption in choices:
                        combo.addItem(caption, key)
                    combo.setCurrentIndex(combo.findData(value))
                    combo.currentIndexChanged.connect(lambda *_: self.changed.emit())
                    self.table.setCellWidget(row, column, combo)
                else:
                    self.table.setItem(row, column, QTableWidgetItem(value))
        self._loading = False

    def layers(self):
        layers = []
        try:
            for row in range(self.table.rowCount()):
                value = lambda column: self.table.item(row, column).text().strip()
                layers.append(ChamberLayer(length=float(value(0)), chambers=int(value(1)),
                    arrangement=self.table.cellWidget(row, 2).currentData(), radius=float(value(3)),
                    center_radius=float(value(4)), shape=self.table.cellWidget(row, 5).currentData(),
                    phase_degrees=float(value(6)), pressure_channels=[int(c.strip()) for c in value(7).split(",")]))
        except ValueError as exc:
            raise ValueError(tr('ui.widgets.quickstart.enter_valid_layer_parameters_separate_channel_numbers_with_commas')) from exc
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
            if channels == list(range(1, len(channels)+1)) and 1 <= count <= 8:
                self._loading = True
                self.table.item(row, 7).setText(",".join(str(c) for c in range(1, count+1)))
                self._loading = False
        self.changed.emit()

    def _add(self):
        try:
            layers = self.layers()
        except ValueError:
            self.changed.emit()
            return
        if len(layers) < 8:
            layers.append(ChamberLayer(length=40.))
            self.set_layers(layers)
            self.changed.emit()

    def _remove(self):
        if self.table.rowCount() > 1:
            row = self.table.currentRow()
            self.table.removeRow(row if row >= 0 else self.table.rowCount()-1)
            self.changed.emit()

    def _move(self, delta):
        row = self.table.currentRow()
        target = row+delta
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
        layout.setContentsMargins(0, 0, 0, 0)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.list = QListWidget()
        self.list.setMaximumHeight(115)
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
            item = QListWidgetItem(tr(
                'ui.widgets.quickstart.channel_value_chambers_value',
                value_0=channel,
                value_1=cavities,
            ))
            item.setData(Qt.ItemDataRole.UserRole, channel)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if channel in chosen else Qt.CheckState.Unchecked
            )
            self.list.addItem(item)
        if required is None:
            self.hint.setText(tr('ui.widgets.quickstart.chambers_on_the_same_pressure_channel_move_together'))
        else:
            self.hint.setText(tr(
                'ui.widgets.quickstart.select_value_independent_inputs_chambers_on_one_channel_move_together',
                value_0=required,
            ))
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
        if (self._required is not None
                and item.checkState() == Qt.CheckState.Checked
                and len(self.selected_channels()) > self._required):
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
        self.form.setContentsMargins(0, 0, 0, 0)
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
            spin.setRange(0., 1000.)
            spin.setDecimals(1)
            spin.setSuffix(" kPa")
            value = pressures.get(channel, pressures.get(str(channel), 0.0))
            spin.setValue(float(value))
            spin.valueChanged.connect(self._value_changed)
            self.fields[channel] = spin
            self.form.addRow(
                QLabel(tr(
                    'ui.widgets.quickstart.channel_value_chambers_value',
                    value_0=channel,
                    value_1=cavities,
                )),
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
        outer.setContentsMargins(0, 0, 0, 0)
        list_row = QHBoxLayout()
        self.list = QListWidget()
        self.list.setMinimumHeight(74)
        self.list.setMaximumHeight(125)
        self.list.currentRowChanged.connect(self._selection_changed)
        list_row.addWidget(self.list, 1)
        buttons = QVBoxLayout()
        self.add_button = QPushButton(tr('ui.widgets.quickstart.add_objective'))
        self.remove_button = QPushButton(tr('ui.widgets.quickstart.remove_objective'))
        self.add_button.clicked.connect(self._add)
        self.remove_button.clicked.connect(self._remove)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch()
        list_row.addLayout(buttons)
        outer.addLayout(list_row)

        self.detail = QWidget()
        self.form = QFormLayout(self.detail)
        outer.addWidget(self.detail)
        self.kind = QComboBox()
        self.weight = QDoubleSpinBox()
        self.weight.setRange(0., 1000.)
        self.weight.setDecimals(3)
        self.weight.setValue(1.)
        self.target = QDoubleSpinBox()
        self.target.setRange(.001, 10000.)
        self.target.setDecimals(2)
        self.force = QDoubleSpinBox()
        self.force.setRange(.001, 1000.)
        self.force.setDecimals(2)
        self.workspace_pressure = QDoubleSpinBox()
        self.workspace_pressure.setRange(.1, 1000.)
        self.workspace_pressure.setDecimals(1)
        self.workspace_order = QSpinBox()
        self.workspace_order.setRange(1, 8)
        self.pressures = ChannelPressureEditor()
        self.workspace_inputs = WorkspaceChannelSelector()
        self.kind_caption = self._add_row("kind", tr('ui.widgets.quickstart.objective_type'), self.kind)
        self.weight_caption = self._add_row("weight", tr('ui.widgets.quickstart.weight'), self.weight)
        self.target_caption = self._add_row("target", tr('ui.widgets.quickstart.target'), self.target)
        self.force_caption = self._add_row("force", tr('ui.widgets.quickstart.load_z_n'), self.force)
        self.pressure_caption = self._add_row(
            "pressures",
            tr('ui.widgets.quickstart.pressure_load_case'),
            self.pressures,
        )
        self.workspace_caption = self._add_row(
            "workspace_channels",
            tr('ui.widgets.quickstart.workspace_drives'),
            self.workspace_inputs,
        )
        self.workspace_pressure_caption = self._add_row(
            "workspace_pressure",
            tr('ui.widgets.quickstart.workspace_max_pressure_kpa'),
            self.workspace_pressure,
        )
        self.workspace_order_caption = self._add_row(
            "workspace_order",
            tr('ui.widgets.quickstart.boundary_gauss_points_free_axis'),
            self.workspace_order,
        )
        self.workspace_note = QLabel(tr('ui.widgets.quickstart.workspace_has_no_manually_selected_load_case_boundary_integration_cases'))
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
            label = tr('ui.widgets.quickstart.target_tip_deflection')
        return f"{label} · w={objective.weight:g}"

    def _update_list_item(self, row):
        if 0 <= row < len(self.draft.objectives) and self.list.item(row) is not None:
            self.list.item(row).setText(self._objective_label(self.draft.objectives[row]))

    def _update_buttons(self):
        self.add_button.setEnabled(len(self.draft.objectives) < 8)
        self.remove_button.setEnabled(len(self.draft.objectives) > 1)

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
                label = tr('ui.widgets.quickstart.target_tip_deflection')
            self.kind.addItem(label, kind)
        self.kind.setCurrentIndex(max(0, self.kind.findData(objective.kind)))
        self.weight.setValue(objective.weight)
        self.target.setValue(objective.target)
        self.force.setValue(objective.force_n)
        self.workspace_pressure.setValue(objective.workspace_pressure_kpa)
        self.workspace_order.setValue(objective.gauss_order)
        self.pressures.set_channels(self.draft.members, objective.pressures_kpa)
        dimensions = len(GOALS[objective.kind][1]) if objective.is_workspace else None
        self.workspace_inputs.set_channels(self.draft.members, dimensions, objective.workspace_channels)
        self._updating = False
        self.detail.show()
        self._set_detail_visibility(objective)
        self._update_buttons()

    def _set_detail_visibility(self, objective):
        workspace = objective.is_workspace
        shape = self.draft.method == "shapeopt"
        target_visible = not workspace and objective.kind != "stiffness"
        target_unit = "°" if objective.kind == "twist" else "N" if objective.kind == "contact" else "mm"
        self.target_caption.setText(tr('ui.widgets.quickstart.target_value', value_0=target_unit))
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
        if len(self.draft.objectives) >= 8:
            return
        self._save_current()
        self.draft.add()
        self._refresh_list()
        self.list.setCurrentRow(len(self.draft.objectives)-1)
        self._update_buttons()
        self.changed.emit()

    def _remove(self):
        if len(self.draft.objectives) <= 1 or not 0 <= self.list.currentRow() < len(self.draft.objectives):
            return
        index = self.list.currentRow()
        self._save_current()
        self.draft.remove(index)
        self._current_index = -1
        self._refresh_list()
        self.list.setCurrentRow(min(index, len(self.draft.objectives)-1))
        self._update_buttons()
        self.changed.emit()

    def set_method(self, method):
        if method == self.draft.method:
            return
        self._save_current()
        self.draft.set_method(method)
        self._refresh_list()
        selected = min(max(self._current_index, 0), len(self.draft.objectives)-1)
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
        self.setMinimumSize(300, 350)
        self.options = QuickstartOptions()
        self.geometry = None

    def set_options(self, options):
        self.options = options
        try:
            self.geometry = InitialDesignGeometry(options)
        except ValueError:
            self.geometry = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#17212e"))
        painter.setPen(QColor("#b4c5db"))
        painter.drawText(16, 25, tr('ui.widgets.quickstart.initial_design_isometric_projection'))
        if self.geometry is not None:
            scale, shift = self.geometry.transform(self.width(), self.height())
            painter.setPen(Qt.PenStyle.NoPen)
            for _depth, points, color, shade, alpha in self.geometry.triangles:
                brush = QColor(color).lighter(shade)
                brush.setAlpha(alpha)
                painter.setBrush(brush)
                uv = scale * points + shift
                painter.drawPolygon(QPolygonF([QPointF(float(x), float(y)) for x, y in uv]))
            painter.setPen(QPen(QColor("#94acc4"), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for line in self.geometry.lines:
                painter.drawPolyline(QPolygonF([QPointF(float(x), float(y)) for x, y in scale * line + shift]))
        origin = QPointF(48, self.height()-58)
        for vector, label, color in [(np.array([1.,0.,0.]), "X", "#f18b85"), (np.array([0.,1.,0.]), "Y", "#79d795"), (np.array([0.,0.,1.]), "Z", "#85bafa")]:
            delta = QPointF(
                float(30*vector@InitialDesignGeometry.horizontal),
                float(30*vector@InitialDesignGeometry.vertical),
            )
            end = origin+delta
            painter.setPen(QPen(QColor(color), 2))
            painter.drawLine(origin, end)
            painter.drawText(end+QPointF(3, -3), label)
        painter.setPen(QColor("#b4c5db"))
        caption = tr('ui.widgets.quickstart.length_value_mm', value_0=self.options.total_length)
        if self.options.method == "shapeopt":
            caption += tr(
                'ui.widgets.quickstart.value_layers_value_cavities',
                value_0=len(self.options.layers),
                value_1=self.options.chambers,
            )
        painter.drawText(
            QRectF(85, self.height()-42, self.width()-95, 36),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            caption,
        )


class QuickstartDialog(QDialog):
    def __init__(self, problem=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('ui.widgets.quickstart.quickstart'))
        self.resize(1250, 850)
        self.problem = None
        initial = QuickstartOptions.from_problem(problem) if problem else QuickstartOptions()
        if problem:
            initial.result_folder = problem.result_folder
            initial.label = problem.label
        self._loading = True
        self.fields = {}
        self._rows = []
        outer = QVBoxLayout(self)
        title = QLabel(tr('ui.widgets.quickstart.start_with_the_motion_you_want'))
        title.setStyleSheet("font-size:22px; font-weight:600;")
        outer.addWidget(title)
        description = QLabel(tr('ui.widgets.quickstart.describe_the_starting_structure_and_goal_to_create_an_editable_optimizat'))
        description.setWordWrap(True)
        outer.addWidget(description)
        columns = QHBoxLayout()
        content = QWidget()
        left = QVBoxLayout(content)
        left.setContentsMargins(0, 0, 12, 0)
        task = self._group(left, tr('ui.widgets.quickstart.1_choose_a_design_task'))
        self._combo(
            task,
            "method",
            tr('ui.widgets.quickstart.optimization_method'),
            [("shapeopt", tr('ui.widgets.quickstart.shape_optimization')), ("simp", tr('ui.widgets.quickstart.topology_optimization'))],
        )
        geometry = self._group(left, tr('ui.widgets.quickstart.2_define_geometry'))
        self._double(geometry, "length", tr('ui.widgets.quickstart.length_mm'), 80., 5., 1000.)
        self._double(geometry, "radius", tr('ui.widgets.quickstart.body_radius_mm'), 10., 1., 200., group="shape")
        self.layers_editor = ChamberLayersEditor(initial.layers)
        self.layers_editor.changed.connect(self._refresh)
        layer_caption = QLabel(tr('ui.widgets.quickstart.serial_layers_parallel_cavities'))
        geometry.addRow(layer_caption)
        geometry.addRow(self.layers_editor)
        self._rows.append(("layers", layer_caption, self.layers_editor, "shape"))
        self._double(geometry, "wall", tr('ui.widgets.quickstart.minimum_wall_mm'), 2., .2, 30., group="shape")
        self._double(
            geometry,
            "height",
            tr('ui.widgets.quickstart.domain_height_mm'),
            16.,
            1.,
            300.,
            group="topology",
        )
        self._double(
            geometry,
            "depth",
            tr('ui.widgets.quickstart.domain_depth_mm'),
            8.,
            1.,
            100.,
            group="topology",
        )
        self._double(geometry, "mesh_size", tr('ui.widgets.quickstart.mesh_size_mm'), 2., .2, 10.)
        self._check(
            geometry,
            "optimize_outer",
            tr('ui.widgets.quickstart.optimize_inner_and_outer_profiles_on_by_default'),
            group="shape",
        )

        material = self._group(left, tr('ui.widgets.quickstart.3_material_properties'))
        self._double(material, "mu", tr('ui.widgets.quickstart.shear_modulus_mpa'), .482, .001, 1000.)
        self._double(material, "kappa", tr('ui.widgets.quickstart.bulk_modulus_mpa'), 4.8, .001, 10000.)

        objective_group = QGroupBox(tr('ui.widgets.quickstart.4_define_objectives'))
        objective_layout = QVBoxLayout(objective_group)
        self.objectives_editor = ObjectiveListEditor(
            initial.objectives, initial.method, initial.channel_members
        )
        self.objectives_editor.changed.connect(self._refresh)
        objective_layout.addWidget(self.objectives_editor)
        left.addWidget(objective_group)

        conditions = self._group(left, tr('ui.widgets.quickstart.5_solve_and_output'))
        self._double(
            conditions,
            "volume_fraction",
            tr('ui.widgets.quickstart.material_fraction'),
            .4,
            .05,
            .95,
            group="topology",
        )
        self._line(conditions, "label", tr('ui.widgets.quickstart.task_name'), initial.label)
        self._line(conditions, "result_folder", tr('ui.widgets.quickstart.result_folder'), initial.result_folder)
        folder = QPushButton(tr('ui.widgets.quickstart.choose_output_folder'))
        folder.clicked.connect(self._browse_folder)
        conditions.addRow("", folder)
        left.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setMinimumWidth(475)
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
        self.error.setStyleSheet("color:#ef8f82;")
        right.addWidget(self.error)
        right.addStretch()
        columns.addLayout(right, 2)
        outer.addLayout(columns, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr('ui.widgets.quickstart.cancel'))
        self.create_button = buttons.addButton(
            tr('ui.widgets.quickstart.create_and_edit'),
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        self.create_button.setDefault(True)
        self.create_button.setStyleSheet("padding:8px 24px; font-weight:600;")
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
        field.setDecimals(3 if key in ("mu", "kappa") else 2 if key == "volume_fraction" else 1)
        field.setRange(minimum, maximum)
        field.setSingleStep(5. if key in ("length", "pressure_kpa") else .05 if key == "volume_fraction" else .1)
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
        values["layers"] = self.layers_editor.layers() if values["method"] == "shapeopt" else []
        values["objectives"] = self.objectives_editor.values()
        return QuickstartOptions(**values)

    def _method_changed(self):
        method = self.fields["method"].currentData()
        self.objectives_editor.set_method(method)
        if self.fields["length"].value() in (40., 80.):
            self.fields["length"].setValue(40. if method == "simp" else 80.)
        if self.fields["mu"].value() in (.482, 10.) and self.fields["kappa"].value() in (4.8, 100.):
            self.fields["mu"].setValue(10. if method == "simp" else .482)
            self.fields["kappa"].setValue(100. if method == "simp" else 4.8)
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
            visible = (group is None or group == "shape" and shape or group == "topology" and not shape)
            if key == "length":
                caption.setText(tr('ui.widgets.quickstart.total_length_mm') if shape else tr('ui.widgets.quickstart.domain_length_mm'))
            caption.setVisible(visible)
            widget.setVisible(visible)
        self.fields["length"].setReadOnly(shape)
        self.fields["length"].setMaximum(1e12 if shape else 1000.)
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
        directory = QFileDialog.getExistingDirectory(
            self,
            tr('ui.widgets.quickstart.output_folder'),
            self.fields["result_folder"].text(),
        )
        if directory:
            self.fields["result_folder"].setText(directory)

    def _create(self):
        try:
            problem = build_quickstart(self.options())
            ProblemSession(problem).source()
        except (ValueError, TypeError, KeyError) as exc:
            self.error.setText(str(exc))
            return
        self.problem = problem
        self.accept()
