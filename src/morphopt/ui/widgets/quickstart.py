"""Design-intent Quickstart dialog; detailed model editing stays in Workbench."""
from __future__ import annotations

import math
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

from ..application.quickstart import GOALS, QuickstartObjective, QuickstartOptions, build_quickstart
from ...optcore.modelparams.partinterface.chamberlayout import ChamberLayer
from ...optcore.modelparams.partinterface import BoxPartInterface
from ..application.definitions import ProblemSession
from ..i18n import T


class ChamberLayersEditor(QWidget):
    """Rows define serial layers; cavity count and arrangement define parallelism."""
    changed = Signal()

    def __init__(self, layers, parent=None):
        super().__init__(parent)
        self._loading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        hint = QLabel(T("沿 Z 轴从底部到末端排列各层；相同压力通道共用压力。", "Layers run from base to tip along Z; equal channel numbers share pressure."))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            T("层长 mm", "Length mm"), T("并联气腔数", "Cavities"), T("截面排布", "Arrangement"),
            T("气腔半径 mm", "Radius mm"), T("中心半径 mm", "Center mm"), T("初始形状", "Shape"),
            T("相位 °", "Phase °"), T("压力通道", "Channels")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setMinimumHeight(155)
        self.table.cellChanged.connect(self._cell_changed)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        for label, callback in [(T("增加一层", "Add layer"), self._add), (T("删除层", "Remove layer"), self._remove),
                                (T("上移", "Move up"), lambda: self._move(-1)), (T("下移", "Move down"), lambda: self._move(1))]:
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
                      f"{layer.center_radius:g}", layer.shape, f"{layer.phase_degrees:g}", ",".join(map(str, layer.pressure_channels))]
            for column, value in enumerate(values):
                if column in (2, 5):
                    combo = QComboBox()
                    choices = [("ring", T("周向", "Ring")), ("line", T("并排", "Line"))] if column == 2 else [("cylinder", T("圆柱", "Cylinder")), ("sphere", T("球形", "Sphere"))]
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
            raise ValueError(T("请填写有效的层参数；压力通道用逗号分隔。", "Enter valid layer parameters; separate channel numbers with commas.")) from exc
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
            chosen = chosen[:required]
            for channel in available:
                if len(chosen) >= required:
                    break
                if channel not in chosen:
                    chosen.append(channel)
        self._required = required
        self._channels = available
        self._updating = True
        self.list.clear()
        for channel in available:
            cavities = ", ".join(map(str, members[channel]))
            item = QListWidgetItem(T(
                f"通道 {channel} · 气腔 {cavities}",
                f"Channel {channel} · chambers {cavities}",
            ))
            item.setData(Qt.ItemDataRole.UserRole, channel)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if channel in chosen else Qt.CheckState.Unchecked
            )
            self.list.addItem(item)
        if required is None:
            self.hint.setText(T(
                "同一压力通道下的气腔联动。",
                "Chambers on the same pressure channel move together.",
            ))
        else:
            self.hint.setText(T(
                f"选择 {required} 路独立压力；同一通道下的气腔联动。",
                f"Select {required} independent inputs; chambers on one channel move together.",
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
                QLabel(T(f"通道 {channel} · 气腔 {cavities}", f"Channel {channel} · chambers {cavities}")),
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
        self.method = method
        self.members = {key: list(value) for key, value in channel_members.items()}
        self.objectives = [self._copy_objective(item) for item in objectives]
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
        self.add_button = QPushButton(T("添加目标", "Add objective"))
        self.remove_button = QPushButton(T("删除目标", "Remove objective"))
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
        self.kind_caption = self._add_row("kind", T("目标类型", "Objective type"), self.kind)
        self.weight_caption = self._add_row("weight", T("权重", "Weight"), self.weight)
        self.target_caption = self._add_row("target", T("目标值", "Target"), self.target)
        self.force_caption = self._add_row("force", T("载荷力 · −Z (N)", "Load · −Z (N)"), self.force)
        self.pressure_caption = self._add_row("pressures", T("压力载荷工况", "Pressure load case"), self.pressures)
        self.workspace_caption = self._add_row("workspace_channels", T("工作空间驱动", "Workspace drives"), self.workspace_inputs)
        self.workspace_pressure_caption = self._add_row("workspace_pressure", T("工作空间最大压力 (kPa)", "Workspace max pressure (kPa)"), self.workspace_pressure)
        self.workspace_order_caption = self._add_row("workspace_order", T("边界高斯点数 / 自由方向", "Boundary Gauss points / free axis"), self.workspace_order)
        self.workspace_note = QLabel(T(
            "工作空间不指定单点载荷工况；系统会按所选驱动自动生成边界积分工况。",
            "Workspace has no manually selected load case; boundary integration cases are generated from the selected drives.",
        ))
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
        if self.objectives:
            self.list.setCurrentRow(0)
        self._update_buttons()

    @staticmethod
    def _copy_objective(objective):
        if isinstance(objective, dict):
            objective = QuickstartObjective(**objective)
        return QuickstartObjective(
            kind=objective.kind,
            weight=objective.weight,
            target=objective.target,
            pressures_kpa=dict(objective.pressures_kpa),
            workspace_channels=list(objective.workspace_channels),
            workspace_pressure_kpa=objective.workspace_pressure_kpa,
            gauss_order=objective.gauss_order,
            force_n=objective.force_n,
        )

    def _allowed(self):
        return sorted(set(GOALS)-{"stiffness"}) if self.method == "shapeopt" else ["stiffness", "bend"]

    def _add_row(self, key, text, widget):
        caption = QLabel(text)
        self.form.addRow(caption, widget)
        return caption

    def _refresh_list(self):
        self._updating = True
        self.list.clear()
        for objective in self.objectives:
            self.list.addItem(self._objective_label(objective))
        self._updating = False

    def _objective_label(self, objective):
        label = T(*GOALS[objective.kind][:2])
        if self.method == "simp" and objective.kind == "bend":
            label = T("末端目标挠度", "Target tip deflection")
        return f"{label} · w={objective.weight:g}"

    def _update_list_item(self, row):
        if 0 <= row < len(self.objectives) and self.list.item(row) is not None:
            self.list.item(row).setText(self._objective_label(self.objectives[row]))

    def _update_buttons(self):
        self.add_button.setEnabled(len(self.objectives) < 8)
        self.remove_button.setEnabled(len(self.objectives) > 1)

    def _save_current(self):
        if not 0 <= self._current_index < len(self.objectives):
            return
        objective = self.objectives[self._current_index]
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
        if not 0 <= row < len(self.objectives):
            self.detail.hide()
            return
        objective = self.objectives[row]
        self._updating = True
        self.kind.clear()
        for kind in self._allowed():
            label = T(*GOALS[kind][:2])
            if self.method == "simp" and kind == "bend":
                label = T("末端目标挠度", "Target tip deflection")
            self.kind.addItem(label, kind)
        self.kind.setCurrentIndex(max(0, self.kind.findData(objective.kind)))
        self.weight.setValue(objective.weight)
        self.target.setValue(objective.target)
        self.force.setValue(objective.force_n)
        self.workspace_pressure.setValue(objective.workspace_pressure_kpa)
        self.workspace_order.setValue(objective.gauss_order)
        self.pressures.set_channels(self.members, objective.pressures_kpa)
        dimensions = len(GOALS[objective.kind][2]) if objective.is_workspace else None
        self.workspace_inputs.set_channels(self.members, dimensions, objective.workspace_channels)
        self._updating = False
        self.detail.show()
        self._set_detail_visibility(objective)
        self._update_buttons()

    def _set_detail_visibility(self, objective):
        workspace = objective.is_workspace
        shape = self.method == "shapeopt"
        target_visible = not workspace and objective.kind != "stiffness"
        target_unit = "°" if objective.kind == "twist" else "N" if objective.kind == "contact" else "mm"
        self.target_caption.setText(T(f"目标值 ({target_unit})", f"Target ({target_unit})"))
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
        if len(self.objectives) >= 8:
            return
        self._save_current()
        channels = sorted(self.members)
        obj = QuickstartObjective(
            kind="bend" if self.method == "shapeopt" else "stiffness",
            pressures_kpa={channel: (60. if channel == 1 else 0.) for channel in channels},
            workspace_channels=channels[:2],
        )
        self.objectives.append(obj)
        self._refresh_list()
        self.list.setCurrentRow(len(self.objectives)-1)
        self._update_buttons()
        self.changed.emit()

    def _remove(self):
        if len(self.objectives) <= 1 or not 0 <= self.list.currentRow() < len(self.objectives):
            return
        index = self.list.currentRow()
        self._save_current()
        self.objectives.pop(index)
        self._current_index = -1
        self._refresh_list()
        self.list.setCurrentRow(min(index, len(self.objectives)-1))
        self._update_buttons()
        self.changed.emit()

    def set_method(self, method):
        if method == self.method:
            return
        self._save_current()
        self.method = method
        fallback = "bend" if method == "shapeopt" else "stiffness"
        allowed = set(self._allowed())
        for objective in self.objectives:
            if objective.kind not in allowed:
                objective.kind = fallback
        self._refresh_list()
        selected = min(max(self._current_index, 0), len(self.objectives)-1)
        self._updating = True
        self.list.setCurrentRow(selected)
        self._updating = False
        self._load_current()

    def set_geometry_channels(self, members):
        members = {key: list(value) for key, value in members.items()}
        if members == self.members:
            return
        self._save_current()
        self.members = members
        available = sorted(members)
        for objective in self.objectives:
            objective.pressures_kpa = {
                channel: objective.pressures_kpa.get(channel, 0.0)
                for channel in available
            }
            if objective.is_workspace:
                required = len(GOALS[objective.kind][2])
                selected = [channel for channel in objective.workspace_channels if channel in members][:required]
                for channel in available:
                    if len(selected) >= required:
                        break
                    if channel not in selected:
                        selected.append(channel)
                objective.workspace_channels = selected
        self._load_current()

    def values(self):
        self._save_current()
        return [self._copy_objective(objective) for objective in self.objectives]


class InitialDesignPreview(QWidget):
    """Orthographic isometric rendering of initial meshes supplied by the kernel."""
    _horizontal = np.array([1., -1., 0.])/math.sqrt(2)
    _vertical = np.array([1., 1., -2.])/math.sqrt(6)
    _depth = np.array([1., 1., 1.])/math.sqrt(3)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 350)
        self.options = QuickstartOptions()
        self.meshes = {}

    def set_options(self, options):
        self.options = options
        try:
            self.meshes = options.geometry_layout().get_initial_meshes() if options.method == "shapeopt" else {
                "body": BoxPartInterface(length=options.length, height=options.height, depth=options.depth).get_initial_mesh()}
        except ValueError:
            self.meshes = {}
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#17212e"))
        painter.setPen(QColor("#b4c5db"))
        painter.drawText(16, 25, T("初始设计 · 正等轴测投影", "Initial design · isometric projection"))
        if self.meshes:
            vertices = np.concatenate([mesh.points for mesh in self.meshes.values()])
            projected = np.column_stack((vertices@self._horizontal, vertices@self._vertical))
            lo, hi = projected.min(axis=0), projected.max(axis=0)
            scale = min((self.width()-80)/max(hi[0]-lo[0], 1.), (self.height()-110)/max(hi[1]-lo[1], 1.))
            shift = np.array([self.width()/2, self.height()/2])-scale*(lo+hi)/2
            polygons = []
            palette = ["#69ddd0", "#f4bb69", "#a6a0ef", "#f596af"]
            for name, mesh in self.meshes.items():
                mesh = mesh.triangulate()
                points = mesh.points
                for triangle in mesh.faces.reshape(-1, 4)[:, 1:]:
                    xyz = points[triangle]
                    normal = np.cross(xyz[1]-xyz[0], xyz[2]-xyz[0])
                    light = .65+.35*abs(np.dot(normal, np.array([1., -1., 2.])))/(max(np.linalg.norm(normal), 1e-12)*math.sqrt(6))
                    color = QColor("#417ba4" if name == "body" else palette[int(name.split(":")[0].split("-")[1]) % len(palette)])
                    color = color.lighter(int(100*light))
                    color.setAlpha(48 if name == "body" and self.options.method == "shapeopt" else 210)
                    uv = scale*np.column_stack((xyz@self._horizontal, xyz@self._vertical))+shift
                    polygons.append((float(xyz.mean(axis=0)@self._depth), uv, color))
            painter.setPen(Qt.PenStyle.NoPen)
            for depth, uv, color in sorted(polygons, key=lambda item: item[0]):
                painter.setBrush(color)
                painter.drawPolygon(QPolygonF([QPointF(float(x), float(y)) for x, y in uv]))
            painter.setPen(QPen(QColor("#94acc4"), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            # Silhouette and end rings make the transparent cylindrical envelope legible.
            if self.options.method == "shapeopt":
                for sign in (-1., 1.):
                    xy = sign*self.options.radius*self._horizontal[:2]
                    xyz = np.array([[xy[0], xy[1], 0.], [xy[0], xy[1], self.options.total_length]])
                    uv = scale*np.column_stack((xyz@self._horizontal, xyz@self._vertical))+shift
                    painter.drawLine(QPointF(*map(float, uv[0])), QPointF(*map(float, uv[1])))
                for z in (0., self.options.total_length):
                    angles = np.linspace(0., 2*np.pi, 49)
                    xyz = np.column_stack((self.options.radius*np.cos(angles), self.options.radius*np.sin(angles), np.full_like(angles, z)))
                    uv = scale*np.column_stack((xyz@self._horizontal, xyz@self._vertical))+shift
                    painter.drawPolyline(QPolygonF([QPointF(float(x), float(y)) for x, y in uv]))
        origin = QPointF(48, self.height()-58)
        for vector, label, color in [(np.array([1.,0.,0.]), "X", "#f18b85"), (np.array([0.,1.,0.]), "Y", "#79d795"), (np.array([0.,0.,1.]), "Z", "#85bafa")]:
            delta = QPointF(float(30*vector@self._horizontal), float(30*vector@self._vertical))
            end = origin+delta
            painter.setPen(QPen(QColor(color), 2))
            painter.drawLine(origin, end)
            painter.drawText(end+QPointF(3, -3), label)
        painter.setPen(QColor("#b4c5db"))
        caption = T(f"长度 {self.options.total_length:g} mm", f"Length {self.options.total_length:g} mm")
        if self.options.method == "shapeopt":
            caption += T(f" · {len(self.options.layers)} 层 · {self.options.chambers} 气腔", f" · {len(self.options.layers)} layers · {self.options.chambers} cavities")
        painter.drawText(QRectF(85, self.height()-42, self.width()-95, 36), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, caption)


class QuickstartDialog(QDialog):
    def __init__(self, problem=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("快速开始 · Quickstart", "Quickstart"))
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
        title = QLabel(T("从想实现的运动开始", "Start with the motion you want"))
        title.setStyleSheet("font-size:22px; font-weight:600;")
        outer.addWidget(title)
        description = QLabel(T("描述初始结构和目标，自动生成可继续编辑的优化问题。", "Describe the starting structure and goal to create an editable optimization problem."))
        description.setWordWrap(True)
        outer.addWidget(description)
        columns = QHBoxLayout()
        content = QWidget()
        left = QVBoxLayout(content)
        left.setContentsMargins(0, 0, 12, 0)
        task = self._group(left, T("1 · 选择设计任务", "1 · Choose a design task"))
        self._combo(task, "method", T("优化方式", "Optimization method"), [("shapeopt", T("形状优化", "Shape optimization")), ("simp", T("拓扑优化", "Topology optimization"))])
        geometry = self._group(left, T("2 · 定义几何", "2 · Define geometry"))
        self._double(geometry, "length", T("长度 (mm)", "Length (mm)"), 80., 5., 1000.)
        self._double(geometry, "radius", T("外半径 (mm)", "Body radius (mm)"), 10., 1., 200., group="shape")
        self.layers_editor = ChamberLayersEditor(initial.layers)
        self.layers_editor.changed.connect(self._refresh)
        layer_caption = QLabel(T("串联层 / 层内并联气腔", "Serial layers / parallel cavities"))
        geometry.addRow(layer_caption)
        geometry.addRow(self.layers_editor)
        self._rows.append(("layers", layer_caption, self.layers_editor, "shape"))
        self._double(geometry, "wall", T("最小壁厚 (mm)", "Minimum wall (mm)"), 2., .2, 30., group="shape")
        self._double(geometry, "height", T("设计域高度 (mm)", "Domain height (mm)"), 16., 1., 300., group="topology")
        self._double(geometry, "depth", T("设计域厚度 (mm)", "Domain depth (mm)"), 8., 1., 100., group="topology")
        self._double(geometry, "mesh_size", T("网格尺寸 (mm)", "Mesh size (mm)"), 2., .2, 10.)
        self._check(geometry, "optimize_outer", T("优化内外轮廓（默认开启）", "Optimize inner and outer profiles (on by default)"), group="shape")

        material = self._group(left, T("3 · 材料参数", "3 · Material properties"))
        self._double(material, "mu", T("剪切模量 μ (MPa)", "Shear modulus μ (MPa)"), .482, .001, 1000.)
        self._double(material, "kappa", T("体积模量 κ (MPa)", "Bulk modulus κ (MPa)"), 4.8, .001, 10000.)

        objective_group = QGroupBox(T("4 · 定义目标函数", "4 · Define objectives"))
        objective_layout = QVBoxLayout(objective_group)
        self.objectives_editor = ObjectiveListEditor(
            initial.objectives, initial.method, initial.channel_members
        )
        self.objectives_editor.changed.connect(self._refresh)
        objective_layout.addWidget(self.objectives_editor)
        left.addWidget(objective_group)

        conditions = self._group(left, T("5 · 求解与输出", "5 · Solve and output"))
        self._double(conditions, "volume_fraction", T("材料占比", "Material fraction"), .4, .05, .95, group="topology")
        self._line(conditions, "label", T("任务名称", "Task name"), initial.label)
        self._line(conditions, "result_folder", T("结果目录", "Result folder"), initial.result_folder)
        folder = QPushButton(T("选择结果目录…", "Choose output folder…"))
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
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(T("取消", "Cancel"))
        self.create_button = buttons.addButton(T("生成并编辑", "Create and edit"), QDialogButtonBox.ButtonRole.AcceptRole)
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
                caption.setText(T("总长度 (mm)", "Total length (mm)") if shape else T("设计域长度 (mm)", "Domain length (mm)"))
            caption.setVisible(visible)
            widget.setVisible(visible)
        self.fields["length"].setReadOnly(shape)
        self.fields["length"].setMaximum(1e12 if shape else 1000.)
        if shape:
            self.fields["length"].blockSignals(True)
            self.fields["length"].setValue(o.total_length)
            self.fields["length"].blockSignals(False)
        self.preview.set_options(o)
        mode = T("形状优化", "Shape optimization") if shape else T("拓扑优化", "Topology optimization")
        parts = [f"<h3>{mode}</h3>"]
        if shape:
            parts += [T(f"几何：{len(o.layers)} 个串联层 · 共 {o.chambers} 个气腔 · 总长 {o.total_length:g} mm", f"Geometry: {len(o.layers)} serial layers · {o.chambers} cavities · total length {o.total_length:g} mm"), T("固定底部，末端自由运动", "Fixed base, freely moving tip")]
        else:
            parts += [T(f"几何：{o.length:g} × {o.height:g} × {o.depth:g} mm · 材料占比 {100*o.volume_fraction:g}%", f"Geometry: {o.length:g} × {o.height:g} × {o.depth:g} mm · material fraction {100*o.volume_fraction:g}%"), T("左端固定；目标对应的载荷沿 −Z", "Left end fixed; objective load cases act along −Z")]
        parts.append(T("目标项与各自工况", "Objective terms and their load cases"))
        for index, objective in enumerate(o.objectives, 1):
            label = T(*GOALS[objective.kind][:2])
            if objective.kind.startswith("workspace_"):
                load = T(
                    f"边界积分驱动：通道 {', '.join(map(str, objective.workspace_channels))}；最大压力 {objective.workspace_pressure_kpa:g} kPa；每方向 {objective.gauss_order} 点",
                    f"Boundary drives: channels {', '.join(map(str, objective.workspace_channels))}; max pressure {objective.workspace_pressure_kpa:g} kPa; {objective.gauss_order} points per free axis; cases generated by integration",
                )
            elif shape:
                pressures = ", ".join(f"{channel}:{objective.pressures_kpa.get(channel, 0.):g}" for channel in o.channel_ids)
                target_zh = "" if objective.kind == "stiffness" else f" · 目标 {objective.target:g}"
                target_en = "" if objective.kind == "stiffness" else f" · target {objective.target:g}"
                load = T(f"压力工况 (kPa)：{pressures}{target_zh}", f"Pressure case (kPa): {pressures}{target_en}")
                if objective.kind == "contact":
                    load += T(" · 固定圆柱接触", " · fixed-cylinder contact")
            else:
                target_zh = "" if objective.kind == "stiffness" else f" · 目标挠度 {objective.target:g} mm"
                target_en = "" if objective.kind == "stiffness" else f" · target deflection {objective.target:g} mm"
                load = T(f"末端 −Z 载荷 {objective.force_n:g} N{target_zh}", f"Tip load −Z {objective.force_n:g} N{target_en}")
            parts.append(T(f"{index}. {label} · 权重 {objective.weight:g} · {load}", f"{index}. {label} · weight {objective.weight:g} · {load}"))
        parts.append(T("生成后可直接预览、保存或进入优化器，也可展开模型继续细调。", "Preview, save or run the generated model, or expand its tree for further editing."))
        self.summary.setText("<br><br>".join(parts))
        try:
            o.validate()
        except ValueError as exc:
            self.error.setText(str(exc))
            self.create_button.setEnabled(False)
        else:
            self.error.clear()
            self.create_button.setEnabled(True)

    def _browse_folder(self):
        directory = QFileDialog.getExistingDirectory(self, T("结果目录", "Output folder"), self.fields["result_folder"].text())
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
