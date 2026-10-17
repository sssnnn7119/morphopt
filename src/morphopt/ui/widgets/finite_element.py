"""Finite-element workspace: private iteration model, independent worker, result export."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

import numpy as np
from PySide6.QtCore import QProcess, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QGroupBox, QHeaderView,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...postprocess import EXPORTERS, RESULT_FIELDS, ResultLocation, available_fields
from ..application.finite_element import FiniteElementResult, FiniteElementSession, IterationModel
from ..application.results import _cpu_torch_defaults
from ..i18n import tr
from ..theme import theme_manager
from .observation_pages import PlotViewport
from .file_dialogs import choose_save_file


class FiniteElementPage(QWidget):
    importObserverRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.session = FiniteElementSession()
        self._job = ''
        self._status_key = ''
        self._status_values = {}
        self._cancelled = False
        self._render_pending = False
        self._loading = False
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._read_output)
        self._process.finished.connect(self._finished)
        self._process.errorOccurred.connect(self._process_error)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self._texts = []
        row = QHBoxLayout()
        self.import_observer = self._button('ui.fea.import_observer', self.importObserverRequested.emit)
        self.open_folder = self._button('ui.fea.open_folder', self._choose_folder)
        row.addWidget(self.import_observer)
        row.addWidget(self.open_folder)
        self.folder = QLineEdit()
        self.folder.setReadOnly(True)
        row.addWidget(self.folder, 1)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(self._label('ui.fea.iteration'))
        self.iterations = QComboBox()
        self.iterations.currentIndexChanged.connect(self._iteration_changed)
        row.addWidget(self.iterations)
        row.addWidget(self._label('ui.fea.result_selection'))
        self.cases = QComboBox()
        self.cases.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.cases.currentIndexChanged.connect(self._load_selected)
        row.addWidget(self.cases)
        self.import_selected = self._button('ui.fea.import_model', self._load_selected)
        row.addWidget(self.import_selected)
        row.addStretch(1)
        self.status = QLabel()
        self.status.setProperty('textRole', 'muted')
        row.addWidget(self.status)
        layout.addLayout(row)

        split = QSplitter(Qt.Orientation.Horizontal)
        controls = QWidget()
        col = QVBoxLayout(controls)
        col.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self.loads_group = QGroupBox()
        self._texts.append((self.loads_group, 'ui.fea.loads'))
        loads_layout = QVBoxLayout(self.loads_group)
        hint = self._label('ui.fea.loads_hint')
        hint.setWordWrap(True)
        hint.setProperty('textRole', 'muted')
        loads_layout.addWidget(hint)
        self.loads = QTableWidget(0, 4)
        self.loads.setMinimumHeight(theme_manager.palette.layout.finite_element.load_table_minimum_height)
        self.loads.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.loads.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.loads.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.loads.itemChanged.connect(self._load_edited)
        loads_layout.addWidget(self.loads)
        row = QHBoxLayout()
        self.solve = self._button('ui.fea.solve', self.start_analysis)
        self.solve.setProperty('actionRole', 'primary')
        self.stop = self._button('ui.fea.stop', self._stop)
        self.stop.setProperty('actionRole', 'danger')
        for button in (self.solve, self.stop):
            row.addWidget(button)
        loads_layout.addLayout(row)
        col.addWidget(self.loads_group, 2)

        self.exports_group = QGroupBox()
        self._texts.append((self.exports_group, 'ui.fea.export'))
        export_layout = QVBoxLayout(self.exports_group)
        row = QHBoxLayout()
        row.addWidget(self._label('ui.fea.export_location'))
        self.export_location = QComboBox()
        for location in ResultLocation:
            self.export_location.addItem(tr('ui.fea.location_' + location.value), location.value)
        self.export_location.currentIndexChanged.connect(self._update_export_fields)
        row.addWidget(self.export_location, 1)
        export_layout.addLayout(row)
        self.field_checks = {}
        for key, provider in RESULT_FIELDS.items():
            check = QCheckBox()
            self._texts.append((check, provider.label_key))
            check.setChecked(True)
            self.field_checks[key] = check
            export_layout.addWidget(check)
        self.no_gauss = self._label('ui.fea.no_gauss')
        self.no_gauss.setWordWrap(True)
        self.no_gauss.setProperty('textRole', 'muted')
        export_layout.addWidget(self.no_gauss)
        self.no_reference_points = self._label('ui.fea.no_reference_points')
        self.no_reference_points.setWordWrap(True)
        self.no_reference_points.setProperty('textRole', 'muted')
        export_layout.addWidget(self.no_reference_points)
        self.export_button = self._button('ui.fea.export_data', self.export_results)
        export_layout.addWidget(self.export_button)
        hint = self._label('ui.fea.export_hint')
        hint.setWordWrap(True)
        hint.setProperty('textRole', 'muted')
        export_layout.addWidget(hint)
        col.addWidget(self.exports_group)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(theme_manager.palette.layout.finite_element.output_maximum_blocks)
        col.addWidget(self.output, 1)
        split.addWidget(controls)

        view = QWidget()
        view_layout = QVBoxLayout(view)
        view_layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        row = QHBoxLayout()
        row.addWidget(self._label('ui.fea.display'))
        self.display_field = QComboBox()
        for key in ('U', 'U1', 'U2', 'U3'):
            self.display_field.addItem(key, key)
        self.display_field.currentIndexChanged.connect(self._render)
        row.addWidget(self.display_field)
        self.deformed = QCheckBox()
        self._texts.append((self.deformed, 'ui.fea.deformed'))
        self.deformed.setChecked(True)
        self.deformed.toggled.connect(self._render)
        row.addWidget(self.deformed)
        row.addStretch(1)
        view_layout.addLayout(row)
        self.viewport = PlotViewport(self)
        view_layout.addWidget(self.viewport, 1)
        split.addWidget(view)
        split.setSizes(list(theme_manager.palette.layout.finite_element.split_sizes))
        layout.addWidget(split, 1)
        self.apply_language()
        self._update_buttons()

    def _button(self, key, slot):
        button = QPushButton()
        self._texts.append((button, key))
        button.clicked.connect(slot)
        return button

    def _label(self, key):
        label = QLabel()
        self._texts.append((label, key))
        return label

    def is_running(self) -> bool:
        return self._process.state() != QProcess.ProcessState.NotRunning

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr('ui.fea.open_folder'), self.folder.text())
        if folder:
            self._set_folder(folder)
            self._load_selected()

    def _set_folder(self, folder: str, iteration: int | None = None) -> None:
        self.folder.setText(str(Path(folder).resolve()))
        self.iterations.blockSignals(True)
        self.iterations.clear()
        for value in IterationModel.iterations(folder):
            self.iterations.addItem(str(value), value)
        index = self.iterations.findData(iteration) if iteration is not None else self.iterations.count() - 1
        self.iterations.setCurrentIndex(index)
        self.iterations.blockSignals(False)
        self._update_cases()
        self._update_buttons()

    def _iteration_changed(self, *_args) -> None:
        self._update_cases()
        self._load_selected()

    def _update_cases(self, selected: FiniteElementResult | None = None) -> None:
        selected = selected or self.cases.currentData()
        iteration = self.iterations.currentData()
        self.cases.blockSignals(True)
        try:
            self.cases.clear()
            if iteration is not None:
                for entry in self.session.result_options(self.folder.text(), iteration):
                    if entry.is_original:
                        label = (tr('ui.fea.original_case', case=entry.source.case)
                                 if entry.source.case is not None else tr('ui.fea.model_loads'))
                    else:
                        label = tr('ui.fea.analysis_result', number=entry.number,
                                   time=entry.created_at.strftime('%H:%M:%S'))
                    self.cases.addItem(label, entry)
                    self.cases.setItemData(self.cases.count() - 1, tr(
                        'ui.fea.result_hint', iteration=entry.source.iteration,
                        case=entry.source.case if entry.source.case is not None else '—',
                    ), Qt.ItemDataRole.ToolTipRole)
            index = self._result_index(selected)
            if index >= 0:
                self.cases.setCurrentIndex(index)
        finally:
            self.cases.blockSignals(False)

    def _result_index(self, entry: FiniteElementResult | None) -> int:
        return next((index for index in range(self.cases.count())
                     if self.cases.itemData(index) == entry), -1)

    def import_iteration(self, folder: str, iteration: int) -> None:
        if self.is_running():
            QMessageBox.information(self, tr('ui.workspace.finite_element'), tr('ui.fea.busy'))
            return
        self._set_folder(folder, iteration)
        if self.iterations.currentIndex() < 0:
            QMessageBox.warning(self, tr('ui.workspace.finite_element'), tr('ui.fea.missing_iteration_model', iteration=iteration))
            return
        self._load_selected()

    def _load_selected(self, *_args) -> None:
        if self.is_running() or self.iterations.currentData() is None:
            return
        entry = self.cases.currentData()
        if entry is None:
            return
        try:
            self.session.select_result(entry)
        except Exception as exc:
            self.cases.blockSignals(True)
            self.cases.setCurrentIndex(self._result_index(self.session.selected_result))
            self.cases.blockSignals(False)
            QMessageBox.warning(self, tr('ui.fea.import_failed'), str(exc))
            self._update_buttons()
            return
        self.output.setPlainText(entry.log_path.read_text(encoding='utf-8') if entry.log_path else '')
        self._populate_loads()
        if entry.is_original:
            self._set_status('imported', iteration=entry.source.iteration)
        else:
            self._set_status('viewing_analysis', number=entry.number, iteration=entry.source.iteration)
        self._render()
        self._update_buttons()

    def _populate_loads(self) -> None:
        self._loading = True
        try:
            values = self.session.load_values()
            self.loads.setRowCount(len(values))
            for row, (name, kind, target, _enabled, numbers) in enumerate(values):
                for column, text in enumerate((name, kind, target)):
                    item = QTableWidgetItem(text)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.loads.setItem(row, column, item)
                self.loads.setItem(row, 3, QTableWidgetItem(', '.join(format(float(value), '.12g') for value in numbers.reshape(-1))))
        finally:
            self._loading = False

    def _load_edited(self, *_args) -> None:
        if self._loading:
            return
        self.session.result = None
        self._set_status('loads_modified')
        self._update_buttons()
        self._render()

    def start_analysis(self) -> None:
        if self.is_running() or not self._has_selected_model():
            return
        try:
            values = {}
            enabled = {name: state for name, _kind, _target, state, _numbers in self.session.load_values()}
            for row in range(self.loads.rowCount()):
                name = self.loads.item(row, 0).text()
                raw = self.loads.item(row, 3).text().strip()
                numbers = json.loads(raw) if raw.startswith('[') else [float(part) for part in re.split(r'[,，\s]+', raw) if part]
                values[name] = (enabled[name],
                    np.asarray(numbers, dtype=float).reshape(-1).tolist())
            self.session.apply_loads(values)
            request = self.session.solve_request()
        except Exception as exc:
            QMessageBox.warning(self, tr('ui.fea.invalid_loads'), str(exc))
            return
        self._start_worker('solve', request)

    def _start_worker(self, job: str, request: Path) -> None:
        self._job, self._cancelled = job, False
        self.output.clear()
        self._set_status('solving' if job == 'solve' else 'exporting')
        self._process.start(sys.executable, ['-u', '-m', 'morphopt.ui.fea_worker', str(request)])
        self._update_buttons()

    def _read_output(self) -> None:
        text = bytes(self._process.readAllStandardOutput()).decode('utf-8', errors='replace')
        cursor = self.output.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)
        self.output.setTextCursor(cursor)

    def _finished(self, code: int, *_args) -> None:
        self._read_output()
        try:
            if self._cancelled:
                self._set_status('stopped')
            elif code:
                self._set_status('failed')
            elif self._job == 'solve':
                entry = self.session.accept_solution(self.output.toPlainText())
                self._update_cases(selected=entry)
                self._populate_loads()
                self._set_status('solved')
                self._render()
            else:
                self._set_status('exported')
        except Exception as exc:
            self._set_status('failed')
            self.output.appendPlainText(str(exc))
        self._update_buttons()

    def _process_error(self, error) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._set_status('failed')
            self.output.appendPlainText(self._process.errorString())
            self._update_buttons()

    def _stop(self) -> None:
        self._cancelled = True
        self._process.kill()

    def _update_buttons(self) -> None:
        busy = self.is_running()
        has_model = self._has_selected_model()
        for widget in (self.import_observer, self.open_folder, self.iterations, self.cases, self.import_selected):
            widget.setEnabled(not busy)
        self.import_selected.setEnabled(not busy and self.iterations.currentIndex() >= 0)
        self.loads.setEnabled(not busy and has_model)
        self.solve.setEnabled(not busy and has_model)
        self.stop.setEnabled(busy)
        self.export_button.setEnabled(not busy and has_model and self.session.result is not None)
        self.export_location.setEnabled(not busy)
        self._update_export_fields()

    def _update_export_fields(self, *_args) -> None:
        location = ResultLocation(self.export_location.currentData())
        available = set(RESULT_FIELDS)
        has_result = self.session.controller is not None and self.session.result is not None
        if has_result:
            try:
                available = set(available_fields(self.session.controller, self.session.result, location))
            except Exception as exc:
                available = set()
                self.output.appendPlainText(str(exc))
        for key, check in self.field_checks.items():
            provider = RESULT_FIELDS[key]
            check.setVisible(provider.location is location and key in available)
            check.setEnabled(not self.is_running() and key in available)
        self.no_gauss.setVisible(location is ResultLocation.ELEMENTS and has_result
            and not any(key in available and field.gauss_kind for key, field in RESULT_FIELDS.items()))
        self.no_reference_points.setVisible(location is ResultLocation.REFERENCE_POINTS and has_result and not available)
        self.export_button.setEnabled(not self.is_running() and self._has_selected_model() and has_result
            and any(key in available and provider.location is location for key, provider in RESULT_FIELDS.items()))

    def _has_selected_model(self) -> bool:
        return (self.session.controller is not None
                and self.cases.currentData() == self.session.selected_result)

    def export_results(self) -> None:
        if self.is_running():
            return
        if not self._has_selected_model() or self.session.result is None:
            QMessageBox.information(self, tr('ui.fea.export'), tr('ui.fea.result_required'))
            return
        location = ResultLocation(self.export_location.currentData())
        fields = [key for key, check in self.field_checks.items()
                  if RESULT_FIELDS[key].location is location and check.isEnabled() and check.isChecked()]
        if not fields:
            QMessageBox.information(self, tr('ui.fea.export'), tr('ui.fea.choose_fields'))
            return
        name = f'fea_iter_{self.session.source.iteration}_{self.session.selected_result.key}_{location.value}'
        selection = choose_save_file(self, tr('ui.fea.export'), self.folder.text(), name,
            {key: tr(exporter.label_key) for key, exporter in EXPORTERS.items()})
        if selection is None:
            return
        try:
            request = self.session.export_request(str(selection.path), selection.format, fields,
                location=location.value, overwrite=selection.overwrite)
        except Exception as exc:
            QMessageBox.warning(self, tr('ui.fea.export'), str(exc))
            return
        self._start_worker('export', request)

    def _render(self, *_args) -> None:
        self._render_pending = True
        if not self.isVisible() or self.session.controller is None:
            return
        try:
            with _cpu_torch_defaults():
                controller, result = self.session.controller, self.session.result
                gc = result.GC if result is not None and self.deformed.isChecked() else None
                meshes = controller.assembly.get_meshes(GC=gc)
                coordinates = controller.GC2RGC(result.GC) if result is not None else None
                field = self.display_field.currentData()
                render_style = theme_manager.palette.viewer.render
                values_by_instance = {}
                if coordinates is not None:
                    for name, instance in controller.assembly._instances.items():
                        if instance.enabled is False:
                            continue
                        values = coordinates[instance._RGC_index].detach().cpu().numpy().reshape(-1, 3)
                        values_by_instance[name] = np.linalg.norm(values, axis=1) if field == 'U' else values[:, int(field[1]) - 1]
                scalar_range = None
                if values_by_instance:
                    lower = min(float(values.min()) for values in values_by_instance.values())
                    upper = max(float(values.max()) for values in values_by_instance.values())
                    scalar_range = (lower, upper if upper > lower else lower + render_style.minimum_scalar_span)
                def build(plotter):
                    scalar_bar_added = False
                    for index, (name, mesh) in enumerate(meshes.items()):
                        if not mesh.n_points or controller.assembly._instances[name].enabled is False:
                            continue
                        kwargs = {'color': theme_manager.palette.viewer.geometry.instance_colors[index % len(theme_manager.palette.viewer.geometry.instance_colors)],
                                  'smooth_shading': True, 'label': name,
                                  'ambient': render_style.mesh_ambient, 'diffuse': render_style.mesh_diffuse,
                                  'specular': render_style.mesh_specular, 'specular_power': render_style.mesh_specular_power}
                        if name in values_by_instance:
                            scalar = values_by_instance[name]
                            if len(scalar) == mesh.n_points:
                                mesh.point_data[field] = scalar
                                kwargs.pop('color')
                                kwargs.update(scalars=field, cmap=render_style.result_colormap, clim=scalar_range,
                                    show_scalar_bar=not scalar_bar_added,
                                    scalar_bar_args={'title': field, 'color': theme_manager.palette.text})
                                scalar_bar_added = True
                        plotter.add_mesh(mesh, **kwargs)
                self.viewport.rebuild(build)
            self._render_pending = False
        except Exception as exc:
            self.output.appendPlainText(tr('ui.fea.preview_failed', error=exc))

    def showEvent(self, event):
        super().showEvent(event)
        if self._render_pending:
            self._render()

    def _set_status(self, key: str, **values) -> None:
        self._status_key, self._status_values = key, values
        self.status.setText(tr('ui.fea.' + key, **values))

    def apply_language(self) -> None:
        for widget, key in self._texts:
            if isinstance(widget, QGroupBox):
                widget.setTitle(tr(key))
            else:
                widget.setText(tr(key))
        self.loads.setHorizontalHeaderLabels([tr('ui.fea.' + key) for key in ('name', 'type', 'target', 'values')])
        for index, location in enumerate(ResultLocation):
            self.export_location.setItemText(index, tr('ui.fea.location_' + location.value))
        self._update_export_fields()
        self._update_cases()
        if self._status_key:
            self._set_status(self._status_key, **self._status_values)

    def apply_theme(self) -> None:
        self.viewport.apply_theme()
        self._render()

    def close_cleanup(self) -> None:
        if self.is_running():
            self._process.kill()
            self._process.waitForFinished()
        self.session.close()
