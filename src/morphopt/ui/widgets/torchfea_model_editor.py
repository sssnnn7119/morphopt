"""SIMP geometry editor backed by a directory watched for TorchFEA exports."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from ..application.imported_models import ImportedModelLibrary
from ..model.problem import PartInterfaceNode, ProblemDefinition, resolve_model_directory


class TorchFEAModelEditor(QWidget):
    """Choose/watch an export directory and link one native TorchFEA model."""

    changed = Signal(object)

    def __init__(self, parent=None, embedded: bool = False):
        super().__init__(parent)
        self._embedded = embedded
        self._node: PartInterfaceNode | None = None
        self._problem: ProblemDefinition | None = None
        self.library = ImportedModelLibrary()
        self._updating = False

        outer = QVBoxLayout(self)
        if not embedded:
            title = QLabel(
                tr('ui.widgets.torchfea_model_editor.simp_initial_geometry_torchfea_assembly')
            )
            title.setStyleSheet("font-size:14px; font-weight:600;")
            outer.addWidget(title)

        note = QLabel(
            tr('ui.widgets.torchfea_model_editor.create_cad_import_step_mesh_and_define_parts_instances_and_sets_in_torch')
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#9aa4b2;")
        outer.addWidget(note)

        self.name = QLineEdit()
        if not embedded:
            name_row = QHBoxLayout()
            name_row.addWidget(QLabel(tr('ui.widgets.torchfea_model_editor.geometry_interface_name')))
            self.name.setToolTip(
                tr('ui.widgets.torchfea_model_editor.registration_name_in_geometryparams_geometry_updaters_are_retargeted_thi')
            )
            self.name.editingFinished.connect(self._rename_interface)
            name_row.addWidget(self.name, 1)
            outer.addLayout(name_row)

        directory_row = QHBoxLayout()
        directory_row.addWidget(QLabel(tr('ui.widgets.torchfea_model_editor.model_directory')))
        self.directory = QLineEdit()
        self.directory.setReadOnly(True)
        directory_row.addWidget(self.directory, 1)
        choose = QPushButton(tr('ui.widgets.torchfea_model_editor.choose_directory'))
        choose.clicked.connect(self._choose_directory)
        directory_row.addWidget(choose)
        outer.addLayout(directory_row)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel(tr('ui.widgets.torchfea_model_editor.current_model')))
        self.models = QComboBox()
        self.models.currentTextChanged.connect(self._select_model)
        model_row.addWidget(self.models, 1)
        refresh = QPushButton(tr('ui.widgets.torchfea_model_editor.rescan'))
        refresh.clicked.connect(lambda: self._scan_directory(auto_import_new=False))
        model_row.addWidget(refresh)
        outer.addLayout(model_row)

        launch = QPushButton(
            tr('ui.widgets.torchfea_model_editor.open_torchfea_ui_and_watch_this_directory')
        )
        launch.clicked.connect(self._launch_torchfea_ui)
        outer.addWidget(launch)

        self.summary = QTreeWidget()
        self.summary.setColumnCount(2)
        self.summary.setHeaderLabels(
            [tr('ui.widgets.torchfea_model_editor.item'), tr('ui.widgets.torchfea_model_editor.details')]
        )
        self.summary.setRootIsDecorated(True)
        self.summary.setAlternatingRowColors(True)
        self.summary.setIndentation(18)
        self.summary.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.summary.header().setStretchLastSection(False)
        self.summary.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive
        )
        self.summary.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.summary.setColumnWidth(0, 240)
        self.summary.setStyleSheet(
            "QTreeWidget { background:#151a21; border:1px solid #30363d; "
            "padding:4px; }"
            "QTreeWidget::item { padding:3px 2px; }"
            "QTreeWidget::item:selected { background:#1f6aa5; }"
            "QHeaderView::section { background:#202938; color:#dbe4ee; "
            "padding:4px; border:0; }"
        )
        outer.addWidget(self.summary)
        self._show_empty_summary(
            tr('ui.widgets.torchfea_model_editor.no_torchfea_model_imported')
        )
        if not embedded:
            outer.addStretch(1)

        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._directory_changed)
        self._scan_timer = QTimer(self)
        self._scan_timer.setSingleShot(True)
        self._scan_timer.setInterval(500)
        self._scan_timer.timeout.connect(
            lambda: self._scan_directory(auto_import_new=True)
        )

    def edit_node(self, node: PartInterfaceNode, problem: ProblemDefinition) -> None:
        self._node = node
        self._problem = problem
        self._updating = True
        try:
            self.name.setText(node.name)
            directory = resolve_model_directory(node.model_directory)
            self.directory.setText(directory)
            self._watch_directory(directory)
            self._scan_directory(auto_import_new=False)
            if node.model_filename:
                self.models.setCurrentText(node.model_filename)
                self._show_summary(node.model_filename, show_error=False)
        finally:
            self._updating = False

    def _rename_interface(self) -> None:
        """Apply the same aggregate-owned rename rule as every other interface."""
        if self._updating or self._node is None or self._problem is None:
            return
        name = self.name.text().strip()
        if name == self._node.name:
            return
        if not self._problem.rename_interface(self._node, name):
            self.name.setText(self._node.name)
            return
        self.changed.emit(self._node)

    def _choose_directory(self) -> bool:
        start = self.directory.text() or str(Path.cwd())
        directory = QFileDialog.getExistingDirectory(
            self, tr('ui.widgets.torchfea_model_editor.select_torchfea_model_directory'), start
        )
        if not directory:
            return False
        if self._node is None:
            return False
        directory = str(Path(directory).resolve())
        self._node.model_directory = directory
        self._node.model_filename = ""
        self.directory.setText(directory)
        self._watch_directory(directory)
        self._scan_directory(auto_import_new=False)
        self.changed.emit(self._node)
        return True

    def _watch_directory(self, directory: str) -> None:
        directory = resolve_model_directory(directory)
        watched = self._watcher.directories()
        if watched:
            self._watcher.removePaths(watched)
        if directory and Path(directory).is_dir():
            self._watcher.addPath(directory)
        self.library.watch(directory)

    def _directory_changed(self, _directory: str) -> None:
        self._scan_timer.start()

    def _scan_directory(self, auto_import_new: bool) -> None:
        if self._node is None:
            return
        current = self._node.model_filename
        directory = resolve_model_directory(self._node.model_directory)
        scan = self.library.scan(directory, current, auto_import=auto_import_new)
        names, new_or_changed = scan.names, scan.changed

        self._updating = True
        try:
            self.models.clear()
            self.models.addItems(names)
            target = scan.selected
            if target in names:
                self.models.setCurrentText(target)
        finally:
            self._updating = False

        # Do not use QComboBox.currentText() here: addItems() selects the
        # first entry automatically, which could silently replace a deleted
        # model with an unrelated .npz file.
        if target in names:
            self._apply_model(
                target, announce=auto_import_new and target in new_or_changed
            )
        elif current:
            self._clear_invalid_model(
                tr('ui.widgets.torchfea_model_editor.the_imported_torchfea_model_is_missing_the_model_selection_was_cleared'),
                clear_directory=not scan.directory_exists,
            )
        else:
            self._node.model_filename = ""
            self.models.blockSignals(True)
            try:
                self.models.setCurrentIndex(-1)
            finally:
                self.models.blockSignals(False)
            self._show_empty_summary(
                tr('ui.widgets.torchfea_model_editor.no_npz_model_exists_in_this_directory_save_one_from_torchfea_ui')
            )

    def _select_model(self, filename: str) -> None:
        if not self._updating and filename:
            self._apply_model(filename, announce=False)

    def _apply_model(self, filename: str, announce: bool) -> None:
        if self._node is None or not filename:
            return
        directory = resolve_model_directory(self._node.model_directory)
        if not self._show_summary(filename, show_error=True):
            self._clear_invalid_model(
                tr('ui.widgets.torchfea_model_editor.the_torchfea_model_is_invalid_the_model_selection_was_cleared'),
                clear_directory=not Path(directory).is_dir(),
                warn=False,
            )
            return
        changed = self._node.model_filename != filename
        self._node.model_filename = filename
        if changed:
            self.changed.emit(self._node)
        if announce:
            QMessageBox.information(
                self,
                tr('ui.widgets.torchfea_model_editor.model_captured'),
                tr('ui.widgets.torchfea_model_editor.automatically_imported_torchfea_model_value', value_0=filename),
            )

    def _clear_invalid_model(
        self, message: str, *, clear_directory: bool = False, warn: bool = True
    ) -> None:
        """Clear a stale/invalid TorchFEA link and optionally warn the user."""
        if self._node is None:
            return

        had_link = bool(self._node.model_directory or self._node.model_filename)
        self._node.model_filename = ""
        if clear_directory:
            self._node.model_directory = ""
            self.directory.clear()
            self._watch_directory("")
            self.models.clear()

        self.models.blockSignals(True)
        try:
            self.models.setCurrentIndex(-1)
        finally:
            self.models.blockSignals(False)
        self._show_empty_summary(message)

        if had_link:
            self.changed.emit(self._node)
        if warn:
            QMessageBox.warning(
                self,
                tr('ui.widgets.torchfea_model_editor.torchfea_model_link_cleared'),
                message,
            )

    def _show_summary(self, filename: str, show_error: bool) -> bool:
        if self._node is None:
            return False
        try:
            model = self.library.inspect(self._node.model_directory, filename)
        except Exception as exc:
            self._show_empty_summary(
                tr('ui.widgets.torchfea_model_editor.cannot_read_model_value', value_0=exc)
            )
            if show_error:
                QMessageBox.warning(
                    self, tr('ui.widgets.torchfea_model_editor.model_import_failed'), str(exc)
                )
            return False

        self._populate_summary(model)
        return True

    def _show_empty_summary(self, message: str) -> None:
        """Show a compact status row while keeping the summary layout stable."""
        self.summary.clear()
        item = QTreeWidgetItem([tr('ui.widgets.torchfea_model_editor.model_information'), message])
        self.summary.addTopLevelItem(item)
        self.summary.expandAll()

    def _populate_summary(self, model) -> None:
        """Render the imported Assembly as a compact, navigable tree.

        The old summary joined every set into one long label.  A tree keeps the
        Assembly/Instance/Part hierarchy visible while allowing large set lists
        to remain collapsed until the user needs them.
        """
        self.summary.clear()
        root = QTreeWidgetItem(
            [
                tr('ui.widgets.torchfea_model_editor.torchfea_model'),
                tr('ui.widgets.torchfea_model_editor.imported'),
            ]
        )
        self.summary.addTopLevelItem(root)

        path_item = QTreeWidgetItem([tr('ui.widgets.torchfea_model_editor.path'), model.path])
        path_item.setToolTip(1, model.path)
        root.addChild(path_item)

        assembly = QTreeWidgetItem(
            [
                tr('ui.widgets.torchfea_model_editor.assembly'),
                tr('ui.widgets.torchfea_model_editor.value_instances_value_parts', value_0=len(model.instances), value_1=len(model.parts)),
            ]
        )
        root.addChild(assembly)

        instances = QTreeWidgetItem(
            [
                tr('ui.widgets.torchfea_model_editor.instances'),
                str(len(model.instances)),
            ]
        )
        assembly.addChild(instances)
        for instance in model.instances:
            instances.addChild(
                QTreeWidgetItem(
                    [
                        instance.name,
                        tr('ui.widgets.torchfea_model_editor.part_value', value_0=instance.part_name),
                    ]
                )
            )

        parts = QTreeWidgetItem(
            [
                tr('ui.widgets.torchfea_model_editor.parts'),
                str(len(model.parts)),
            ]
        )
        assembly.addChild(parts)
        for part in model.parts:
            part_item = QTreeWidgetItem([part.name, ""])
            parts.addChild(part_item)
            self._add_set_group(part_item, tr('ui.widgets.torchfea_model_editor.surface_sets'), part.surface_sets)
            self._add_set_group(part_item, tr('ui.widgets.torchfea_model_editor.node_sets'), part.node_sets)
            self._add_set_group(
                part_item, tr('ui.widgets.torchfea_model_editor.element_sets'), part.element_sets
            )
            self._add_set_group(
                part_item, tr('ui.widgets.torchfea_model_editor.element_types'), part.element_types
            )

        root.setExpanded(True)
        assembly.setExpanded(True)
        instances.setExpanded(True)
        parts.setExpanded(True)

    @staticmethod
    def _add_set_group(parent: QTreeWidgetItem, title: str, names) -> None:
        values = list(names or ())
        group = QTreeWidgetItem([title, str(len(values))])
        parent.addChild(group)
        for value in values:
            group.addChild(QTreeWidgetItem([str(value), ""]))

    def _launch_torchfea_ui(self) -> None:
        if self._node is None:
            return
        if not self._node.model_directory and not self._choose_directory():
            return

        model_directory = resolve_model_directory(self._node.model_directory)

        QMessageBox.information(
            self,
            tr('ui.widgets.torchfea_model_editor.torchfea_modeling_scope'),
            tr('ui.widgets.torchfea_model_editor.only_define_the_assembly_layer_in_torchfea_ui_create_parts_and_instances'),
        )

        try:
            self.library.launch(model_directory)
        except OSError:
            QMessageBox.warning(
                self,
                tr('ui.widgets.torchfea_model_editor.launch_failed'),
                tr('ui.widgets.torchfea_model_editor.could_not_launch_torchfea_ui_ensure_it_is_installed_in_the_current_pytho'),
            )
