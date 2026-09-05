"""Definition workbench (v2).

Layout:
  header      scheme + label
  center      two tabs only:
                1. 编辑   -> a QStackedWidget routed by the selected tree node
                              (property / solver / loads / steps / updater /
                               objective pages)
                2. 代码(只读) -> generated ``ThisController`` (auto-synced)
  right       PyVista preview of the initial geometry + per-step loads
  footer      ▶ 导入观察部分 (hand the definition to the observer page)

Interchange is the ``*.morph`` JSON (open/export); the runnable ``*.py`` is
generated from the model in the read-only code tab (no .py import).
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTabWidget, QLabel,
    QPlainTextEdit, QPushButton, QFileDialog, QStackedWidget, QLineEdit,
)
from PySide6.QtGui import QFont

from .model.problem import Node, ProblemDefinition
from .model.schemas import SCHEME_LABELS
from .widgets.model_tree import ModelTree
from .widgets.editor import PropertyEditor, fields_for_node
from .widgets.solver_editor import SolverEditor
from .widgets.stepmatrix import StepMatrix
from .widgets.updater_editor import UpdaterEditor
from .widgets.objective_editor import ObjectiveEditor
from .widgets.viewer import PreviewViewer
from .codegen.generator import generate_source


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
            ("change", "更换优化问题", "更换优化问题类型（形状 / 拓扑 / 协同）", self.changeProblemRequested.emit),
            ("open", "打开 .morph", "打开已有的 .morph 定义", self.openMorphRequested.emit),
            ("export", "导出 .morph", "把当前定义保存为 .morph", self.exportMorphRequested.emit),
            ("runpy", "导出运行 .py", "由当前定义生成可运行的无界面 .py", self.exportRunPyRequested.emit),
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
        head.addWidget(QLabel("优化名称"))
        self._name_edit = QLineEdit()
        self._name_edit.setFixedWidth(180)
        self._name_edit.setToolTip("优化问题名称（导出/运行的 opt_label）")
        self._name_edit.editingFinished.connect(self._apply_name)
        head.addWidget(self._name_edit)
        head.addSpacing(10)
        head.addWidget(QLabel("输出路径"))
        self._path_edit = QLineEdit()
        self._path_edit.setMinimumWidth(240)
        self._path_edit.setToolTip("结果输出目录（Controller.path_result_folder）")
        self._path_edit.editingFinished.connect(self._apply_path)
        head.addWidget(self._path_edit, 1)
        btn_dir = QPushButton("…")
        btn_dir.setFixedWidth(30)
        btn_dir.clicked.connect(self._browse_path)
        head.addWidget(btn_dir)
        head.addSpacing(10)
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
        self.prop_editor = PropertyEditor()
        self.solver_editor = SolverEditor()
        self.step_matrix = StepMatrix()
        self.updater_editor = UpdaterEditor()
        self.objective_editor = ObjectiveEditor()
        for w in (self.prop_editor, self.solver_editor, self.step_matrix,
                  self.updater_editor, self.objective_editor):
            self._stack.addWidget(w)
            w.changed.connect(self._schedule_rebuild)

        # loads hint: loads are added/edited in the left tree per type
        self._loads_hint = QLabel(
            "Loads：左树“Loads”下列出每个载荷（可展开查看参数）。\n"
            "• 右键 Loads → 添加载荷类型\n"
            "• 右键单个载荷：删除 / 上移 / 下移\n"
            "• 点选单个载荷，按该类型专属字段编辑参数与名称")
        self._loads_hint.setWordWrap(True)
        self._loads_hint.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._loads_hint.setContentsMargins(12, 12, 12, 12)
        self._stack.addWidget(self._loads_hint)

        # when a load name is edited in the property form, cascade the rename
        self._open_name: str | None = None
        self.prop_editor.changed.connect(self._maybe_cascade_rename)
        center.addTab(self._stack, "编辑")

        self.code_view = QPlainTextEdit()
        self.code_view.setReadOnly(True)
        self.code_view.setFont(QFont("DejaVu Sans Mono", 10))
        center.addTab(self.code_view, "代码 (只读)")
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
        b_import = QPushButton("▶ 导入观察部分")
        b_import.setToolTip("将当前定义提交至观察部分，以开始或继续优化")
        b_import.setStyleSheet(
            "background-color:#00695c; font-weight:600; padding:6px 18px;")
        b_import.clicked.connect(lambda: self.importToObserver.emit(self.problem))
        foot.addWidget(b_import)
        outer.addLayout(foot)

    # ------------------------------------------------------------- reload
    def reload(self) -> None:
        self._name_edit.setText(self.problem.label)
        self._path_edit.setText(self.problem.result_folder)
        self._update_caption()
        self.tree.set_problem(self.problem)
        self.objective_editor.set_problem(self.problem)
        self.refresh_code()
        self.viewer.set_problem(self.problem)
        self._select_editor(self._last_selected)

    def _update_caption(self) -> None:
        self.title.setText(
            f"[{SCHEME_LABELS.get(self.problem.scheme, self.problem.scheme)}]  "
            f"{self.problem.label}")

    # -------------------------------------------- name / output-path slots
    def _apply_name(self) -> None:
        v = self._name_edit.text().strip()
        if v and v != self.problem.label:
            self.problem.label = v
            self._update_caption()
            self.refresh_code()
            self.notify.emit(f"优化名称：{v}")
        else:
            self._name_edit.setText(self.problem.label)

    def _apply_path(self) -> None:
        v = self._path_edit.text().strip()
        if v != self.problem.result_folder:
            self.problem.result_folder = v
            self.refresh_code()

    def _browse_path(self) -> None:
        start = self._path_edit.text() or os.getcwd()
        folder = QFileDialog.getExistingDirectory(self, "选择输出路径", start)
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
        elif kind == "loads":
            self._stack.setCurrentWidget(self._loads_hint)
        elif kind == "steps":
            self.step_matrix.edit_node(node, self.problem)
            self._stack.setCurrentWidget(self.step_matrix)
        elif kind == "updater":
            self.updater_editor.edit_node(node, self.problem)
            self._stack.setCurrentWidget(self.updater_editor)
        elif kind == "objective":
            self.objective_editor.set_problem(self.problem)
            self._stack.setCurrentWidget(self.objective_editor)
        else:
            fields, code_slots, extra = fields_for_node(node, self.problem)
            subtitle = self._subtitle(node)
            self.prop_editor.edit_node(node, fields=fields, code_slots=code_slots,
                                       extra_choices=extra, subtitle=subtitle)
            self._stack.setCurrentWidget(self.prop_editor)

    def _maybe_cascade_rename(self, node: Node) -> None:
        """Keep step-matrix keys / jacobian_needed consistent on load rename."""
        if node.kind != "interface" or self._open_name is None:
            return
        old, new = self._open_name, node.name
        if old == new or not new:
            return
        loads = next((n for n in self.problem.root.children if n.kind == "loads"), None)
        if loads is not None and any(i is not node and i.name == new for i in loads.children):
            node.name = old  # reject duplicate names
            self._open_name = old
            self._schedule_rebuild()
            return
        steps = next((n for n in self.problem.root.iter_nodes() if n.kind == "steps"), None)
        if steps is not None:
            for row in steps.params.get("step_values", []):
                if old in row:
                    row[new] = row.pop(old)
        obj = self.problem.node("objective")
        if obj is not None:
            obj.params["jacobian_needed"] = [
                new if x == old else x for x in obj.params.get("jacobian_needed", [])]
        self._open_name = new

    @staticmethod
    def _subtitle(node: Node) -> str:
        if node.kind == "surface":
            return "表面 0 = 外表面；表面 ≥1 = 内腔(flip)。修改后自动更新预览。"
        if node.kind == "geometry":
            return "几何网格/壳层参数；下层表面列表可在左树右键增删排序。"
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
