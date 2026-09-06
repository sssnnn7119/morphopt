"""Schema-driven property editor (center pane of the workbench).

``fields_for_node`` decides which parameter fields / code slots belong to each
tree-node kind (surface / interface / material / geometry / solver / ...);
``PropertyEditor`` renders those fields into editable widgets and keeps them in
sync with the node's ``params`` dict.  Hand-written python code slots
(``_apply_surface_constraints`` / ``_map_bsp_designfield``) are edited with the
:class:`~morphopt.ui.widgets.codeeditor.CodeEditor` widget.
"""

from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QComboBox, QCheckBox,
    QSpinBox, QPushButton, QHBoxLayout, QLabel, QFileDialog, QScrollArea,
    QPlainTextEdit,
)

from ..model.problem import Node
from ..model.schemas import (
    SURFACE_TYPES, INTERFACE_TYPES, MATERIAL_TYPES, SOLVER_FIELDS,
    GEOMETRY_SCHEMES,
)
from .codeeditor import CodeEditor
from .values import parse_vec_text, DOF_LABELS
from ..i18n import T, pick


def fields_for_node(node: Node, problem=None) -> tuple[list[dict], dict, dict]:
    """Return (param_fields, code_slots, extra_choices) for ``node``."""
    kind = node.kind
    scheme = problem.scheme if problem is not None else "shapeopt"
    if kind == "surface":
        st = node.params.get("type", "bsp_cylinder")
        spec = SURFACE_TYPES.get(st, {})
        return list(spec.get("params", [])), {}, {}
    if kind == "interface":
        it = node.params.get("type", "Pressure")
        spec = INTERFACE_TYPES.get(it, {})
        choices: dict[str, list[str]] = {}
        if problem is not None:
            # dynamic choices: surfaces sets + rp names
            choices = dynamic_choices(problem, it, node)
        return list(spec.get("params", [])), {}, choices
    if kind == "material":
        mt = node.params.get("type", "")
        spec = MATERIAL_TYPES.get(mt, {})
        code_slots = {}
        if mt in ("SIMP_BSPFieldMaterials", "CodesignMaterials"):
            code_slots["_map_bsp_designfield"] = "map_bsp_designfield(nodes)"
        return list(spec.get("params", [])), code_slots, {}
    if kind == "geometry":
        fields = list(GEOMETRY_SCHEMES.get(scheme, []))
        code_slots = {}
        if scheme in ("shapeopt", "codesign"):
            code_slots["_apply_surface_constraints"] = "apply_surface_constraints()"
        return fields, code_slots, {}
    if kind == "solver":
        return list(SOLVER_FIELDS), {}, {}
    if kind == "objective":
        return [], {}, {}
    if kind == "updater":
        return [], {}, {}
    return [], {}, {}


def dynamic_choices(problem, itype: str, iface: Node) -> dict[str, list[str]]:
    """Fill combo lists from the current problem tree."""
    surfaces = [s for s in problem.surfaces()]
    n = len(surfaces)
    surface_sets = [f"surface_{i}_All" for i in range(n)]
    if problem.scheme == "codesign":
        for i in range(1, n):
            surface_sets.append(f"surface_{i}_offset")
    surface_sets += ["surface_0_Bottom", "surface_0_Head"]

    rp_names = [nd.name for nd in problem.interfaces()
                if nd.params.get("type") == "ReferencePoint"]
    choices: dict[str, list[str]] = {}
    spec = INTERFACE_TYPES.get(itype, {})
    for f in spec.get("params", []):
        if f["key"] in ("surface_name", "set_nodes_name", "surface_name1", "surface_name2"):
            choices[f["key"]] = surface_sets
        elif f["key"] in ("rp_name", "rp_name1", "rp_name2"):
            choices[f["key"]] = rp_names
    return choices


