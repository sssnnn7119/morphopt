"""Editable Objective-Function panel.

Shown when the ``objective`` node is selected in the workbench.  The two
hand-written methods ``objective_function(self)`` / ``get_metrics(self)`` of the
generated ``ObjectiveFunction`` are edited here (body only, the ``def`` line is
added by the code generator).  ``jacobian_needed`` is the list of RP load names
whose Jacobians are requested.  The whole problem is (re)generated read-only in
the workbench's "代码 (只读)" tab; editing the canonical ``*.morph`` and re-
exporting the ``.py`` is the recommended workflow.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLabel, QComboBox, QPushButton,
    QHBoxLayout, QLineEdit,
)

from ..model.problem import Node, ProblemDefinition
from ..codegen.objective_templates import OBJECTIVE_TEMPLATES
from .codeeditor import CodeEditor


class ObjectiveEditor(QWidget):
    changed = Signal(object)   # objective Node

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        head = QLabel("目标函数（唯一可手写代码区，其余生成代码为只读）")
        head.setStyleSheet("font-weight:600; color:#e0e0e0;")
        lay.addWidget(head)

        form = QFormLayout()
        # template chooser
        tbar = QHBoxLayout()
        self.tpl_combo = QComboBox()
        self.btn_apply = QPushButton("插入模板")
        self.btn_apply.clicked.connect(self._apply_template)
        tbar.addWidget(self.tpl_combo, 1)
        tbar.addWidget(self.btn_apply)
        form.addRow("模板", self._wrap(tbar))

        self.jac = QLineEdit()
        self.jac.setPlaceholderText("例如 force_RP_head, moment_RP_head（逗号分隔）")
        self.jac.editingFinished.connect(self._save_jacobian)
        form.addRow("jacobian_needed", self.jac)

        lay.addLayout(form)

        self.obj_editor = CodeEditor("objective_function() 函数体（可编辑）")
        self.obj_editor.edit.textChanged.connect(self._save_objective)
        lay.addWidget(self.obj_editor, 1)

        self.met_editor = CodeEditor("get_metrics() 函数体（可编辑）")
        self.met_editor.edit.textChanged.connect(self._save_metrics)
        lay.addWidget(self.met_editor, 1)

        self._obj: Node | None = None
        self._problem: ProblemDefinition | None = None
        self._loading = False

    @staticmethod
    def _wrap(w: QWidget) -> QWidget:
        return w

    # ------------------------------------------------------------------ api
    def set_problem(self, problem: ProblemDefinition) -> None:
        self._problem = problem
        self._obj = problem.node("objective")
        self._loading = True
        try:
            # template list
            self.tpl_combo.clear()
            for t in OBJECTIVE_TEMPLATES.get(problem.scheme, []):
                self.tpl_combo.addItem(t["name"], t)
            self.tpl_combo.setCurrentIndex(-1)
            if self._obj is not None:
                self.jac.setText(", ".join(self._obj.params.get("jacobian_needed", []) or []))
                self.obj_editor.set_body(str(self._obj.params.get("_objective_function", "")))
                self.met_editor.set_body(str(self._obj.params.get("_get_metrics", "")))
            else:
                self.jac.clear()
                self.obj_editor.set_body("")
                self.met_editor.set_body("")
        finally:
            self._loading = False

    # ------------------------------------------------------------- handlers
    def _current(self) -> Node:
        if self._obj is None and self._problem is not None:
            self._obj = self._problem.node("objective")
        return self._obj

    def _save_jacobian(self) -> None:
        if self._loading:
            return
        nd = self._current()
        if nd is None:
            return
        names = [t.strip() for t in self.jac.text().split(",") if t.strip()]
        nd.params["jacobian_needed"] = names
        self.changed.emit(nd)

    def _save_objective(self) -> None:
        if self._loading:
            return
        nd = self._current()
        if nd is None:
            return
        nd.params["_objective_function"] = self.obj_editor.body()
        self.changed.emit(nd)

    def _save_metrics(self) -> None:
        if self._loading:
            return
        nd = self._current()
        if nd is None:
            return
        nd.params["_get_metrics"] = self.met_editor.body()
        self.changed.emit(nd)

    def _apply_template(self) -> None:
        idx = self.tpl_combo.currentIndex()
        if idx < 0:
            return
        t = self.tpl_combo.itemData(idx)
        if not t:
            return
        nd = self._current()
        if nd is None:
            return
        nd.params["_objective_function"] = t["objective"]
        nd.params["_get_metrics"] = t["metrics"]
        nd.params["jacobian_needed"] = list(t.get("jacobian_needed", []))
        # refresh UI
        self.set_problem(self._problem)
        self.changed.emit(nd)
