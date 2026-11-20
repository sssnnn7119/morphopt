"""Configure and preview exports from completed optimization iterations."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PySide6.QtCore import QProcess, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QLabel, QMessageBox, QProgressBar, QPushButton, QSizePolicy,
    QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from ...constants import CONSTANT
from ...postprocess import IterationModel, design_view_options
from ...utils.paths import sanitize_name
from ..application.results import ResultSession
from ..i18n import tr, translated_or
from ..presentation.labels import component_selection_title, design_view_title
from ..processes import start_worker
from .file_dialogs import choose_save_directory, choose_save_file, confirm_overwrite
from .viewport import VIEWS


def label(key: str) -> str:
    return tr("ui.history_export." + key)


def spin(minimum: int, maximum: int, value: int) -> QSpinBox:
    box = QSpinBox()
    box.setRange(minimum, maximum)
    box.setValue(value)
    return box


class GifOptions(QWidget):
    """Choose an archived scene, frame range, and camera for rendering and playback."""

    def __init__(self, results, camera, size, style, initial_target, directory: Path):
        super().__init__()
        self.style = dict(style)
        self._theme_text = QColor(style["text_color"])
        self.folder = results.folder
        self.directory = directory
        self.directory.mkdir()
        self._frame = QPixmap()
        self._requested = None
        self._rendering = None
        self._process = QProcess(self)
        self._process.finished.connect(self._preview_finished)
        self._process.errorOccurred.connect(self._preview_error)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self._render_preview)
        self.camera = camera
        self.components = results.fea_components()
        self.cases = results.deformation_cases()
        layout = QHBoxLayout(self)
        form = self.form = QFormLayout()
        layout.addLayout(form)
        self.source = QComboBox()
        self.source.addItem(label("design"), "design")
        self.source.addItem(label("deformation"), "deformation")
        self.source.setCurrentIndex(int("case" in initial_target or not self.components))
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
        self.size = QComboBox()
        for width, height in dict.fromkeys([size, (640, 480), (1280, 720), (1920, 1080)]):
            self.size.addItem(f"{width} × {height}", [width, height])
        form.addRow(label("resolution"), self.size)
        self.preset = QComboBox()
        if camera.get("position"):
            self.preset.addItem(label("source_camera"), "source")
        for name in VIEWS:
            self.preset.addItem(tr("ui.visualization.isometric") if name == "isometric"
                                else name.upper(), name)
        self.preset.addItem(label("custom_camera"), "custom")
        form.addRow(label("camera"), self.preset)
        self.vectors = []
        self.camera_fields = QWidget()
        vectors = QFormLayout(self.camera_fields)
        vectors.setContentsMargins(0, 0, 0, 0)
        positions = camera.get("position", ((1, 1, 1), (0, 0, 0), (0, 0, 1)))
        for key, values in zip(("eye", "focus", "up"), positions):
            row = QHBoxLayout()
            boxes = []
            for axis, value in zip("XYZ", values):
                box = QDoubleSpinBox()
                box.setDecimals(6)
                box.setRange(-1e12, 1e12)
                box.setPrefix(axis + " ")
                box.setValue(value)
                box.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
                box.setMinimumWidth(82)
                row.addWidget(box)
                boxes.append(box)
            vectors.addRow(label(key), row)
            self.vectors.append(boxes)
        form.addRow(self.camera_fields)
        self.parallel = QCheckBox(label("parallel"))
        self.parallel.setChecked(camera.get("parallel_projection", False))
        form.addRow(self.parallel)

        self.background = QPushButton()
        self.background.clicked.connect(self._choose_background)
        form.addRow(label("background"), self.background)
        self._set_background(QColor(self.style["background"]))

        preview = QVBoxLayout()
        layout.addLayout(preview, 1)
        preview.addWidget(QLabel(label("last_frame")))
        self.image = QLabel()
        self.image.setWordWrap(True)
        self.image.setMinimumSize(260, 180)
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        preview.addWidget(self.image, 1)

        self.source.currentIndexChanged.connect(self._targets)
        self.target.currentIndexChanged.connect(self._views)
        self.preset.currentIndexChanged.connect(self._camera_fields)
        self._targets()
        for i in range(self.target.count()):
            data = self.target.itemData(i)
            if all(initial_target.get(k) == v for k, v in data.items()):
                self.target.setCurrentIndex(i)
                break
        index = self.view.findData(initial_target.get("view", ""))
        if index >= 0:
            self.view.setCurrentIndex(index)
        self._camera_fields()
        for combo in (self.source, self.target, self.view, self.size, self.preset):
            combo.currentIndexChanged.connect(self._schedule_preview)
        for row in self.vectors:
            for box in row:
                box.valueChanged.connect(self._schedule_preview)
        self.parallel.toggled.connect(self._schedule_preview)
        self.last.valueChanged.connect(self._schedule_preview)

    def _targets(self):
        self.target.clear()
        design = self.source.currentData() == "design"
        if design:
            for category, component in self.components:
                self.target.addItem(component_selection_title(category, component),
                                    {"category": category, "name": component.name})
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

    def _camera_fields(self):
        self.camera_fields.setVisible(self.preset.currentData() == "custom")

    def options(self) -> dict:
        """Return a worker request shared by the preview and the saved GIF."""
        target = self.target.currentData()
        if target is None:
            raise ValueError(tr("ui.history_gif.target_unavailable"))
        if self.view.currentData():
            target["view"] = self.view.currentData()
        preset = self.preset.currentData()
        if preset == "source":
            camera = dict(self.camera)
        elif preset == "custom":
            position = [[box.value() for box in row] for row in self.vectors]
            direction = np.subtract(position[1], position[0])
            if not np.linalg.norm(np.cross(direction, position[2])):
                raise ValueError(label("invalid_camera"))
            camera = {**self.camera, "position": position}
        else:
            direction, up = VIEWS[preset]
            camera = {"direction": list(direction), "up": list(up)}
        camera["parallel_projection"] = self.parallel.isChecked()
        return dict(action="export_gif", mode=self.source.currentData(), target=target,
                    first_iteration=self.first.value(), last_iteration=self.last.value(),
                    fps=self.fps.value(), window_size=self.size.currentData(),
                    camera=camera, style=dict(self.style))

    def _choose_background(self):
        color = QColorDialog.getColor(QColor(self.style["background"]), self, label("background"))
        if color.isValid():
            self._set_background(color)
            self._schedule_preview()

    def _set_background(self, color: QColor):
        self.style["background"] = color.name()
        # Keep the iteration label legible when the export background changes.
        def brightness(c: QColor) -> float:
            return 0.299 * c.redF() + 0.587 * c.greenF() + 0.114 * c.blueF()

        level = brightness(color)
        self.style["text_color"] = (self._theme_text.name() if abs(level - brightness(self._theme_text)) >= 0.45
                                    else "#000000" if level > 0.5 else "#ffffff")
        swatch = QPixmap(20, 20)
        swatch.fill(color)
        self.background.setIcon(QIcon(swatch))
        self.background.setText(color.name().upper())

    def showEvent(self, event):
        super().showEvent(event)
        self._schedule_preview()

    def _schedule_preview(self):
        if not self.isVisible():
            return
        try:
            request = self.options()
        except ValueError as exc:
            self._requested = None
            self._frame = QPixmap()
            self.image.setText(str(exc))
            return
        request["action"] = "preview_history"
        request["iteration"] = request.pop("last_iteration")
        del request["first_iteration"], request["fps"]
        if request != self._requested:
            self._requested = request
            self._frame = QPixmap()
            self.image.setText(label("loading_preview"))
            self._timer.start()

    def _render_preview(self):
        if self._rendering is not None or self._requested is None or not self.isVisible():
            return
        self._rendering = self._requested
        path = self.directory / "request.json"
        path.write_text(json.dumps(dict(self._rendering, folder=self.folder,
                                        destination=str(self.directory / "frame.png"))), encoding="utf-8")
        start_worker(self._process, path)

    def _preview_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._preview_finished(1, QProcess.ExitStatus.CrashExit)

    def _preview_finished(self, code, status):
        rendered = self._rendering
        self._rendering = None
        output = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if rendered is None:
            return
        if rendered != self._requested:
            self._timer.start()
            return
        self._timer.stop()
        if code == 0 and status == QProcess.ExitStatus.NormalExit:
            self._frame = QPixmap.fromImage(QImage(str(self.directory / "frame.png")))
        if self._frame.isNull():
            self.image.setText(label("preview_failed"))
            self.image.setToolTip(output.strip() or self._process.errorString())
        else:
            self.image.setToolTip("")
            self._fit_frame()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_frame()

    def _fit_frame(self):
        if not self._frame.isNull():
            self.image.setPixmap(self._frame.scaled(self.image.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                    Qt.TransformationMode.SmoothTransformation))

    def hideEvent(self, event):
        self._timer.stop()
        if self._frame.isNull():
            self._requested = None
        super().hideEvent(event)

    def stop_preview(self):
        self._timer.stop()
        self._rendering = None
        if self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()
            self._process.waitForFinished(-1)


class HistoryExportDialog(QDialog):
    """Export GIFs, boundary geometry, or Abaqus jobs from a single history window."""

    def __init__(self, results: ResultSession, iteration: int, camera: dict, size: tuple,
                 style: dict, *, initial_target=None, parent=None):
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
        self.gif = GifOptions(results, camera, size, style, initial_target or {}, self._directory / "preview")
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
        self.component_mode.currentIndexChanged.connect(self._voxel_options)
        self._voxel_options()
        layout_components.addLayout(form)
        self.empty_components = QLabel(label("no_components"))
        layout_components.addWidget(self.empty_components)
        layout_components.addStretch()
        self.tabs.addTab(component_page, label("components"))

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
                    self.component.addItem(component_selection_title(category, component),
                                           (category, component.name, component.export_modes))
            if initial_target:
                for index in range(self.component.count()):
                    category, name, _ = self.component.itemData(index)
                    if (category, name) == (initial_target.get("category"), initial_target.get("name")):
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
        return bool(self.inp_case.count() if self.inp_kind.currentData() == "job" else self.inp_step.count())

    def _component_modes(self):
        self.component_mode.clear()
        if self.component.count():
            _, _, modes = self.component.currentData()
            for mode in modes:
                title = translated_or(f"ui.history_export.{mode}", mode)
                self.component_mode.addItem(title, mode)
        self._availability()

    def _voxel_options(self):
        visible = self.component_mode.currentData() == "voxel_obj"
        self.component_form.setRowVisible(self.voxel_size, visible)
        self.component_form.setRowVisible(self.voxel_threshold, visible)

    def _availability(self):
        enabled = (self.gif.target.count(), self.component_mode.count(), self._inp_available())
        self.export.setEnabled(bool(enabled[self.tabs.currentIndex()]) and not self._active)

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
            category, component_name, _ = self.component.currentData()
            name = sanitize_name(component_name)
            destination = choose_save_directory(self, self.windowTitle(), self.folder, f"{name}_{step}")
            if not destination:
                return
            exists = Path(destination).exists()
            if exists and not confirm_overwrite(self, Path(destination), message_key="ui.history_export.component_overwrite"):
                return
            selection = dict(category=category, name=component_name, mode=self.component_mode.currentData())
            if selection["mode"] == "voxel_obj":
                selection["options"] = dict(voxel_size=self.voxel_size.value(),
                                            threshold=self.voxel_threshold.value())
            self._start(dict(action="export_components", iteration=step, selections=[selection],
                             overwrite=exists), destination)
            return
        if tab == 0:
            request = self._gif_request()
            if not request:
                return
            name = request["target"].get("name") or request["target"].get("case")
            formats = {"gif": tr("ui.history_gif.file_filter")}
        else:
            step = self.inp_step.currentData()
            case = self.inp_case.currentText() if self.inp_kind.currentData() == "job" else None
            request = dict(action="export_inp", iteration=step, case=case, nlgeom=self.nlgeom.isChecked())
            name = f"iteration_{step}_{case or 'mesh'}"
            formats = {"inp": "Abaqus (*.inp)"}
        selected = choose_save_file(self, self.windowTitle(), self.folder, sanitize_name(name), formats)
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
        output = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._idle()
        if code or status != QProcess.ExitStatus.NormalExit:
            message = QMessageBox(QMessageBox.Icon.Warning, self.windowTitle(), label("failed"), parent=self)
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
        QMessageBox.information(self, self.windowTitle(), tr("ui.history_export.completed", path=str(path)))
        self.accept()

    def done(self, result):
        if self._active:
            self._active = False
            self._process.kill()
            self._process.waitForFinished(-1)
            if self._request["action"] == "export_gif":
                path = Path(self._request["destination"])
                path.with_name(f".{path.stem}.partial.gif").unlink(missing_ok=True)
        self.gif.stop_preview()
        self._temporary.cleanup()
        super().done(result)
