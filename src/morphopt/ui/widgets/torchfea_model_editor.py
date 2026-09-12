"""SIMP geometry editor backed by a directory watched for TorchFEA exports."""

from __future__ import annotations

from pathlib import Path
import shutil
import sys

from PySide6.QtCore import QFileSystemWatcher, QProcess, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...optcore.modelparams.geometry import inspect_model
from ..i18n import T
from ..model.problem import GeometryNode


class TorchFEAModelEditor(QWidget):
    """Choose/watch an export directory and link one native TorchFEA model."""

    changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._node: GeometryNode | None = None
        self._known_mtimes: dict[str, int] = {}
        self._updating = False

        outer = QVBoxLayout(self)
        title = QLabel(T(
            "SIMP 初始几何 · TorchFEA Assembly",
            "SIMP initial geometry · TorchFEA Assembly"))
        title.setStyleSheet("font-size:14px; font-weight:600;")
        outer.addWidget(title)

        note = QLabel(T(
            "CAD 建模、STEP 导入、剖分、部件（Part）、实例（Instance）和集合均在 "
            "torchfea-ui 中完成。\n"
            "这里只读取装配体（Assembly）的部件、实例、面集、节点集和单元集；载荷、边界条件、"
            "约束、参考点和求解器不会从 TorchFEA 模型导入。",
            "Create CAD, import STEP, mesh, and define Parts, Instances, and sets in "
            "torchfea-ui.\nOnly Assembly Parts/Instances and their surface/node/element "
            "sets are read here; loads, boundaries, constraints, reference points, and "
            "the solver are not imported."))
        note.setWordWrap(True)
        note.setStyleSheet("color:#9aa4b2;")
        outer.addWidget(note)

        directory_row = QHBoxLayout()
        directory_row.addWidget(QLabel(T("模型目录", "Model directory")))
        self.directory = QLineEdit()
        self.directory.setReadOnly(True)
        directory_row.addWidget(self.directory, 1)
        choose = QPushButton(T("选择目录…", "Choose directory…"))
        choose.clicked.connect(self._choose_directory)
        directory_row.addWidget(choose)
        outer.addLayout(directory_row)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel(T("当前模型", "Current model")))
        self.models = QComboBox()
        self.models.currentTextChanged.connect(self._select_model)
        model_row.addWidget(self.models, 1)
        refresh = QPushButton(T("重新扫描", "Rescan"))
        refresh.clicked.connect(lambda: self._scan_directory(auto_import_new=False))
        model_row.addWidget(refresh)
        outer.addLayout(model_row)

        launch = QPushButton(T(
            "打开 torchfea-ui 并监视此目录",
            "Open torchfea-ui and watch this directory"))
        launch.clicked.connect(self._launch_torchfea_ui)
        outer.addWidget(launch)

        self.summary = QTreeWidget()
        self.summary.setColumnCount(2)
        self.summary.setHeaderLabels([
            T("项目 / Item", "Item"), T("详情 / Details", "Details")
        ])
        self.summary.setRootIsDecorated(True)
        self.summary.setAlternatingRowColors(True)
        self.summary.setIndentation(18)
        self.summary.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.summary.header().setStretchLastSection(False)
        self.summary.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive)
        self.summary.header().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.summary.setColumnWidth(0, 240)
        self.summary.setStyleSheet(
            "QTreeWidget { background:#151a21; border:1px solid #30363d; "
            "padding:4px; }"
            "QTreeWidget::item { padding:3px 2px; }"
            "QTreeWidget::item:selected { background:#1f6aa5; }"
            "QHeaderView::section { background:#202938; color:#dbe4ee; "
            "padding:4px; border:0; }")
        outer.addWidget(self.summary)
        self._show_empty_summary(T(
            "尚未导入 TorchFEA 模型。", "No TorchFEA model imported."))
        outer.addStretch(1)

        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._directory_changed)
        self._scan_timer = QTimer(self)
        self._scan_timer.setSingleShot(True)
        self._scan_timer.setInterval(500)
        self._scan_timer.timeout.connect(
            lambda: self._scan_directory(auto_import_new=True))

    def edit_node(self, node: GeometryNode) -> None:
        self._node = node
        self._updating = True
        try:
            self.directory.setText(node.model_directory)
            self._watch_directory(node.model_directory)
            self._scan_directory(auto_import_new=False)
            if node.model_filename:
                self.models.setCurrentText(node.model_filename)
                self._show_summary(node.model_filename, show_error=False)
        finally:
            self._updating = False

    def validate_link(self, node: GeometryNode) -> bool:
        """Validate a persisted SIMP link without requiring page selection."""
        self._node = node
        if not node.model_directory or not node.model_filename:
            return False

        self.directory.setText(node.model_directory)
        try:
            inspect_model(node.model_directory, node.model_filename)
        except Exception:
            self._clear_invalid_model(
                T(
                    "已导入的 TorchFEA 模型不存在或无法读取，已清空模型选择。",
                    "The imported TorchFEA model is missing or unreadable; "
                    "the model selection was cleared.",
                ),
                clear_directory=not Path(node.model_directory).is_dir(),
            )
            return False
        return True

    def _choose_directory(self) -> bool:
        start = self.directory.text() or str(Path.cwd())
        directory = QFileDialog.getExistingDirectory(
            self, T("选择 TorchFEA 模型目录", "Select TorchFEA model directory"),
            start)
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
        watched = self._watcher.directories()
        if watched:
            self._watcher.removePaths(watched)
        if directory and Path(directory).is_dir():
            self._watcher.addPath(directory)
        self._known_mtimes = self._model_mtimes(directory)

    @staticmethod
    def _model_mtimes(directory: str) -> dict[str, int]:
        path = Path(directory)
        if not path.is_dir():
            return {}
        return {
            item.name: item.stat().st_mtime_ns
            for item in path.glob("*.npz") if item.is_file()
        }

    def _directory_changed(self, _directory: str) -> None:
        self._scan_timer.start()

    def _scan_directory(self, auto_import_new: bool) -> None:
        if self._node is None:
            return
        current = self._node.model_filename
        directory_exists = Path(self._node.model_directory).is_dir()
        mtimes = self._model_mtimes(self._node.model_directory)
        names = sorted(mtimes, key=lambda name: mtimes[name], reverse=True)
        new_or_changed = [
            name for name in names
            if mtimes[name] > self._known_mtimes.get(name, -1)
        ]
        self._known_mtimes = mtimes

        self._updating = True
        try:
            self.models.clear()
            self.models.addItems(names)
            target = new_or_changed[0] if auto_import_new and new_or_changed else current
            if not target and names:
                target = names[0]
            if target in names:
                self.models.setCurrentText(target)
        finally:
            self._updating = False

        # Do not use QComboBox.currentText() here: addItems() selects the
        # first entry automatically, which could silently replace a deleted
        # model with an unrelated .npz file.
        if target in names:
            self._apply_model(target, announce=auto_import_new and target in new_or_changed)
        elif current:
            self._clear_invalid_model(
                T(
                    "已导入的 TorchFEA 模型不存在，已清空模型选择。",
                    "The imported TorchFEA model is missing; the model selection was cleared.",
                ),
                clear_directory=not directory_exists,
            )
        else:
            self._node.model_filename = ""
            self.models.blockSignals(True)
            try:
                self.models.setCurrentIndex(-1)
            finally:
                self.models.blockSignals(False)
            self._show_empty_summary(T(
                "该目录中没有 .npz 模型。请在 torchfea-ui 中保存模型。",
                "No .npz model exists in this directory. Save one from torchfea-ui."))

    def _select_model(self, filename: str) -> None:
        if not self._updating and filename:
            self._apply_model(filename, announce=False)

    def _apply_model(self, filename: str, announce: bool) -> None:
        if self._node is None or not filename:
            return
        if not self._show_summary(filename, show_error=True):
            self._clear_invalid_model(
                T(
                    "TorchFEA 模型无效，已清空模型选择。",
                    "The TorchFEA model is invalid; the model selection was cleared.",
                ),
                clear_directory=not Path(self._node.model_directory).is_dir(),
                warn=False,
            )
            return
        changed = self._node.model_filename != filename
        self._node.model_filename = filename
        if changed:
            self.changed.emit(self._node)
        if announce:
            QMessageBox.information(
                self, T("已捕获模型", "Model captured"),
                T(f"已自动导入 TorchFEA 模型：{filename}",
                  f"Automatically imported TorchFEA model: {filename}"))

    def _clear_invalid_model(self, message: str, *,
                             clear_directory: bool = False,
                             warn: bool = True) -> None:
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
                T("TorchFEA 模型链接已清空", "TorchFEA model link cleared"),
                message,
            )

    def _show_summary(self, filename: str, show_error: bool) -> bool:
        if self._node is None:
            return False
        try:
            model = inspect_model(self._node.model_directory, filename)
        except Exception as exc:
            self._show_empty_summary(T(
                f"无法读取模型：{exc}", f"Cannot read model: {exc}"))
            if show_error:
                QMessageBox.warning(
                    self, T("模型导入失败", "Model import failed"), str(exc))
            return False

        self._populate_summary(model)
        return True

    def _show_empty_summary(self, message: str) -> None:
        """Show a compact status row while keeping the summary layout stable."""
        self.summary.clear()
        item = QTreeWidgetItem([T("模型信息", "Model information"), message])
        self.summary.addTopLevelItem(item)
        self.summary.expandAll()

    def _populate_summary(self, model) -> None:
        """Render the imported Assembly as a compact, navigable tree.

        The old summary joined every set into one long label.  A tree keeps the
        Assembly/Instance/Part hierarchy visible while allowing large set lists
        to remain collapsed until the user needs them.
        """
        self.summary.clear()
        root = QTreeWidgetItem([
            T("TorchFEA 模型", "TorchFEA model"),
            T("已导入", "Imported"),
        ])
        self.summary.addTopLevelItem(root)

        path_item = QTreeWidgetItem([T("路径", "Path"), model.path])
        path_item.setToolTip(1, model.path)
        root.addChild(path_item)

        assembly = QTreeWidgetItem([
            T("装配体（Assembly）", "Assembly"),
            T(f"{len(model.instances)} 个实例，{len(model.parts)} 个部件",
              f"{len(model.instances)} instances, {len(model.parts)} parts"),
        ])
        root.addChild(assembly)

        instances = QTreeWidgetItem([
            T("实例", "Instances"), str(len(model.instances)),
        ])
        assembly.addChild(instances)
        for instance in model.instances:
            instances.addChild(QTreeWidgetItem([
                instance.name,
                T(f"部件：{instance.part_name}", f"Part: {instance.part_name}"),
            ]))

        parts = QTreeWidgetItem([
            T("部件", "Parts"), str(len(model.parts)),
        ])
        assembly.addChild(parts)
        for part in model.parts:
            part_item = QTreeWidgetItem([part.name, ""])
            parts.addChild(part_item)
            self._add_set_group(
                part_item, T("面集", "Surface sets"),
                part.surface_sets)
            self._add_set_group(
                part_item, T("节点集", "Node sets"),
                part.node_sets)
            self._add_set_group(
                part_item, T("单元集", "Element sets"),
                part.element_sets)
            self._add_set_group(
                part_item, T("单元类型", "Element types"),
                part.element_types)

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

        QMessageBox.information(
            self, T("TorchFEA 建模范围", "TorchFEA modeling scope"),
            T(
                "在 torchfea-ui 中只需定义装配体（Assembly）这一层：完成部件（Part）、"
                "实例（Instance）、"
                "剖分以及面集/节点集/单元集后，使用“保存模型”把 .npz 保存到当前"
                "监视目录。MorphOpt 会自动捕获它；请不要在那里定义优化载荷或求解器。",
                "Only define the Assembly layer in torchfea-ui: create Parts and "
                "Instances, mesh them, and define surface/node/element sets. Then use "
                "Save Model to write the .npz into the watched directory. MorphOpt "
                "will capture it automatically; do not define optimization loads or "
                "the solver there."))

        executable = shutil.which("torchfea-ui")
        if executable:
            result = QProcess.startDetached(
                executable, [], self._node.model_directory)
        else:
            result = QProcess.startDetached(
                sys.executable, ["-m", "torchfea.ui"],
                self._node.model_directory)
        started = result[0] if isinstance(result, tuple) else bool(result)
        if not started:
            QMessageBox.warning(
                self, T("启动失败", "Launch failed"),
                T("无法启动 torchfea-ui，请确认它安装在当前 Python 环境中。",
                  "Could not launch torchfea-ui; ensure it is installed in the "
                  "current Python environment."))
