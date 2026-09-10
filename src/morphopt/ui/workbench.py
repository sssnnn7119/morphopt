"""Definition workbench (v2).

Layout:
  header      scheme + label
  center      two tabs only:
                1. 编辑   -> a QStackedWidget routed by the selected tree node
                              (property / solver / loads / steps / updater /
                               objective pages)
                2. 代码(只读) -> generated ``ThisController`` (auto-synced)
  right       PyVista preview of the initial geometry + per-step loads
  footer      ▶ 进入优化器 (hand the definition to the observer page)

Interchange is the ``*.morph`` JSON (open/export); the runnable ``*.py`` is
generated from the model in the read-only code tab (no .py import).
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTabWidget, QLabel,
    QPlainTextEdit, QPushButton, QFileDialog, QStackedWidget, QLineEdit,
    QComboBox,
)
from PySide6.QtGui import QFont

from .model.problem import Node, ProblemDefinition
from .model.schemas import MATERIAL_TYPES
from .schemes.base import scheme_label
from .widgets.model_tree import (
    ModelTree, surface_title_text, surface_index, container_title, _full_label,
)
from .widgets.editor import PropertyEditor, fields_for_node
from .widgets.solver_editor import SolverEditor, detect_devices
from .widgets.stepmatrix import StepMatrix
from .widgets.updater_editor import UpdaterEditor
from .widgets.objective_editor import ObjectiveEditor
from .widgets.viewer import PreviewViewer
from .codegen.generator import generate_source
from .i18n import T


class Workbench(QWidget):
    notify = Signal(str)
    #: emitted with the finished problem when the user wants the observer page
    importToObserver = Signal(object)
    #: definition-level file / problem actions (fulfilled by the MainWindow)
    changeProblemRequested = Signal()
    openMorphRequested = Signal()
    exportMorphRequested = Signal()
    exportRunPyRequested = Signal()

    def __init__(self, problem: ProblemDefinition, parent=None):
        super().__init__(parent)
        self.problem = problem
        self._last_selected: Node | None = None
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(250)
        self._rebuild_timer.timeout.connect(self._on_any_change)
        self._build_ui()
        self.reload()

    # ------------------------------------------------------------- layout
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # definition actions (definition-page content, not a global toolbar) --
        actbar = QHBoxLayout()
        self._act_buttons: dict[str, QPushButton] = {}
        actions = [
            ("change", T("更换优化问题", "Change Problem"),
             T("更换优化问题类型（形状 / 拓扑）",
               "Change the optimization problem type (shape / topology)"),
             self.changeProblemRequested.emit),
            ("open", T("打开 .morph", "Open .morph"),
             T("打开已有的 .morph 定义", "Open an existing .morph definition"),
             self.openMorphRequested.emit),
            ("export", T("导出 .morph", "Export .morph"),
             T("把当前定义保存为 .morph", "Save the current definition as .morph"),
             self.exportMorphRequested.emit),
            ("runpy", T("导出运行 .py", "Export Run .py"),
             T("由当前定义生成可运行的无界面 .py",
               "Generate a headless runnable .py from the current definition"),
             self.exportRunPyRequested.emit),
        ]
        for key, text, tooltip, slot in actions:
            b = QPushButton(text)
            b.setToolTip(tooltip)
            b.setStyleSheet("padding:4px 14px;")
            b.clicked.connect(slot)
            actbar.addWidget(b)
            self._act_buttons[key] = b
        actbar.addStretch(1)
        outer.addLayout(actbar)

        # header: optimization name + output path (editable) + scheme caption
        head = QHBoxLayout()
        self._lbl_name = QLabel(T("优化名称", "Optimization name"))
        head.addWidget(self._lbl_name)
        self._name_edit = QLineEdit()
        self._name_edit.setFixedWidth(180)
        self._name_edit.setToolTip(T(
            "优化问题名称（导出/运行的 opt_label）",
            "Problem name (opt_label used when exporting / running)"))
        self._name_edit.editingFinished.connect(self._apply_name)
        head.addWidget(self._name_edit)
        head.addSpacing(10)
        self._lbl_path = QLabel(T("输出路径", "Output folder"))
        head.addWidget(self._lbl_path)
        self._path_edit = QLineEdit()
        self._path_edit.setMinimumWidth(120)
        self._path_edit.setToolTip(T(
            "结果输出目录（Controller.path_result_folder）",
            "Result output directory (Controller.path_result_folder)"))
        self._path_edit.editingFinished.connect(self._apply_path)
        head.addWidget(self._path_edit, 1)
        btn_dir = QPushButton("…")
        btn_dir.setFixedWidth(30)
        btn_dir.clicked.connect(self._browse_path)
        head.addWidget(btn_dir)
        head.addSpacing(12)
        # global compute device (used by start_optimization and the Updater)
        self._lbl_device = QLabel(T("设备", "Device"))
        head.addWidget(self._lbl_device)
        self._device = QComboBox()
        self._device.setEditable(True)
        self._device.setFixedWidth(150)
        self._device.addItem("cpu")
        for dev in detect_devices():
            if dev != "cpu":
                self._device.addItem(dev)
        self._device.setToolTip(T(
            "全局计算设备（cpu / cuda:0…）；作用于 start_optimization 与 Updater",
            "Global compute device (cpu / cuda:0…); used by start_optimization "
            "and the Updater."))
        self._device.currentTextChanged.connect(self._save_device)
        head.addWidget(self._device)
        self._device_block = False
        head.addSpacing(8)
        self.title = QLabel("")
        self.title.setStyleSheet("color:#7f8c8d;")
        head.addWidget(self.title)
        outer.addLayout(head)

        split = QSplitter(Qt.Orientation.Horizontal)

        # ---- left tree
        self.tree = ModelTree()
        self.tree.nodeSelected.connect(self._on_node_selected)
        self.tree.treeChanged.connect(self._schedule_rebuild)
        split.addWidget(self.tree)

        # ---- center: 编辑 (stacked) + 代码(只读)
        center = QTabWidget()
        self._center = center

        self._stack = QStackedWidget()
        self._repopulate_stack()
        center.addTab(self._stack, T("编辑", "Edit"))

        self.code_view = QPlainTextEdit()
        self.code_view.setReadOnly(True)
        self.code_view.setFont(QFont("DejaVu Sans Mono", 10))
        center.addTab(self.code_view, T("代码 (只读)", "Code (read-only)"))
        center.setMinimumWidth(440)
        split.addWidget(center)

        # ---- right preview
        self.viewer = PreviewViewer()
        split.addWidget(self.viewer)

        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setStretchFactor(2, 1)
        split.setSizes([230, 560, 460])
        outer.addWidget(split, 1)

        # ---- footer: hand the finished definition over to the observer page
        foot = QHBoxLayout()
        self._msg = QLabel("")
        self._msg.setStyleSheet("color:#9aa4b2;")
        foot.addWidget(self._msg, 1)
        self._b_import = QPushButton(T("▶ 进入优化器", "▶ Send to Observer"))
        self._b_import.setToolTip(T(
            "将当前定义提交至优化器，以开始或继续优化",
            "Hand the current definition to the observer page to start or continue"))
        self._b_import.setStyleSheet(
            "background-color:#00695c; font-weight:600; padding:6px 18px;")
        self._b_import.clicked.connect(lambda: self.importToObserver.emit(self.problem))
        foot.addWidget(self._b_import)
        outer.addLayout(foot)

    # --------------------------------------------------------- center stack
    def _repopulate_stack(self) -> None:
        """(Re)build the editor pages of the center "编辑" tab.

        Recreates the (cheap, form-only) editors in place so all their
        localized texts are regenerated in the current language.  All data
        lives on the model nodes, so nothing is lost.  The PyVista preview
        viewport and the tree are *not* rebuilt here.
        """
        stack = self._stack
        while stack.count():
            w = stack.widget(0)
            stack.removeWidget(w)
            w.deleteLater()

        self.prop_editor = PropertyEditor()
        self.solver_editor = SolverEditor()
        self.step_matrix = StepMatrix()
        self.updater_editor = UpdaterEditor()
        self.objective_editor = ObjectiveEditor()
        self.optimizer_overview = self._make_optimizer_overview()
        for w in (self.prop_editor, self.solver_editor, self.step_matrix,
                  self.updater_editor, self.objective_editor,
                  self.optimizer_overview):
            stack.addWidget(w)
            changed = getattr(w, "changed", None)
            if changed is not None:
                changed.connect(self._schedule_rebuild)
            code_changed = getattr(w, "codeChanged", None)
            if code_changed is not None:
                code_changed.connect(self.refresh_code)

        # loads hint: loads are added/edited in the left tree per type
        self._loads_hint = self._make_loads_hint()
        stack.addWidget(self._loads_hint)

        # when a load name is edited in the property form, cascade the rename
        self._open_name: str | None = None
        self.prop_editor.changed.connect(self._maybe_cascade_rename)

    @staticmethod
    def _make_optimizer_overview() -> QLabel:
        """Concise landing page for the model-tree optimization definition."""
        overview = QLabel(T(
            "优化问题定义\n\n"
            "这里集中管理优化目标、几何优化器和材料优化器。\n"
            "各优化器下分别管理子优化目标、等式约束和罚函数约束。\n"
            "请在左侧展开并选择具体项目后编辑详细参数。",
            "Optimization definition\n\n"
            "This section contains the optimization objective, geometry "
            "optimizer, and material optimizer.\n"
            "Each optimizer contains its sub-objectives, equality constraints, "
            "and penalty constraints.\n"
            "Expand the section on the left and select a concrete item to edit "
            "its details."))
        overview.setWordWrap(True)
        overview.setAlignment(Qt.AlignmentFlag.AlignTop)
        overview.setContentsMargins(16, 16, 16, 16)
        return overview

    @staticmethod
    def _make_loads_hint() -> QLabel:
        hint = QLabel(T(
            "载荷：左树的“载荷”节点下分为“载荷定义”和“载荷工况”。\n"
            "• 右键“载荷定义” → 添加载荷类型\n"
            "• 右键单个载荷：删除 / 上移 / 下移\n"
            "• 点选单个载荷，按该类型专属字段编辑参数与名称",
            "Loads are grouped into Load definition and Load cases.\n"
            "• Right-click Load definition → add a load type\n"
            "• Right-click a load: delete / move up / move down\n"
            "• Select a load to edit its type-specific fields and its name"))
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignTop)
        hint.setContentsMargins(12, 12, 12, 12)
        return hint

    # ------------------------------------------------------------- reload
    def reload(self) -> None:
        self._name_edit.setText(self.problem.label)
        self._path_edit.setText(self.problem.result_folder)
        # show the current compute device without re-triggering a save
        self._device_block = True
        try:
            dev = self.problem.device or "cpu"
            if self._device.findText(dev) < 0:
                self._device.addItem(dev)
            self._device.setCurrentText(dev)
        finally:
            self._device_block = False
        self._update_caption()
        self.tree.set_problem(self.problem)
        self.objective_editor.set_problem(self.problem)
        self.refresh_code()
        self.viewer.set_problem(self.problem)
        self._select_editor(self._last_selected)

    def _update_caption(self) -> None:
        self.title.setText(
            f"[{scheme_label(self.problem.scheme)}]  "
            f"{self.problem.label}")

    # ------------------------------------------------------------ language
    def apply_language(self) -> None:
        """Re-apply the current language to the whole definition page in place.

        Unlike the old behaviour this does *not* destroy and recreate the whole
        workbench (which recreated the PyVista viewport and blackened the
        observer's GL pages).  The shell texts, the model-tree titles and the
        centre editors are all refreshed; the preview viewport keeps its state.
        """
        act_text = {
            "change": (T("更换优化问题", "Change Problem"),
                       T("更换优化问题类型（形状 / 拓扑）",
                         "Change the optimization problem type (shape / topology)")),
            "open": (T("打开 .morph", "Open .morph"),
                     T("打开已有的 .morph 定义", "Open an existing .morph definition")),
            "export": (T("导出 .morph", "Export .morph"),
                       T("把当前定义保存为 .morph",
                         "Save the current definition as .morph")),
            "runpy": (T("导出运行 .py", "Export Run .py"),
                      T("由当前定义生成可运行的无界面 .py",
                        "Generate a headless runnable .py from the current definition")),
        }
        for key, (text, tip) in act_text.items():
            b = self._act_buttons.get(key)
            if b is not None:
                b.setText(text)
                b.setToolTip(tip)
        self._lbl_name.setText(T("优化名称", "Optimization name"))
        self._lbl_path.setText(T("输出路径", "Output folder"))
        self._lbl_device.setText(T("设备", "Device"))
        self._name_edit.setToolTip(T(
            "优化问题名称（导出/运行的 opt_label）",
            "Problem name (opt_label used when exporting / running)"))
        self._path_edit.setToolTip(T(
            "结果输出目录（Controller.path_result_folder）",
            "Result output directory (Controller.path_result_folder)"))
        self._device.setToolTip(T(
            "全局计算设备（cpu / cuda:0…）；作用于 start_optimization 与 Updater",
            "Global compute device (cpu / cuda:0…); used by start_optimization "
            "and the Updater."))
        self._update_caption()
        self._center.setTabText(0, T("编辑", "Edit"))
        self._center.setTabText(1, T("代码 (只读)", "Code (read-only)"))
        self._b_import.setText(T("▶ 进入优化器", "▶ Send to Observer"))
        self._b_import.setToolTip(T(
            "将当前定义提交至优化器，以开始或继续优化",
            "Hand the current definition to the observer page to start or continue"))

        # Refresh the model-tree titles and the centre editors in the new
        # language.  Only the cheap form editors are re-created (data lives on
        # the model nodes); the PyVista preview viewport is left untouched.
        self.tree.apply_language()
        center_idx = self._center.currentIndex()
        self._repopulate_stack()
        self._select_editor(self._last_selected)
        self._center.setCurrentIndex(center_idx)

        self.viewer.apply_language()

    # -------------------------------------------- name / output-path slots
    def _apply_name(self) -> None:
        v = self._name_edit.text().strip()
        if v and v != self.problem.label:
            self.problem.label = v
            self._update_caption()
            self.refresh_code()
            self.notify.emit(T(f"优化名称：{v}", f"Optimization name: {v}"))
        else:
            self._name_edit.setText(self.problem.label)

    def _apply_path(self) -> None:
        v = self._path_edit.text().strip()
        if v != self.problem.result_folder:
            self.problem.result_folder = v
            self.refresh_code()

    def _save_device(self, text: str) -> None:
        """Persist the global compute device on the definition."""
        if getattr(self, "_device_block", False):
            return
        text = (text or "").strip()
        if not text:
            return
        if text != self.problem.device:
            self.problem.device = text
            self.refresh_code()
            self.notify.emit(T(f"设备：{text}", f"Device: {text}"))

    def _browse_path(self) -> None:
        start = self._path_edit.text() or os.getcwd()
        folder = QFileDialog.getExistingDirectory(
            self, T("选择输出路径", "Select output folder"), start)
        if folder:
            self._path_edit.setText(folder)
            self.problem.result_folder = folder
            self.refresh_code()

    def refresh_code(self) -> None:
        try:
            self.code_view.setPlainText(generate_source(self.problem))
        except Exception as exc:  # pragma: no cover
            self.code_view.setPlainText(f"# code generation failed:\n{exc}")

    # ------------------------------------------------------ node selection
    def _on_node_selected(self, node: Node) -> None:
        self._last_selected = node
        self._select_editor(node)

    def _select_editor(self, node: Node | None) -> None:
        if node is None:
            self._stack.setCurrentWidget(self.prop_editor)
            return
        kind = node.kind
        self._open_name = node.name if node.kind == "interface" else None
        if kind == "solver":
            self.solver_editor.edit_node(node, self.problem)
            self._stack.setCurrentWidget(self.solver_editor)
        elif kind in {"loads_group", "loads"}:
            self._stack.setCurrentWidget(self._loads_hint)
        elif kind == "steps":
            self.step_matrix.edit_node(node, self.problem)
            self._stack.setCurrentWidget(self.step_matrix)
        elif kind == "updater":
            self._stack.setCurrentWidget(self.optimizer_overview)
        elif kind.startswith("updater_"):
            # These transient leaf nodes point at the canonical updater
            # configuration and open the selected sub-optimizer in full.
            self.updater_editor.edit_node(
                node.updater_parent, self.problem, focus=node)
            self._stack.setCurrentWidget(self.updater_editor)
        elif kind == "objective":
            self.objective_editor.set_problem(self.problem)
            self._stack.setCurrentWidget(self.objective_editor)
        else:
            fields, code_slots, extra = fields_for_node(node, self.problem)
            subtitle = self._subtitle(node)
            title = None
            if node.kind == "surface":
                idx = surface_index(self.problem, node)
                if idx is not None:
                    title = surface_title_text(node, idx)
            elif node.kind == "material":
                mt = node.material_type
                spec = MATERIAL_TYPES.get(mt, {})
                title = _full_label(spec, mt)
            elif node.kind == "geometry":
                title = container_title("geometry")
            self.prop_editor.edit_node(node, fields=fields, code_slots=code_slots,
                                       extra_choices=extra, subtitle=subtitle,
                                       title=title,
                                       completion_problem=self.problem)
            self._stack.setCurrentWidget(self.prop_editor)

    def _maybe_cascade_rename(self, node: Node) -> None:
        """Delegate load rename invariants to the problem aggregate."""
        if node.kind != "interface" or self._open_name is None:
            return
        old, new = self._open_name, node.name
        if old == new or not new:
            return
        # PropertyEditor applies its local text field before emitting changed.
        # Restore the original name so ``rename_interface`` can atomically
        # validate uniqueness and update all cross-references.
        node.name = old
        if self.problem.rename_interface(node, new):
            self._open_name = new
        else:
            self._open_name = old
        self._schedule_rebuild()

    @staticmethod
    def _subtitle(node: Node) -> str:
        if node.kind == "surface":
            return T(
                "表面 0 = 外表面；表面 ≥1 = 内腔(flip)。修改后自动更新预览。",
                "Surface 0 = outer; surfaces ≥1 = cavities (flip). "
                "The preview updates automatically.")
        if node.kind == "geometry":
            return T(
                "这里定义优化的初始构型（几何模型与初始尺寸）；下层表面列表可在左树右键增删排序。",
                "Define the optimization's initial configuration here (geometry "
                "model and initial dimensions); manage surfaces below via the "
                "tree.")
        return ""

    # ------------------------------------------------------ change refresh
    def _schedule_rebuild(self, *_args) -> None:
        self._rebuild_timer.start()

    def _on_any_change(self) -> None:
        try:
            self.refresh_code()
        except Exception:
            pass
        self.viewer.set_problem(self.problem)
        self.objective_editor.set_problem(self.problem)
        # refresh tree summaries (e.g. load param rows) and the visible editor
        self.tree.rebuild(select=self._last_selected)
        if self._last_selected is not None:
            self._select_editor(self._last_selected)
        self.notify.emit(self.problem.label)

    def set_problem(self, problem: ProblemDefinition) -> None:
        self.problem = problem
        self.reload()

    # --------------------------------------------------------- footer slots
    def set_message(self, text: str) -> None:
        self._msg.setText(text)
