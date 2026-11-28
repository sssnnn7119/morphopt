"""Configure and preview exports from completed optimization iterations."""

from __future__ import annotations

import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PySide6.QtCore import QProcess, QRect, QSignalBlocker, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...constants import CONSTANT
from ...postprocess import IterationModel, OptimizationArchive, design_view_options
from ...postprocess.visualization import camera_state, draw_history_scene, set_camera
from ...shapeopt.boundary_part import BoundaryPart
from ...utils.paths import sanitize_name
from ..application.results import ResultSession
from ..i18n import tr, translated_or
from ..presentation.labels import component_selection_title, design_view_title
from ..processes import start_worker
from .file_dialogs import choose_save_directory, choose_save_file, confirm_overwrite
from .viewport import VIEWS, PlotViewport


def label(key: str) -> str:
    return tr("ui.history_export." + key)


def spin(minimum: int, maximum: int, value: int) -> QSpinBox:
    box = QSpinBox()
    box.setRange(minimum, maximum)
    box.setValue(value)
    return box


def _camera_axes(yaw: float, pitch: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return forward, right and unrolled up for a Z-up camera (angles in radians)."""
    c, s = math.cos(yaw), math.sin(yaw)
    forward = np.array([c * math.cos(pitch), s * math.cos(pitch), math.sin(pitch)])
    right = np.array([s, -c, 0.0])
    return forward, right, np.cross(right, forward)


class ExportViewport(QWidget):
    """Frame the interactive scene at the aspect ratio of the exported GIF."""

    def __init__(self, size: tuple[int, int]):
        super().__init__()
        self.output_size = QSize(*size)
        self.outline = QFrame(self)
        self.outline.setObjectName("gifPreviewOutline")
        self.outline.setFrameShape(QFrame.Shape.Box)
        self.view = PlotViewport(self.outline, controls=False)
        self.setMinimumSize(260, 180)

    def fit_frame(self):
        margins = self.outline.contentsMargins()
        available = self.rect().marginsRemoved(margins).size()
        size = self.output_size.scaled(available, Qt.AspectRatioMode.KeepAspectRatio)
        rect = QRect(0, 0, size.width(), size.height()).marginsAdded(margins)
        rect.moveCenter(self.rect().center())
        self.outline.setGeometry(rect)
        self.view.setGeometry(self.outline.contentsRect())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_frame()


class GifOptions(QWidget):
    """Choose an archived scene, frame range, and camera for rendering and playback."""

    def __init__(self, results, camera, size, style, initial_target):
        super().__init__()
        self.style = dict(style)
        self.archive = OptimizationArchive(results.folder)
        self._has_camera = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._draw)
        self.camera = camera
        self.components = results.fea_components()
        self.cases = results.deformation_cases()
        layout = QHBoxLayout(self)
        form = self.form = QFormLayout()
        layout.addLayout(form)
        self.source = QComboBox()
        self.source.addItem(label("design"), "design")
        self.source.addItem(label("deformation"), "deformation")
        self.source.setCurrentIndex(
            int("case" in initial_target or not self.components)
        )
        form.addRow(label("source"), self.source)
        self.target = QComboBox()
        form.addRow(tr("ui.history_gif.target"), self.target)
        self.view = QComboBox()
        form.addRow(label("design_view"), self.view)
        self.first = spin(1, results.iteration, 1)
        self.last = spin(1, results.iteration, results.iteration)
        self.first.valueChanged.connect(self.last.setMinimum)
        form.addRow(tr("ui.history_gif.first_iteration"), self.first)
        form.addRow(tr("ui.history_gif.last_iteration"), self.last)
        self.fps = spin(1, 60, 8)
        form.addRow(tr("ui.history_gif.fps"), self.fps)
        self.resolution_preset = QComboBox()
        for width, height in dict.fromkeys(
            [size, (640, 480), (1280, 720), (1920, 1080)]
        ):
            self.resolution_preset.addItem(f"{width} × {height}", [width, height])
        self.resolution_preset.addItem(label("custom_size"), None)
        form.addRow(label("resolution"), self.resolution_preset)
        self.dimensions = QHBoxLayout()
        # GIF stores each pixel dimension as an unsigned 16-bit integer.
        self.pixel_width, self.pixel_height = (spin(1, 65535, n) for n in size)
        for key, field in (("width", self.pixel_width), ("height", self.pixel_height)):
            caption = QLabel(label(key))
            caption.setBuddy(field)
            self.dimensions.addWidget(caption)
            self.dimensions.addWidget(field, 1)
            field.setKeyboardTracking(False)
        form.addRow("", self.dimensions)
        form.setRowVisible(self.dimensions, False)
        self.preset = QComboBox()
        if camera.get("position"):
            self.preset.addItem(label("source_camera"), "source")
        for name in VIEWS:
            self.preset.addItem(
                tr("ui.visualization.isometric")
                if name == "isometric"
                else name.upper(),
                name,
            )
        self.preset.setPlaceholderText(tr("ui.visualization.choose_view"))
        form.addRow(label("camera"), self.preset)
        self.position = self._pose_row("eye", ("X", "Y", "Z"), (1e12,) * 3)
        self.angles = self._pose_row(
            "angles",
            tuple(label(key) for key in ("yaw", "pitch", "roll")),
            (180, 90, 180),
            degrees=True,
        )
        self.projection = QComboBox()
        self.projection.addItem(tr("ui.visualization.perspective"), False)
        self.projection.addItem(tr("ui.visualization.parallel"), True)
        self.projection.setCurrentIndex(int(camera.get("parallel_projection", False)))
        form.addRow(tr("ui.visualization.projection"), self.projection)

        self.view_height = QDoubleSpinBox()
        self.view_height.setDecimals(8)
        self.view_height.setRange(1e-8, 1e12)
        self.view_height.setKeyboardTracking(False)
        form.addRow(label("view_height"), self.view_height)
        form.setRowVisible(self.view_height, self.projection.currentData())

        self.background = QPushButton()
        self.background.clicked.connect(self._choose_background)
        form.addRow(label("background"), self.background)
        self._set_background(QColor(self.style["background"]))

        preview = QVBoxLayout()
        layout.addLayout(preview, 1)
        hint = QLabel(label("last_frame"))
        hint.setWordWrap(True)
        self.frame = ExportViewport(size)
        self.viewport = self.frame.view
        header = QHBoxLayout()
        header.addWidget(hint, 1)
        self.fit_button = QPushButton(tr("ui.visualization.fit"))
        self.fit_button.clicked.connect(self.viewport.fit_view)
        header.addWidget(self.fit_button)
        preview.addLayout(header)
        preview.addWidget(self.frame, 1)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.hide()
        preview.addWidget(self.error)

        self.source.currentIndexChanged.connect(self._targets)
        self.target.currentIndexChanged.connect(self._views)
        self._targets()
        for i in range(self.target.count()):
            data = self.target.itemData(i)
            if all(initial_target.get(k) == v for k, v in data.items()):
                self.target.setCurrentIndex(i)
                break
        index = self.view.findData(initial_target.get("view", ""))
        if index >= 0:
            self.view.setCurrentIndex(index)
        self.preset.activated.connect(self._apply_preset)
        for field in self.position:
            field.valueChanged.connect(self._set_position)
        for field in self.angles:
            field.valueChanged.connect(self._set_angles)
        self.projection.currentIndexChanged.connect(self._set_projection)
        for combo in (self.source, self.target, self.view):
            combo.currentIndexChanged.connect(self._queue_scene)
        self.first.valueChanged.connect(self._queue_scene)
        self.last.valueChanged.connect(self._queue_scene)
        self.resolution_preset.currentIndexChanged.connect(self._resize_frame)
        self.pixel_width.valueChanged.connect(self._resize_frame)
        self.pixel_height.valueChanged.connect(self._resize_frame)
        self.view_height.valueChanged.connect(self._set_view_height)
        # VTK updates several camera properties during one mouse event. Read the final pose
        # once Qt regains control, including during a drag and after wheel zoom or a preset.
        self._pose_timer = QTimer(self)
        self._pose_timer.setSingleShot(True)
        self._pose_timer.timeout.connect(self._sync_pose)
        self._camera_observer = self.viewport.plotter.camera.AddObserver(
            "ModifiedEvent", lambda *_: self._pose_timer.start(0)
        )

    def _pose_row(self, key, names, limits, *, degrees=False):
        row = QHBoxLayout()
        fields = []
        for name, limit in zip(names, limits):
            box = QDoubleSpinBox()
            box.setDecimals(3 if degrees else 6)
            box.setRange(-limit, limit)
            box.setKeyboardTracking(False)
            box.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            box.setMinimumWidth(box.fontMetrics().horizontalAdvance("−180.000") + 30)
            column = QVBoxLayout()
            caption = QLabel(f"{name} (°)" if degrees else name)
            caption.setBuddy(box)
            column.addWidget(caption)
            column.addWidget(box)
            row.addLayout(column, 1)
            fields.append(box)
        self.form.addRow(label(key), row)
        return fields

    def _targets(self):
        self.target.clear()
        design = self.source.currentData() == "design"
        if design:
            for category, component in self.components:
                self.target.addItem(
                    component_selection_title(category, component),
                    {"category": category, "name": component.name},
                )
        else:
            for case in self.cases:
                self.target.addItem(case, {"case": case})
        self.form.setRowVisible(self.view, design)
        self._views()

    def _views(self):
        self.view.clear()
        index = self.target.currentIndex()
        if self.source.currentData() == "design" and index >= 0:
            for view in design_view_options(self.components[index][1]):
                self.view.addItem(design_view_title(view), view.key)

    def _resize_frame(self):
        preset = self.resolution_preset.currentData()
        self.form.setRowVisible(self.dimensions, preset is None)
        width, height = preset or (self.pixel_width.value(), self.pixel_height.value())
        self.frame.output_size = QSize(width, height)
        self.frame.fit_frame()

    def _sync_pose(self):
        """Display the preview camera's world position and yaw, pitch and roll in degrees."""
        camera = self.viewport.plotter.camera
        parallel = bool(camera.parallel_projection)
        self.form.setRowVisible(self.view_height, parallel)
        if parallel:
            with QSignalBlocker(self.view_height):
                self.view_height.setValue(2 * camera.parallel_scale)
        x, y, z = camera.direction
        horizontal = math.hypot(x, y)
        # At a vertical view yaw and roll are coupled. Keep the displayed yaw as reference.
        yaw = (
            math.atan2(y, x)
            if horizontal > 1e-10
            else math.radians(self.angles[0].value())
        )
        pitch = math.atan2(z, horizontal)
        _, right, up = _camera_axes(yaw, pitch)
        roll = math.atan2(np.dot(camera.up, right), np.dot(camera.up, up))
        for fields, values in (
            (self.position, camera.position),
            (self.angles, np.degrees([yaw, pitch, roll])),
        ):
            for field, value in zip(fields, values):
                with QSignalBlocker(field):
                    field.setValue(value)

    def _set_position(self):
        plotter = self.viewport.plotter
        camera = plotter.camera
        eye = np.array([field.value() for field in self.position])
        focus = eye + np.asarray(camera.direction) * camera.distance
        plotter.camera_position = eye, focus, camera.up
        plotter.render()

    def _set_angles(self):
        plotter = self.viewport.plotter
        camera = plotter.camera
        yaw, pitch, roll = (math.radians(field.value()) for field in self.angles)
        forward, right, up = _camera_axes(yaw, pitch)
        focus = np.asarray(camera.position) + camera.distance * forward
        plotter.camera_position = (
            camera.position,
            focus,
            math.cos(roll) * up + math.sin(roll) * right,
        )
        plotter.render()

    def _set_projection(self):
        plotter = self.viewport.plotter
        if self.projection.currentData():
            plotter.enable_parallel_projection()
        else:
            plotter.disable_parallel_projection()
        plotter.render()

    def _set_view_height(self, height: float):
        """Set the full vertical span of the parallel view in model units."""
        plotter = self.viewport.plotter
        plotter.camera.parallel_scale = height / 2
        plotter.render()

    def _apply_preset(self):
        preset = self.preset.currentData()
        plotter = self.viewport.plotter
        if preset == "source":
            set_camera(plotter, self.camera)
            with QSignalBlocker(self.projection):
                self.projection.setCurrentIndex(int(plotter.camera.parallel_projection))
        else:
            self.viewport.set_view(preset)
        self.preset.setCurrentIndex(-1)
        self._sync_pose()
        plotter.render()

    def _target(self):
        target = dict(self.target.currentData() or {})
        if self.source.currentData() == "design" and self.view.currentData():
            target["view"] = self.view.currentData()
        return target

    def _queue_scene(self):
        self._timer.start(0)

    def _draw(self):
        """Load only the selected final iteration and preserve the user's camera across redraws."""
        self._timer.stop()
        plotter = self.viewport.plotter
        pose = camera_state(plotter) if self._has_camera else None
        try:
            target = self._target()
            if not target:
                raise ValueError(tr("ui.history_gif.target_unavailable"))
            # As in the GIF writer, skip steps without a saved deformation.
            for step in range(self.last.value(), self.first.value() - 1, -1):
                if draw_history_scene(
                    plotter,
                    self.archive,
                    step,
                    self.source.currentData(),
                    target,
                    self.style,
                ):
                    break
            else:
                raise ValueError(label("preview_failed"))
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            plotter.clear()
            self.error.setText(str(exc))
            self.error.show()
        else:
            self.error.hide()
            plotter.show_axes()
            if pose:
                set_camera(plotter, pose)
            else:
                plotter.camera.parallel_projection = self.projection.currentData()
                self._apply_preset()
                self._has_camera = True
        plotter.render()

    def options(self) -> dict:
        """Freeze the interactive preview camera for every exported frame."""
        if self._timer.isActive() or not self._has_camera:
            self._draw()
        if not self.error.isHidden():
            raise ValueError(self.error.text())
        return dict(
            action="export_gif",
            mode=self.source.currentData(),
            target=self._target(),
            first_iteration=self.first.value(),
            last_iteration=self.last.value(),
            fps=self.fps.value(),
            window_size=self.frame.output_size.toTuple(),
            camera=camera_state(self.viewport.plotter),
            style=dict(self.style),
        )

    def _choose_background(self):
        color = QColorDialog.getColor(
            QColor(self.style["background"]), self, label("background")
        )
        if color.isValid():
            self._set_background(color)
            self._queue_scene()

    def _set_background(self, color: QColor):
        self.style["background"] = color.name()
        swatch = QPixmap(20, 20)
        swatch.fill(color)
        self.background.setIcon(QIcon(swatch))
        self.background.setText(color.name().upper())

    def showEvent(self, event):
        super().showEvent(event)
        if not self._has_camera:
            self._queue_scene()

    def close_preview(self):
        self._timer.stop()
        self.viewport.plotter.camera.RemoveObserver(self._camera_observer)
        self._pose_timer.stop()
        self.viewport.plotter.close()


class HistoryExportDialog(QDialog):
    """Export GIFs, boundary geometry, or Abaqus jobs from a single history window."""

    def __init__(
        self,
        results: ResultSession,
        iteration: int,
        camera: dict,
        size: tuple,
        style: dict,
        *,
        initial_target=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(label("title"))
        self.resize(950, 525)
        self.folder = results.folder
        self._temporary = TemporaryDirectory(prefix="morphopt-history-export-")
        self._directory = Path(self._temporary.name)
        self._process = QProcess(self)
        self._process.finished.connect(self._completed)
        self._process.errorOccurred.connect(self._failed)
        self._active = False
        self._request = {}
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.gif = GifOptions(results, camera, size, style, initial_target or {})
        self.tabs.addTab(self.gif, label("gif"))

        component_page = QWidget()
        layout_components = QVBoxLayout(component_page)
        form = self.component_form = QFormLayout()
        self.component_step = spin(1, results.iteration, iteration)
        form.addRow(label("iteration"), self.component_step)
        self.component = QComboBox()
        form.addRow(label("component"), self.component)
        self.component_mode = QComboBox()
        form.addRow(label("output"), self.component_mode)
        self.surface_group = QGroupBox(label("surface_formats"))
        self.surface_form = QFormLayout(self.surface_group)
        self.surface_choices: list[QComboBox] = []
        form.addRow(self.surface_group)
        self.voxel_size = QDoubleSpinBox()
        self.voxel_size.setDecimals(6)
        self.voxel_size.setRange(0.000001, 1e6)
        self.voxel_size.setValue(CONSTANT.KERNEL.SIMP.EXPORT_VOXEL_SIZE)
        form.addRow(label("voxel_size"), self.voxel_size)
        self.voxel_threshold = QDoubleSpinBox()
        self.voxel_threshold.setDecimals(6)
        self.voxel_threshold.setRange(0, 1)
        self.voxel_threshold.setSingleStep(0.05)
        self.voxel_threshold.setValue(CONSTANT.KERNEL.SIMP.EXPORT_DENSITY_THRESHOLD)
        form.addRow(label("voxel_threshold"), self.voxel_threshold)
        self.component_mode.currentIndexChanged.connect(self._component_options)
        layout_components.addLayout(form)
        self.empty_components = QLabel(label("no_components"))
        layout_components.addWidget(self.empty_components)
        layout_components.addStretch()
        component_scroll = QScrollArea()
        component_scroll.setWidgetResizable(True)
        component_scroll.setWidget(component_page)
        self.tabs.addTab(component_scroll, label("components"))

        inp_page = QWidget()
        inp = self.inp_form = QFormLayout(inp_page)
        self.inp_kind = QComboBox()
        self.inp_kind.addItem(label("static_job"), "job")
        self.inp_kind.addItem(label("parts_only"), "parts")
        inp.addRow(label("inp_content"), self.inp_kind)
        self.inp_step = QComboBox()
        self.inp_case = QComboBox()
        for step in IterationModel.iterations(self.folder):
            if step <= results.iteration:
                self.inp_step.addItem(str(step), step)
        ix = self.inp_step.findData(iteration)
        self.inp_step.setCurrentIndex(ix if ix >= 0 else self.inp_step.count() - 1)
        inp.addRow(label("iteration"), self.inp_step)
        inp.addRow(label("case"), self.inp_case)
        self.nlgeom = QCheckBox(label("nlgeom"))
        self.nlgeom.setChecked(True)
        inp.addRow(self.nlgeom)
        self.inp_hint = QLabel()
        self.inp_hint.setWordWrap(True)
        inp.addRow(self.inp_hint)
        self.tabs.addTab(inp_page, "Abaqus INP")

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton(tr("ui.files.cancel"))
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.export = QPushButton(label("save"))
        self.export.setProperty("actionRole", "primary")
        self.export.clicked.connect(self._export)
        buttons.addWidget(self.export)
        layout.addLayout(buttons)
        self._component_session = results
        self._initial_target = initial_target
        self.tabs.currentChanged.connect(self._select_tab)
        self.gif.target.currentIndexChanged.connect(self._availability)
        self.inp_step.currentIndexChanged.connect(self._cases)
        self.inp_kind.currentIndexChanged.connect(self._cases)
        self.component.currentIndexChanged.connect(self._component_modes)
        self._component_modes()
        self._cases()

    def _select_tab(self, index):
        # Native exports require task code; opening the GIF preview only needs VTK files.
        if index == 1 and self._component_session is not None:
            results, self._component_session = self._component_session, None
            initial_target = self._initial_target
            for category, component in results.design_components():
                if component.export_modes:
                    self.component.addItem(
                        component_selection_title(category, component),
                        (category, component),
                    )
            if initial_target:
                for index in range(self.component.count()):
                    category, component = self.component.itemData(index)
                    if (category, component.name) == (
                        initial_target.get("category"),
                        initial_target.get("name"),
                    ):
                        self.component.setCurrentIndex(index)
                        break
            self.empty_components.setVisible(not self.component.count())
        self._availability()

    def _cases(self):
        self.inp_case.clear()
        step = self.inp_step.currentData()
        if step is not None:
            self.inp_case.addItems(IterationModel(self.folder, step).cases())
        job = self.inp_kind.currentData() == "job"
        self.inp_form.setRowVisible(self.inp_case, job)
        self.inp_form.setRowVisible(self.nlgeom, job)
        hint = "inp_hint" if job else "parts_hint"
        self.inp_hint.setText(label(hint if self._inp_available() else "no_model"))
        self._availability()

    def _inp_available(self) -> bool:
        return bool(
            self.inp_case.count()
            if self.inp_kind.currentData() == "job"
            else self.inp_step.count()
        )

    def _component_modes(self):
        with QSignalBlocker(self.component_mode):
            self.component_mode.clear()
            if self.component.currentData():
                _, component = self.component.currentData()
                for mode in component.export_modes:
                    title = translated_or(f"ui.history_export.{mode}", mode)
                    self.component_mode.addItem(title, mode)
        self.component_form.setRowVisible(self.component_mode, self.component_mode.count() > 1)
        self._component_options()

    def _component_options(self):
        mode = self.component_mode.currentData()
        self.component_form.setRowVisible(self.voxel_size, mode == "voxel_obj")
        self.component_form.setRowVisible(self.voxel_threshold, mode == "voxel_obj")
        self.surface_choices.clear()
        while self.surface_form.rowCount():
            self.surface_form.removeRow(0)
        if mode == "all_surfaces":
            _, component = self.component.currentData()
            if isinstance(component, BoundaryPart):
                for index, surface in enumerate(component.surface_interfaces()):
                    choice = QComboBox()
                    for fmt in surface.export_formats:
                        choice.addItem(fmt.name, fmt.value)
                    choice.setEnabled(choice.count() > 1)
                    self.surface_form.addRow(f"surface_{index} [{type(surface).__name__}]", choice)
                    self.surface_choices.append(choice)
        self.surface_group.setVisible(bool(self.surface_choices))
        self._availability()

    def _availability(self):
        enabled = (
            self.gif.target.count(),
            self.component_mode.count() and all(choice.count() for choice in self.surface_choices),
            self._inp_available(),
        )
        self.export.setEnabled(
            bool(enabled[self.tabs.currentIndex()]) and not self._active
        )

    def _gif_request(self):
        try:
            return self.gif.options()
        except ValueError as exc:
            QMessageBox.warning(self, self.windowTitle(), str(exc))
            return None

    def _export(self):
        tab = self.tabs.currentIndex()
        if tab == 1:
            step = self.component_step.value()
            category, component = self.component.currentData()
            name = sanitize_name(component.name)
            destination = choose_save_directory(
                self, self.windowTitle(), self.folder, f"{name}_{step}"
            )
            if not destination:
                return
            exists = Path(destination).exists()
            if exists and not confirm_overwrite(
                self,
                Path(destination),
                message_key="ui.history_export.component_overwrite",
            ):
                return
            selection = dict(
                category=category,
                name=component.name,
                mode=self.component_mode.currentData(),
            )
            if any(choice.currentIndex() > 0 for choice in self.surface_choices):
                selection["options"] = {
                    "surface_formats": [choice.currentData() for choice in self.surface_choices]
                }
            elif selection["mode"] == "voxel_obj":
                selection["options"] = dict(
                    voxel_size=self.voxel_size.value(),
                    threshold=self.voxel_threshold.value(),
                )
            self._start(
                dict(
                    action="export_components",
                    iteration=step,
                    selections=[selection],
                    overwrite=exists,
                ),
                destination,
            )
            return
        if tab == 0:
            request = self._gif_request()
            if not request:
                return
            name = request["target"].get("name") or request["target"].get("case")
            formats = {"gif": tr("ui.history_gif.file_filter")}
        else:
            step = self.inp_step.currentData()
            case = (
                self.inp_case.currentText()
                if self.inp_kind.currentData() == "job"
                else None
            )
            request = dict(
                action="export_inp",
                iteration=step,
                case=case,
                nlgeom=self.nlgeom.isChecked(),
            )
            name = f"iteration_{step}_{case or 'mesh'}"
            formats = {"inp": "Abaqus (*.inp)"}
        selected = choose_save_file(
            self, self.windowTitle(), self.folder, sanitize_name(name), formats
        )
        if selected is None:
            return
        self._start(request, selected.path)

    def _start(self, options, destination):
        self._request = dict(options, folder=self.folder, destination=str(destination))
        path = self._directory / "request.json"
        path.write_text(json.dumps(self._request, ensure_ascii=False), encoding="utf-8")
        self._active = True
        self.tabs.setEnabled(False)
        self.export.setEnabled(False)
        self.progress.show()
        start_worker(self._process, path)

    def _idle(self):
        self._active = False
        self.tabs.setEnabled(True)
        self.progress.hide()
        self._availability()

    def _failed(self, error):
        if error == QProcess.ProcessError.FailedToStart and self._active:
            self._idle()
            QMessageBox.warning(self, self.windowTitle(), self._process.errorString())

    def _completed(self, code, status):
        if not self._active:
            return
        output = bytes(self._process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        self._idle()
        if code or status != QProcess.ExitStatus.NormalExit:
            message = QMessageBox(
                QMessageBox.Icon.Warning,
                self.windowTitle(),
                label("failed"),
                parent=self,
            )
            if output.strip():
                reason = output.strip().splitlines()[-1]
                if self._request["action"] == "export_inp" and self._request["case"]:
                    reason += "\n" + label("parts_alternative")
                message.setInformativeText(reason)
            message.setDetailedText(output)
            message.exec()
            return
        self._success(self._request["destination"])

    def _success(self, path):
        QMessageBox.information(
            self, self.windowTitle(), tr("ui.history_export.completed", path=str(path))
        )
        self.accept()

    def done(self, result):
        if self._active:
            self._active = False
            self._process.kill()
            self._process.waitForFinished(-1)
            if self._request["action"] == "export_gif":
                path = Path(self._request["destination"])
                path.with_name(f".{path.stem}.partial.gif").unlink(missing_ok=True)
        self.gif.close_preview()
        self._temporary.cleanup()
        super().done(result)