class PropertyEditor(QWidget):
    """Renders the field list of one node into editable widgets."""

    changed = Signal(object)   # Node that changed

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._title = QLabel("—")
        self._title.setStyleSheet("font-size:14px; font-weight:600; color:#e0e0e0;")
        outer.addWidget(self._title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self._form = QFormLayout(body)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._form.setContentsMargins(8, 4, 8, 4)
        self._form.setVerticalSpacing(6)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self._node: Node | None = None
        self._controls: dict[str, QWidget] = {}
        self._code_controls: dict[str, CodeEditor] = {}
        self._dof_groups: dict[str, list[QCheckBox]] = {}

    # ------------------------------------------------------------- content
    def edit_node(self, node: Node, fields=None, code_slots=None,
                  extra_choices=None, subtitle: str = "",
                  title: str | None = None) -> None:
        # Re-selecting the SAME node object (e.g. auto-refresh after a field /
        # code-slot edit) must not tear down and rebuild the form: that would
        # drop focus and clear the undo history of the editor being typed in.
        if node is self._node and self._form.rowCount():
            # Keep the form; only refresh the header (a surface may have moved).
            self._title.setText(title if title is not None else (node.name or node.kind))
            return
        if fields is None:
            fields, code_slots, extra_choices = fields_for_node(node)
        code_slots = code_slots or {}
        extra_choices = extra_choices or {}

        self._node = node
        self._controls.clear()
        self._code_controls.clear()
        self._dof_groups.clear()
        # clear form (remove all rows)
        while self._form.rowCount():
            self._form.removeRow(0)

        self._title.setText(title if title is not None else (node.name or node.kind))
        if node.kind == "interface":
            name_edit = QLineEdit(node.name or "")
            name_edit.setToolTip(T(
                "载荷名称（在载荷步矩阵 / jacobian_needed 中引用）。改名会自动级联更新。",
                "Load name (referenced by the step matrix / jacobian_needed). "
                "Renaming cascades automatically."))
            name_edit.editingFinished.connect(lambda e=name_edit: self._rename_node(e.text()))
            self._form.addRow(T("名称", "Name"), name_edit)
        if subtitle:
            lbl = QLabel(subtitle)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color:#7f8c8d; font-size:11px;")
            self._form.addRow(lbl)

        for f in fields:
            self._add_field(f, extra_choices.get(f["key"]))
        for key, caption in code_slots.items():
            self._add_code_slot(key, caption)

    def _rename_node(self, text: str) -> None:
        if self._node is None:
            return
        text = text.strip()
        if not text or text == self._node.name:
            return
        self._node.name = text
        self._title.setText(text)
        self.changed.emit(self._node)

    def _add_field(self, f: dict, choices: list[str] | None) -> None:
        key = f["key"]
        node = self._node
        cur = node.params.get(key, f["default"])
        typ = f["type"]

        label = QLabel(pick(f["label"], f.get("label_en")))
        label.setToolTip(pick(f.get("doc", ""), f.get("doc_en")))

        if typ == "bool":
            w = QCheckBox()
            w.setChecked(bool(cur))
            w.toggled.connect(lambda v, k=key: self._set(k, bool(v)))
        elif typ == "int":
            w = QSpinBox()
            lo = f.get("min")
            hi = f.get("max")
            w.setRange(int(lo) if lo is not None else -10**6,
                       int(hi) if hi is not None else 10**6)
            w.setValue(int(cur) if cur is not None else 0)
            w.valueChanged.connect(lambda v, k=key: self._set(k, int(v)))
        elif typ == "combo":
            w = QComboBox()
            w.setEditable(True)
            items = list(f.get("choices") or []) + list(choices or [])
            for it in items:
                w.addItem(str(it))
            w.setCurrentText(str(cur) if cur is not None else "")
            w.editTextChanged.connect(lambda t, k=key: self._set(k, str(t)))
        elif typ == "file":
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit(str(cur or ""))
            btn = QPushButton("…")
            btn.setFixedWidth(28)
            btn.clicked.connect(lambda: self._browse(edit))
            lay.addWidget(edit, 1)
            lay.addWidget(btn)
            edit.editingFinished.connect(
                lambda k=key: self._set(k, edit.text()))
            self._controls[key] = edit
            self._form.addRow(label, w)
            return
        elif typ == "dofs":
            host = QWidget()
            h = QHBoxLayout(host)
            h.setContentsMargins(0, 0, 0, 0)
            n = int(f.get("size", 6))
            current = set(int(x) for x in (cur or []))
            boxes: list[QCheckBox] = []
            for i in range(n):
                cb = QCheckBox(DOF_LABELS.get(i, str(i)))
                cb.setChecked(i in current)
                cb.toggled.connect(lambda _=False, k=key: self._sync_dofs(k))
                h.addWidget(cb)
                boxes.append(cb)
            h.addStretch(1)
            self._dof_groups[key] = boxes
            self._form.addRow(label, host)
            return
        elif typ == "vecN" or typ.startswith("vec"):
            w = QLineEdit()
            w.setText(_vec_to_text(cur))
            keep_int = bool(f.get("ints", False))
            w.editingFinished.connect(
                lambda k=key: self._set(k, parse_vec_text(w.text(), ints=keep_int)))
        elif typ == "code" or typ == "text":
            w = QPlainTextEdit()
            w.setPlainText(str(cur or ""))
            w.setMinimumHeight(120)
            w.textChanged.connect(lambda k=key: self._set(k, w.toPlainText()))
            self._controls[key] = w
            self._form.addRow(label, w)
            return
        else:  # float / str
            w = QLineEdit()
            if typ == "float":
                w.setValidator(QDoubleValidator())
            w.setText(str(cur) if cur is not None else "")
            w.editingFinished.connect(lambda k=key: self._set(k, _parse_text_value(w.text(), typ)))

        self._controls[key] = w
        self._form.addRow(label, w)

    def _add_code_slot(self, key: str, caption: str) -> None:
        node = self._node
        editor = CodeEditor(caption)
        editor.set_body(str(node.params.get(key, "") or ""))
        editor.edit.textChanged.connect(lambda: self._sync_code(key, editor))
        self._code_controls[key] = editor
        self._form.addRow(editor)

    # -------------------------------------------------------------- helpers
    def _sync_dofs(self, key: str) -> None:
        boxes = self._dof_groups.get(key, [])
        vals = sorted(i for i, cb in enumerate(boxes) if cb.isChecked())
        self._set(key, vals)

    def _set(self, key: str, value) -> None:
        if self._node is None:
            return
        self._node.params[key] = value
        self.changed.emit(self._node)

    def _sync_code(self, key: str, editor: CodeEditor) -> None:
        if self._node is None:
            return
        self._node.params[key] = editor.body()
        self.changed.emit(self._node)

    def _browse(self, edit: QLineEdit) -> None:
        start = edit.text() or "."
        path, _ = QFileDialog.getOpenFileName(
            self, T("选择文件", "Select file"), start,
            "Mesh / geometry (*.inp *.stl *.step *.stp)")
        if path:
            edit.setText(path)
            if self._node is not None and edit in self._controls.values():
                key = next((k for k, w in self._controls.items() if w is edit), None)
                if key:
                    self._set(key, path)


# ---------------------------------------------------------------------------
def _vec_to_text(val) -> str:
    if isinstance(val, str):
        return val
    try:
        return ", ".join(str(v) for v in val)
    except TypeError:
        return str(val)


def _parse_text_value(text: str, typ: str):
    if typ == "float":
        try:
            return float(text)
        except ValueError:
            return text
    return text
