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
    QCheckBox, QPushButton, QHBoxLayout, QLabel, QComboBox,
    QToolButton, QMenu, QFrame, QWidgetAction, QTableWidget,
    QTableWidgetItem, QHeaderView,
)

from ..model.problem import Node, ProblemDefinition
from ..model import schemas as S
from .model_tree import surface_title_text
from .param_form import ParamForm
from .solver_editor import detect_devices
from ..i18n import T, pick


def _category_label(category: str) -> str:
    if category == "objectives":
        return T("目标函数", "Objective functions")
    return T("约束函数", "Constraints")


class UpdaterEditor(QWidget):
    changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # run-level compute device (used by the generated Updater)
        devrow = QHBoxLayout()
        devrow.addWidget(QLabel(T("Updater 设备", "Updater device")))
        self._device = QComboBox()
        self._device.setEditable(True)
        self._device.addItem("cpu")
        for dev in detect_devices():
            if dev != "cpu":
                self._device.addItem(dev)
        self._device.setToolTip(T(
            "Updater 专用计算设备（cpu / cuda:0…），与运行设备（start_optimization）独立；留空默认跟随运行设备。",
            "Device for the Updater only (cpu / cuda:0…); independent from the "
            "run device (start_optimization). Empty = follow the run device."))
        self._device.currentTextChanged.connect(self._save_device)
        devrow.addWidget(self._device, 1)
        outer.addLayout(devrow)

        hint = QLabel(T(
            "为每个子优化器选择目标函数与约束。",
            "Choose objective functions and constraints per sub-optimizer."))
        hint.setStyleSheet("color:#7f8c8d;")
        outer.addWidget(hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self._layout = QVBoxLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        self._node: Node | None = None
        self._problem: ProblemDefinition | None = None
        self._scheme = "shapeopt"
        self._loading = False

    # ------------------------------------------------------------------ api
    def edit_node(self, node: Node, problem) -> None:
        self._node = node
        self._problem = problem
        self._scheme = problem.scheme if problem is not None else "shapeopt"
        # show the current updater device without re-triggering a save
        self._loading = True
        try:
            dev = problem.updater_device or (problem.device if problem is not None else "cpu")
            if self._device.findText(dev) < 0:
                self._device.addItem(dev)
            self._device.setCurrentText(dev if dev else "cpu")
        finally:
            self._loading = False
        # clear
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        geom = node.geometry_config()
        mats = node.materials_config()
        if geom:
            self._layout.addWidget(self._section_box(
                T("几何更新器 (UpdaterGeometries)", "Geometry updater (UpdaterGeometries)"),
                geom, "geometry"))
        if mats:
            self._layout.addWidget(self._section_box(
                T("材料更新器 (UpdaterMaterials)", "Material updater (UpdaterMaterials)"),
                mats, "materials"))
        if not geom and not mats:
            self._layout.addWidget(QLabel(T(
                "(该方案没有可编辑的子优化器)",
                "(this scheme has no editable sub-optimizer)")))

    def _save_device(self, text: str) -> None:
        """Persist the (Updater-only) device on the definition."""
        if self._loading or self._problem is None:
            return
        text = (text or "").strip()
        if text:
            if text != self._problem.updater_device:
                self._problem.updater_device = text
        else:
            self._problem.updater_device = None  # empty -> follow run device
        if self._node is not None:
            self.changed.emit(self._node)

    # ------------------------------------------------------------- builders
    def _section_box(self, title: str, cfg: dict, group: str) -> QWidget:
        g = QGroupBox(title)
        form = QFormLayout(g)

        spin = QSpinBox()
        spin.setRange(1, 100000)
        spin.setValue(int(cfg.get("max_step_iter", 50)))
        spin.valueChanged.connect(lambda v: self._set(cfg, "max_step_iter", int(v)))
        form.addRow(T("最大迭代次数", "max_step_iter"), spin)

        cur = cfg.get("if_update")
        form.addRow(T("曲面更新与否", "if_update"),
                    self._if_update_control(cfg, cur, group))

        # objectives are scheme-default and read-only (no add/edit window)
        form.addRow(_objective_readonly(cfg, group, self._scheme))
        # constraints are user-selectable / parameter-editable
        n_surfaces = len(self._problem.surfaces()) if self._problem is not None else 0
        form.addRow(_item_list(cfg, group, "constraints", self._scheme,
                               self._on_change, n_surfaces))
        return g

    # -------------------------------------------------------- if_update ui
    def _if_update_control(self, cfg: dict, cur, group: str) -> QWidget:
        """Checkbox widget for ``if_update``.

        * geometry sub-optimizer: one checkbox per surface (index 0, 1, …);
          the stored value is a bool list aligned to the surface list.
        * other sub-optimizers (materials…): a single bool checkbox.
        """
        if group == "geometry":
            surfaces = self._problem.surfaces() if self._problem is not None else []
            if surfaces:
                return _IfUpdateDropDown(cfg, cur, surfaces, self._on_change)
        chk = QCheckBox()
        chk.setChecked(True if cur is None else bool(cur))
        chk.setToolTip(T(
            "勾选 = 该曲面参与更新。",
            "Checked = this surface participates in the update."))
        chk.toggled.connect(lambda v: self._set(cfg, "if_update", bool(v)))
        return chk

    # ------------------------------------------------------------- helpers
    def _set(self, cfg: dict, key: str, value) -> None:
        cfg[key] = value
        self._on_change()

    def _on_change(self, *_args) -> None:
        if self._node is not None:
            self.changed.emit(self._node)


class _IfUpdateDropDown(QToolButton):
    """Collapsible multi-select: one checkbox per surface, in a dropdown.

    The button shows ``<checked>/<total>``; opening the menu lets you toggle
    each surface (or use all / clear) while the popup stays open, so many
    surfaces stay compact in the form.
    """

    def __init__(self, cfg: dict, cur, surfaces: list, on_change, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._on_change = on_change
        self._checks: list[QCheckBox] = []

        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self)
        self.setMenu(menu)

        act = QWidgetAction(menu)
        panel = QWidget()
        panel.setMinimumWidth(250)
        col = QVBoxLayout(panel)
        col.setContentsMargins(8, 6, 8, 6)
        col.setSpacing(4)

        bar = QHBoxLayout()
        b_all = QPushButton(T("全选", "All"))
        b_none = QPushButton(T("清空", "None"))
        b_all.clicked.connect(lambda: self._set_all(True))
        b_none.clicked.connect(lambda: self._set_all(False))
        bar.addWidget(b_all)
        bar.addWidget(b_none)
        bar.addStretch(1)
        col.addLayout(bar)

        states = _as_bool_list(cur, len(surfaces))
        body = QWidget()
        vb = QVBoxLayout(body)
        vb.setContentsMargins(0, 0, 0, 0)
        vb.setSpacing(2)
        for i, srf in enumerate(surfaces):
            cb = QCheckBox(surface_title_text(srf, i))
            cb.setChecked(states[i])
            vb.addWidget(cb)
            self._checks.append(cb)
        vb.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedHeight(min(200, 18 + 26 * max(len(surfaces), 1)))
        scroll.setWidget(body)
        col.addWidget(scroll)

        act.setDefaultWidget(panel)
        menu.addAction(act)

        for cb in self._checks:
            cb.toggled.connect(self._commit)
        self._update_text()

    # ------------------------------------------------------------ helpers
    def _set_all(self, state: bool) -> None:
        for cb in self._checks:
            cb.blockSignals(True)
            cb.setChecked(state)
            cb.blockSignals(False)
        self._commit()

    def _commit(self, *_args) -> None:
        self._cfg["if_update"] = [c.isChecked() for c in self._checks]
        self._update_text()
        self._on_change()

    def _update_text(self) -> None:
        names = [c.text() for c in self._checks if c.isChecked()]
        self.setText(f"{len(names)}/{len(self._checks)}")
        self.setMinimumWidth(80)
        self.setToolTip(T(
            f"勾选参与更新的曲面：{', '.join(names) or '无'}",
            f"Surfaces to update: {', '.join(names) or 'none'}"))


class _DistanceMatrixDropDown(QToolButton):
    """Popup matrix editor for the Distance constraint's ``min_distance``.

    The button (``<N>×<N>``) opens a panel holding an editable N x N grid of
    inter-surface minimum distances (N = number of surfaces, rows/columns are
    the surface indices).  Editing a cell writes straight back into the
    Distance constraint's ``params['min_distance']`` so the generated code and
    the model stay in sync.
    """

    _DEFAULT = 2.5

    def __init__(self, params: dict, n: int, on_change, parent=None):
        super().__init__(parent)
        self._params = params
        self._n = max(1, int(n))
        self._on_change = on_change
        self._loading = False

        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setMinimumWidth(110)
        self.setToolTip(T(
            "编辑各表面之间的最小距离矩阵 min_distance[i][j]",
            "Edit the inter-surface minimum-distance matrix min_distance[i][j]"))
        self._update_text()

        menu = QMenu(self)
        self.setMenu(menu)
        act = QWidgetAction(menu)
        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(8, 8, 8, 8)
        col.setSpacing(6)

        cap = QLabel(T("表面间最小距离  min_distance[i][j]",
                       "Inter-surface minimum distance  min_distance[i][j]"))
        cap.setStyleSheet("color:#9aa4b2;")
        col.addWidget(cap)

        self._table = QTableWidget(self._n, self._n)
        self._table.setHorizontalHeaderLabels([str(j) for j in range(self._n)])
        self._table.setVerticalHeaderLabels([str(i) for i in range(self._n)])
        self._table.setMaximumHeight(min(440, 40 + 30 * self._n))
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._table.verticalHeader().setDefaultSectionSize(26)
        col.addWidget(self._table)

        bar = QHBoxLayout()
        bar.addStretch(1)
        b_reset = QPushButton(T("全部设为默认", "Reset to default"))
        b_reset.clicked.connect(self._reset_defaults)
        bar.addWidget(b_reset)
        col.addLayout(bar)

        act.setDefaultWidget(panel)
        menu.addAction(act)

        self._load_matrix()
        self._table.cellChanged.connect(self._on_cell)

    # ------------------------------------------------------------ helpers
    def _matrix(self) -> list[list[float]]:
        """Current N x N matrix (stored value padded / squared to N x N)."""
        default = self._DEFAULT
        n = self._n
        stored = self._params.get("min_distance")
        rows: list[list[float]] = []
        if isinstance(stored, (list, tuple)):
            for r in stored:
                if isinstance(r, (list, tuple)):
                    rows.append([float(x) for x in r])
                elif isinstance(r, (int, float)):
                    rows.append([float(r)])
        out = []
        for i in range(n):
            row = rows[i] if i < len(rows) else []
            row = [float(x) for x in row]
            out.append(row[:n] + [default] * (n - len(row)))
        return out

    def _load_matrix(self) -> None:
        mat = self._matrix()
        self._loading = True
        try:
            for i in range(self._n):
                for j in range(self._n):
                    self._table.setItem(i, j, QTableWidgetItem(f"{mat[i][j]:g}"))
        finally:
            self._loading = False
        self._params["min_distance"] = mat
        self._update_text()

    def _on_cell(self, r: int, c: int) -> None:
        if self._loading:
            return
        item = self._table.item(r, c)
        if item is None:
            return
        try:
            val = float(item.text())
        except ValueError:
            return
        mat = self._matrix()
        mat[r][c] = val
        self._params["min_distance"] = mat
        self._update_text()
        self._on_change()

    def _reset_defaults(self) -> None:
        default = self._DEFAULT
        mat = [[default] * self._n for _ in range(self._n)]
        self._params["min_distance"] = mat
        self._loading = True
        try:
            for i in range(self._n):
                for j in range(self._n):
                    item = self._table.item(i, j)
                    if item is not None:
                        item.setText(f"{default:g}")
        finally:
            self._loading = False
        self._update_text()
        self._on_change()

    def _update_text(self) -> None:
        self.setText(f"{self._n}×{self._n}")
        self.setFixedHeight(26)


def _distance_params_form(item: dict, n_surfaces: int, on_change) -> QWidget:
    """Form for a Distance constraint: a labelled matrix dropdown."""
    w = QWidget()
    form = QFormLayout(w)
    form.setContentsMargins(0, 0, 0, 0)
    params = item.setdefault("params", {})
    dd = _DistanceMatrixDropDown(params, n_surfaces, on_change)
    form.addRow(T("min_distance [[i][j]]", "min_distance [[i][j]]"), dd)
    return w


def _objective_readonly(cfg: dict, group: str, scheme: str) -> QWidget:
    """Read-only summary of the scheme-default objective functions."""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    cap = QLabel(T("子优化目标函数", "Objective functions per sub-optimizer"))
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
        line = QLabel(f"• {itype} — {pick(spec.get('label', ''), spec.get('label_en'))}")
        line.setStyleSheet("color:#c8d0da;")
        lay.addWidget(line)
    return w


def _item_list(cfg: dict, group: str, category: str, scheme: str, on_change,
               n_surfaces: int = 0) -> QWidget:
    """A compact list manager for one category of the section."""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    cap = QLabel(_category_label(category))
    cap.setStyleSheet("color:#9aa4b2;")
    lay.addWidget(cap)

    items = cfg.setdefault(category, [])
    specs = {s.get("_type"): s for s in _specs_for(scheme, group, category)}

    for it in items:
        itype = it.get("type", "")
        spec = specs.get(itype) or _find_spec(itype, category)
        label = pick(spec["label"], spec.get("label_en")) if spec else itype
        grp = QGroupBox(label)
        col = QVBoxLayout(grp)
        top = QHBoxLayout()
        top.addWidget(QLabel(itype))
        top.addStretch(1)
        btn_del = QPushButton(T("删除", "Delete"))
        btn_del.setFixedWidth(52)
        btn_del.clicked.connect(lambda _=False, i=it: _remove(items, i, on_change))
        top.addWidget(btn_del)
        col.addLayout(top)
        if spec and spec.get("params"):
            if itype == "Distance" and n_surfaces:
                # Distance carries an N x N min_distance matrix; edit it in a
                # dedicated popup grid instead of a raw text field.
                col.addWidget(_distance_params_form(it, n_surfaces, on_change))
            else:
                pf = ParamForm(it.setdefault("params", {}), spec["params"])
                pf.changed.connect(lambda _k, i=it: on_change(i))
                col.addWidget(pf)
        lay.addWidget(grp)

    # add row
    addbar = QHBoxLayout()
    addbar.addWidget(QLabel(T("添加：", "Add:")))
    combo = QComboBox()
    for spec in specs.values():
        combo.addItem(pick(spec["label"], spec.get("label_en")), spec.get("_type"))
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


def _as_bool_list(cur, n: int, default: bool = True) -> list[bool]:
    """Coerce an ``if_update`` value into a length-``n`` bool list.

    One entry per surface (index 0, 1, …).  ``None`` / scalars are expanded;
    a too-short list is padded with ``default``.
    """
    if isinstance(cur, (list, tuple)):
        return [bool(cur[i]) if i < len(cur) else default for i in range(n)]
    if cur is None:
        return [default] * n
    return [bool(cur)] * n
