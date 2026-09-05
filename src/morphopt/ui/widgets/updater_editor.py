"""Structured Updater editor: pick objective functions / constraints (no code).

Each sub-optimizer (UpdaterGeometries / UpdaterMaterials) exposes:
* max_step_iter, if_update
* a list of objective functions
* a list of constraints
and every item can have parameters edited in an inline form.  Items are stored
structurally in the model (``objective_functions`` / ``constraints``) and the
code generator turns them back into ``add_objective_function`` /
``add_constraints`` calls.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QGroupBox, QFormLayout, QSpinBox,
    QLineEdit, QPushButton, QHBoxLayout, QLabel, QComboBox,
)

from ..model.problem import Node
from ..model import schemas as S
from .param_form import ParamForm

CATEGORY_LABEL = {"objectives": "目标函数 (objective)", "constraints": "约束 (constraint)"}


class UpdaterEditor(QWidget):
    changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        hint = QLabel("为每个子优化器选择目标函数与约束（非代码方式）；参数改动立即生效并同步到生成代码。")
        hint.setStyleSheet("color:#7f8c8d;")
        outer.addWidget(hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self._layout = QVBoxLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        self._node: Node | None = None
        self._scheme = "shapeopt"

    # ------------------------------------------------------------------ api
    def edit_node(self, node: Node, problem) -> None:
        self._node = node
        self._scheme = problem.scheme if problem is not None else "shapeopt"
        # clear
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        geom = node.params.get("geometry")
        mats = node.params.get("materials")
        if geom:
            self._layout.addWidget(self._section_box("UpdaterGeometries", geom, "geometry"))
        if mats:
            self._layout.addWidget(self._section_box("UpdaterMaterials", mats, "materials"))
        if not geom and not mats:
            self._layout.addWidget(QLabel("(该方案没有可编辑的子优化器)"))

    # ------------------------------------------------------------- builders
    def _section_box(self, title: str, cfg: dict, group: str) -> QWidget:
        g = QGroupBox(title)
        form = QFormLayout(g)

        spin = QSpinBox()
        spin.setRange(1, 100000)
        spin.setValue(int(cfg.get("max_step_iter", 50)))
        spin.valueChanged.connect(lambda v: self._set(cfg, "max_step_iter", int(v)))
        form.addRow("max_step_iter", spin)

        ifup = QLineEdit()
        cur = cfg.get("if_update")
        ifup.setText("" if cur is None else str(cur))
        ifup.editingFinished.connect(
            lambda: self._set(cfg, "if_update", _parse_literal(ifup.text(), cur)))
        form.addRow("if_update", ifup)

        # objectives are scheme-default and read-only (no add/edit window)
        form.addRow(_objective_readonly(cfg, group, self._scheme))
        # constraints are user-selectable / parameter-editable
        form.addRow(_item_list(cfg, group, "constraints", self._scheme, self._on_change))
        return g

    # ------------------------------------------------------------- helpers
    def _set(self, cfg: dict, key: str, value) -> None:
        cfg[key] = value
        self._on_change()

    def _on_change(self, *_args) -> None:
        if self._node is not None:
            self.changed.emit(self._node)


def _objective_readonly(cfg: dict, group: str, scheme: str) -> QWidget:
    """Read-only summary of the scheme-default objective functions."""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    cap = QLabel("目标函数 (objective，方案默认)")
    cap.setStyleSheet("color:#9aa4b2;")
    lay.addWidget(cap)
    items = cfg.get("objective_functions") or []
    specs = {s.get("_type"): s for s in _specs_for(scheme, group, "objectives")}
    if not items:
        lay.addWidget(QLabel("—"))
        return w
    for it in items:
        itype = it.get("type", "?")
        spec = specs.get(itype) or {}
        line = QLabel(f"• {itype} — {spec.get('label', '')}")
        line.setStyleSheet("color:#c8d0da;")
        lay.addWidget(line)
    return w


def _item_list(cfg: dict, group: str, category: str, scheme: str, on_change) -> QWidget:
    """A compact list manager for one category of the section."""
    from PySide6.QtWidgets import QGridLayout

    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    cap = QLabel(CATEGORY_LABEL[category])
    cap.setStyleSheet("color:#9aa4b2;")
    lay.addWidget(cap)

    items = cfg.setdefault(category, [])
    specs = {s.get("_type"): s for s in _specs_for(scheme, group, category)}

    for it in items:
        itype = it.get("type", "")
        spec = specs.get(itype) or _find_spec(itype, category)
        label = spec["label"] if spec else itype
        grp = QGroupBox(label)
        col = QVBoxLayout(grp)
        top = QHBoxLayout()
        top.addWidget(QLabel(itype))
        top.addStretch(1)
        btn_del = QPushButton("删除")
        btn_del.setFixedWidth(52)
        btn_del.clicked.connect(lambda _=False, i=it: _remove(items, i, on_change))
        top.addWidget(btn_del)
        col.addLayout(top)
        if spec and spec.get("params"):
            pf = ParamForm(it.setdefault("params", {}), spec["params"])
            pf.changed.connect(lambda _k, i=it: on_change(i))
            col.addWidget(pf)
        lay.addWidget(grp)

    # add row
    addbar = QHBoxLayout()
    addbar.addWidget(QLabel("添加："))
    combo = QComboBox()
    for spec in specs.values():
        combo.addItem(spec["label"], spec.get("_type"))
    combo.setCurrentIndex(-1)
    addbar.addWidget(combo, 1)
    btn_add = QPushButton("＋")
    btn_add.setFixedWidth(34)
    btn_add.clicked.connect(lambda: _add(items, combo, scheme, group, category, on_change))
    addbar.addWidget(btn_add)
    lay.addLayout(addbar)
    return w


def _specs_for(scheme: str, group: str, category: str):
    out = []
    cat = S.UPDATER_CATALOG.get(category, {})
    for name, spec in cat.items():
        if spec["group"] == group and scheme in spec["schemes"]:
            s = dict(spec)
            s["_type"] = name
            out.append(s)
    return out


def _find_spec(itype: str, category: str):
    cat = S.UPDATER_CATALOG.get(category, {})
    spec = cat.get(itype)
    return dict(spec) if spec else None


def _add(items: list, combo: QComboBox, scheme: str, group: str, category: str, on_change) -> None:
    data = combo.currentData()
    if data is None:
        return
    params = S.updater_item_defaults(data, category)
    items.append({"type": data, "params": params})
    combo.setCurrentIndex(-1)
    on_change()


def _remove(items: list, item: dict, on_change) -> None:
    if item in items:
        items.remove(item)
        on_change()


def _parse_literal(text: str, default):
    import ast
    text = text.strip()
    if not text:
        return default
    try:
        return ast.literal_eval(text)
    except Exception:
        return text
