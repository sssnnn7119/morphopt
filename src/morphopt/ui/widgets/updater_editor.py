"""Structured Updater editor: pick objective functions / constraints.

Each sub-optimizer (UpdaterBoundaryPart / UpdaterSIMPMaterial) exposes:
* max_step_iter; material updaters also expose if_update
* a list of objective functions
* a list of geometry symmetry constraints and a list of penalty constraints
and every item can have parameters edited in an inline form. Built-in
symmetries are attached to their surfaces; custom code becomes the Part-level
``apply_surface_constraints`` hook.
"""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import QEvent, QObject, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from ...constants import CONSTANT
from ..application.devices import detect_devices
from ..application.editing import DefinitionCommands
from ..application.updaters import (
    UpdaterItems,
    distance_matrix,
    editor_signature,
    updater_sections,
)
from ..i18n import tr
from ..model.problem import ProblemDefinition, UpdaterNode
from ..presentation.labels import (
    node_title,
    node_type_title,
    surface_title_text,
    updater_item_title_text,
    updater_section_title_text,
)
from ..presentation.navigation import UpdaterItemTreeNode, UpdaterTreeNode
from ..refresh import RefreshContext
from ..theme import theme_manager
from .codeeditor import CodeEditor
from .collection_controls import CollectionHeader, ItemActions, set_card_selected
from .param_form import ParamForm


def _category_label(category: str) -> str:
    if category == "objectives":
        return tr("ui.widgets.updater_editor.objective_functions")
    if category == "geometry_symmetry":
        return tr("ui.widgets.updater_editor.geometry_symmetry_constraints")
    return tr("ui.widgets.updater_editor.penalty_constraints")


class UpdaterEditor(QWidget):
    changed = Signal(object)
    activated = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(*theme_manager.palette.layout.zero_margins)

        # run-level compute device (used by the generated Updater)
        devrow = QHBoxLayout()
        devrow.addWidget(QLabel(tr("ui.widgets.updater_editor.updater_device")))
        self._device = QComboBox()
        self._device.setEditable(True)
        self._device.addItem("cpu")
        for dev in detect_devices():
            if dev != "cpu":
                self._device.addItem(dev)
        self._device.setToolTip(
            tr(
                "ui.widgets.updater_editor.device_for_the_updater_only_cpu_cuda_0_independent_from_the_run_device_s"
            )
        )
        self._device.currentTextChanged.connect(self._save_device)
        devrow.addWidget(self._device, 1)
        outer.addLayout(devrow)

        hint = QLabel(
            tr(
                "ui.widgets.updater_editor.choose_objective_geometry_symmetry_and_penalty_constraints_per_sub_optim"
            )
        )
        hint.setProperty("textRole", "muted")
        outer.addWidget(hint)
        self._focus_label = QLabel("")
        self._focus_label.setProperty("textRole", "accent")
        outer.addWidget(self._focus_label)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        body = QWidget()
        self._layout = QVBoxLayout(body)
        self._layout.setContentsMargins(
            *deepcopy(theme_manager.palette.layout.widgets.collection_contents_margins)
        )
        self._layout.setSpacing(theme_manager.palette.layout.widgets.collection_spacing)
        self._scroll.setWidget(body)
        outer.addWidget(self._scroll, 1)
        self._node: UpdaterNode | None = None
        self._problem: ProblemDefinition | None = None
        self._focus: UpdaterTreeNode | None = None
        self._selected_item: UpdaterItemTreeNode | None = None
        self._item_lists: list[UpdaterItemList] = []
        self._loading = False
        self._structure = None

    # ------------------------------------------------------------------ api
    def edit_node(
        self,
        node: UpdaterNode,
        problem: ProblemDefinition,
        focus: UpdaterTreeNode | None = None,
        *,
        scroll_to_focus: bool = True,
    ) -> None:
        self._node = node
        self._problem = problem
        self._focus = focus
        if scroll_to_focus:
            self._selected_item = (
                focus if isinstance(focus, UpdaterItemTreeNode) else None
            )
        focus_group = focus.section_group if focus is not None else None
        focus_category = focus.group if focus is not None else None
        self._focus_label.setText(self._focus_text(focus))
        # show the current updater device without re-triggering a save
        self._loading = True
        try:
            dev = problem.updater_device or (
                problem.device if problem is not None else "cpu"
            )
            if self._device.findText(dev) < 0:
                self._device.addItem(dev)
            self._device.setCurrentText(dev if dev else "cpu")
        finally:
            self._loading = False
        sections = updater_sections(
            node, problem, focus_group, focus.config_index if focus else None
        )
        structure = editor_signature(problem, sections, focus_category)
        if structure == self._structure:
            self._focus_item(scroll=scroll_to_focus)
            return
        self._structure = structure
        self._item_lists.clear()
        while self._layout.count():
            widget = self._layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        for section in sections:
            title = updater_section_title_text(problem, section.group, section.config)
            self._layout.addWidget(
                self._section_box(title, section.config, section.group, focus_category)
            )
        if not sections:
            self._layout.addWidget(
                QLabel(
                    tr(
                        "ui.widgets.updater_editor.this_scheme_has_no_editable_sub_optimizer"
                    )
                )
            )
        self._layout.addStretch(1)
        self._focus_item(scroll=scroll_to_focus)

    def refresh_ui(self, context: RefreshContext) -> None:
        if context.problem.updater is not None:
            self.edit_node(
                context.problem.updater,
                context.problem,
                self._focus,
                scroll_to_focus=False,
            )

    def _item_list(
        self, config: dict, group: str, category: str, n_surfaces: int = 0
    ) -> UpdaterItemList:
        editor = UpdaterItemList(
            config,
            group,
            category,
            self._problem,
            self._on_change,
            self._on_code_change,
            n_surfaces,
        )
        editor.activated.connect(lambda item: self._on_item_activated(editor, item))
        self._item_lists.append(editor)
        return editor

    def _on_item_activated(self, editor: UpdaterItemList, item: dict | None) -> None:
        configs = (
            self._node.geometry
            if editor.model.group == "geometry"
            else self._node.materials
        )
        index = next(
            index
            for index, config in enumerate(configs)
            if config is editor.model.config
        )
        suffix = {
            "objectives": "objectives",
            "geometry_symmetry": "symmetry",
            "constraints": "penalty",
        }[editor.model.category]
        group = f"{editor.model.group}_{suffix}"
        selection = (
            UpdaterItemTreeNode(self._node, group, index, item)
            if item is not None
            else UpdaterTreeNode(self._node, group, index)
        )
        self._selected_item = (
            selection if isinstance(selection, UpdaterItemTreeNode) else None
        )
        if item is None and isinstance(self._focus, UpdaterItemTreeNode):
            self._focus = selection
        self._focus_item(scroll=False)
        self.activated.emit(selection)

    def _focus_item(self, *, scroll: bool) -> None:
        for editor in self._item_lists:
            for item_id, box in editor.item_boxes.items():
                selected = self._selected_item is not None and item_id == id(
                    self._selected_item.item
                )
                set_card_selected(box, selected)
        if scroll and self._selected_item is not None:
            QTimer.singleShot(0, self, self._scroll_to_selected_item)

    def _scroll_to_selected_item(self) -> None:
        if self._selected_item is not None:
            for editor in self._item_lists:
                box = editor.item_boxes.get(id(self._selected_item.item))
                if box is not None:
                    margins = deepcopy(
                        theme_manager.palette.layout.updater_editor.selection_scroll_margins
                    )
                    self._scroll.ensureWidgetVisible(box, margins[0], margins[1])
                    return

    def _focus_text(self, focus: UpdaterTreeNode | None) -> str:
        if focus is None:
            return ""
        return tr(
            "ui.widgets.updater_editor.selected_value",
            value_0=node_title(self._problem, focus),
        )

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
    def _section_box(
        self, title: str, cfg: dict, group: str, focus_category: str | None = None
    ) -> QWidget:
        g = QGroupBox(title)
        form = QFormLayout(g)

        show_controls = focus_category in {None, group}
        show_objectives = focus_category in {None, f"{group}_objectives"}
        show_symmetry = group == "geometry" and focus_category in {
            None,
            "geometry_symmetry",
        }
        show_penalties = focus_category in {None, f"{group}_penalty"}

        if show_controls:
            if group == "geometry":
                form.addRow(
                    tr("ui.widgets.updater_editor.target_part"),
                    self._part_target_control(cfg),
                )
            elif group == "materials":
                form.addRow(
                    tr("ui.widgets.updater_editor.target_material"),
                    self._material_target_control(cfg),
                )

            iterations = QLineEdit(
                str(
                    cfg.get(
                        "max_step_iter",
                        CONSTANT.UI.UPDATER_EDITOR.DEFAULT_MAX_STEP_ITERATIONS,
                    )
                )
            )

            def save_iterations() -> None:
                text = iterations.text().strip()
                if text:
                    try:
                        value = int(text)
                    except ValueError:
                        value = text
                    self._set(cfg, "max_step_iter", value)

            iterations.editingFinished.connect(save_iterations)
            form.addRow(tr("ui.widgets.updater_editor.max_step_iter"), iterations)

            if group == "materials":
                form.addRow(
                    tr("ui.widgets.updater_editor.if_update"),
                    self._material_update_control(cfg),
                )
        elif group == "geometry" and focus_category == "geometry_symmetry":
            form.addRow(
                tr("ui.widgets.updater_editor.target_part"),
                self._part_target_control(cfg),
            )

        if show_objectives:
            form.addRow(
                self._item_list(
                    cfg,
                    group,
                    "objectives",
                )
            )

        n_surfaces = self._surface_count(cfg, group)
        if show_symmetry:
            form.addRow(
                self._item_list(
                    cfg,
                    group,
                    "geometry_symmetry",
                )
            )
        if show_penalties:
            form.addRow(
                self._item_list(
                    cfg,
                    group,
                    "constraints",
                    n_surfaces,
                )
            )
        return g

    # -------------------------------------------------------- if_update ui
    def _part_target_control(self, cfg: dict) -> QWidget:
        """Combo box selecting the boundary Part this sub-optimizer updates.

        Every boundary part has its own geometry optimizer; changing this entry
        selects the Part registered for this optimizer.
        """
        combo = QComboBox()
        target = self._problem.config_part_node(cfg) if self._problem else None
        if self._problem is not None:
            available = DefinitionCommands(self._problem).available_optimizer_targets()
            for node in self._problem.boundary_part_nodes():
                if node is target or node in available:
                    combo.addItem(node_title(self._problem, node), node)
        index = combo.findData(target)
        combo.setCurrentIndex(index)
        combo.currentIndexChanged.connect(
            lambda _i: self._set_geometry_target(cfg, combo.currentData())
        )
        return combo

    def _material_target_control(self, cfg: dict) -> QWidget:
        """Combo box selecting the material definition this optimizer updates.

        Only design-carrying materials (SIMP density fields) can be updated.
        """
        combo = QComboBox()
        target = self._problem.config_material_node(cfg) if self._problem else None
        if self._problem is not None:
            available = DefinitionCommands(self._problem).available_optimizer_targets()
            for material in self._problem.material_nodes():
                if material.is_updatable and (
                    material is target or material in available
                ):
                    combo.addItem(node_title(self._problem, material), material)
        index = combo.findData(target)
        combo.setCurrentIndex(index)
        combo.currentIndexChanged.connect(
            lambda _i: self._set_material_target(cfg, combo.currentData())
        )
        return combo

    def _surface_count(self, cfg: dict, group: str) -> int:
        """Number of surfaces whose update flags this config controls.

        A geometry sub-optimizer only owns the surfaces of its own Part, so the
        checkbox list and the distance matrix are scoped to that Part.
        """
        if self._problem is None:
            return 0
        if group != "geometry":
            return len(self._problem.surfaces())
        node = self._problem.config_part_node(cfg)
        if node is None:
            return len(self._problem.surfaces())
        return len(node.surfaces)

    def _material_update_control(self, cfg: dict) -> QWidget:
        """Edit the material updater's update switch."""
        cur = cfg.get("if_update")
        chk = QCheckBox()
        chk.setChecked(True if cur is None else bool(cur))
        chk.setToolTip(
            tr(
                "ui.widgets.updater_editor.material_update_help"
            )
        )
        chk.toggled.connect(lambda v: self._set(cfg, "if_update", bool(v)))
        return chk

    # ------------------------------------------------------------- helpers
    def _set(self, cfg: dict, key: str, value) -> None:
        cfg[key] = value
        self._on_change()

    def _set_geometry_target(self, cfg: dict, target) -> None:
        if self._problem is not None and self._problem.set_geometry_updater_target(
            cfg, target
        ):
            self._on_change()

    def _set_material_target(self, cfg: dict, target) -> None:
        if self._problem is not None and self._problem.set_material_updater_target(
            cfg, target
        ):
            self._on_change()

    def _on_change(self, *_args) -> None:
        if self._node is not None:
            self.changed.emit(self._node)

    def _on_code_change(self) -> None:
        self._on_change()


class _DistanceMatrixDropDown(QToolButton):
    """Popup matrix editor for the Distance constraint's ``min_distance``.

    The button (``<N>×<N>``) opens a panel holding an editable N x N grid of
    inter-surface minimum distances (N = number of surfaces, rows/columns are
    the surface indices).  Editing a cell writes straight back into the
    Distance constraint's ``params['min_distance']`` so the generated code and
    the model stay in sync.
    """

    _DEFAULT = CONSTANT.UI.UPDATER_EDITOR.DEFAULT_INTER_SURFACE_DISTANCE

    def __init__(self, params: dict, n: int, on_change, parent=None, helper_names=()):
        super().__init__(parent)
        self._params = params
        self._n = max(1, int(n))
        self._on_change = on_change
        self._loading = False
        self._helper_names = set(helper_names)

        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setProperty("menuButton", True)
        self.setMinimumWidth(
            theme_manager.palette.layout.updater_editor.distance_matrix_button_minimum_width
        )
        self.setToolTip(
            tr(
                "ui.widgets.updater_editor.edit_the_inter_surface_minimum_distance_matrix_min_distance_i_j"
            )
        )
        self._update_text()

        menu = QMenu(self)
        self.setMenu(menu)
        act = QWidgetAction(menu)
        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(
            *deepcopy(
                theme_manager.palette.layout.updater_editor.distance_matrix_panel_margins
            )
        )
        col.setSpacing(
            theme_manager.palette.layout.updater_editor.distance_matrix_panel_spacing
        )

        cap = QLabel(
            tr(
                "ui.widgets.updater_editor.inter_surface_minimum_distance_min_distance_i_j"
            )
        )
        cap.setProperty("textRole", "muted")
        col.addWidget(cap)

        self._table = QTableWidget(self._n, self._n)
        self._table.setHorizontalHeaderLabels([str(j) for j in range(self._n)])
        self._table.setVerticalHeaderLabels([str(i) for i in range(self._n)])
        self._table.setMaximumHeight(
            min(
                theme_manager.palette.layout.updater_editor.distance_matrix_table_maximum_height,
                theme_manager.palette.layout.updater_editor.distance_matrix_table_base_height
                + theme_manager.palette.layout.updater_editor.distance_matrix_table_row_height
                * self._n,
            )
        )
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._table.verticalHeader().setDefaultSectionSize(
            theme_manager.palette.layout.updater_editor.distance_matrix_table_section_height
        )
        col.addWidget(self._table)

        bar = QHBoxLayout()
        bar.addStretch(1)
        b_reset = QPushButton(tr("ui.widgets.updater_editor.reset_to_default"))
        b_reset.clicked.connect(self._reset_defaults)
        bar.addWidget(b_reset)
        col.addLayout(bar)

        act.setDefaultWidget(panel)
        menu.addAction(act)

        self._load_matrix()
        self._table.cellChanged.connect(self._on_cell)

    # ------------------------------------------------------------ helpers
    def _matrix(self) -> list[list[float | str]]:
        """Current N x N matrix (stored value padded / squared to N x N)."""
        return distance_matrix(self._params.get("min_distance"), self._n, self._DEFAULT)

    def _load_matrix(self) -> None:
        mat = self._matrix()
        self._loading = True
        try:
            for i in range(self._n):
                for j in range(self._n):
                    value = mat[i][j]
                    self._table.setItem(
                        i,
                        j,
                        QTableWidgetItem(
                            value if isinstance(value, str) else f"{value:g}"
                        ),
                    )
        finally:
            self._loading = False
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
            val = item.text().strip()
            if val not in self._helper_names:
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
        self.setFixedHeight(
            theme_manager.palette.layout.updater_editor.item_button_height
        )


def _distance_params_form(
    item: dict, n_surfaces: int, on_change, problem=None
) -> QWidget:
    """Form for a Distance constraint: a labelled matrix dropdown."""
    w = QWidget()
    form = QFormLayout(w)
    form.setContentsMargins(*theme_manager.palette.layout.zero_margins)
    params = item["params"]
    helper_names = [node.name for node in problem.helper_variables] if problem else []
    dd = _DistanceMatrixDropDown(
        params, n_surfaces, on_change, helper_names=helper_names
    )
    form.addRow(
        tr("ui.widgets.updater_editor.minimum_distance_matrix_min_distance_i_j"),
        dd,
    )
    return w


class UpdaterItemList(QWidget):
    """One card manager for all three ordered updater item categories."""

    activated = Signal(object)

    def __init__(
        self,
        config,
        group,
        category,
        problem,
        on_change,
        on_code_change,
        n_surfaces=0,
        parent=None,
    ):
        super().__init__(parent)
        self.model = UpdaterItems(config, group, category, problem)
        self.on_change, self.on_code_change = on_change, on_code_change
        self.n_surfaces = n_surfaces
        self.item_boxes: dict[int, QGroupBox] = {}
        self._items_by_widget: dict[QObject, dict] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        layout.setSpacing(theme_manager.palette.layout.widgets.collection_spacing)
        self._add_menu = QMenu(self)
        specs = self.model.specs()
        for item_type, spec in specs.items():
            self._add_menu.addAction(
                node_type_title(spec, item_type),
                lambda _checked=False, kind=item_type: self._add(kind),
            )
        if category != "geometry_symmetry":
            custom_menu = self._add_menu.addMenu(
                tr("ui.widgets.model_tree.custom_class")
            )
            choices = self.model.custom_choices()
            for item_type, custom in choices:
                custom_menu.addAction(
                    updater_item_title_text(
                        {"type": item_type, "custom_class": custom.name},
                        specs.get(item_type),
                    ),
                    lambda _checked=False, kind=item_type, name=custom.name: self._add(
                        kind, name
                    ),
                )
            if not choices:
                custom_menu.addAction(
                    tr(
                        "ui.widgets.updater_editor.custom_class_create_a_compatible_class_first"
                    )
                ).setEnabled(False)
        header = CollectionHeader(_category_label(category), menu=self._add_menu)
        self.add_button = header.add_button
        layout.addWidget(header)
        for index, item in enumerate(self.model.items):
            spec = self.model.spec(item)
            title = updater_item_title_text(item, spec)
            box = QGroupBox(title)
            self.item_boxes[id(item)] = box
            column = QVBoxLayout(box)
            column.addWidget(
                ItemActions(
                    index,
                    len(self.model.items),
                    lambda entry=item: self._remove(entry),
                    lambda offset, entry=item: self._move(entry, offset),
                )
            )
            self._item_editor(column, item, spec)
            for widget in [box, *box.findChildren(QWidget)]:
                widget.installEventFilter(self)
                self._items_by_widget[widget] = item
            layout.addWidget(box)

    def _item_editor(self, column, item, spec):
        problem = self.model.problem
        if self.model.category == "geometry_symmetry":
            if item["type"] == "Custom":
                editor = CodeEditor(
                    tr("ui.widgets.updater_editor.apply_surface_constraints_body"),
                    completion_context="apply_surface_constraints",
                    completion_problem=problem,
                )
                editor.set_body(item["params"].get("code", ""))
                editor.edit.textChanged.connect(lambda: self._save_code(item, editor))
                column.addWidget(editor)
                return
            references = QFormLayout()
            compatible = self.model.compatible_surfaces(spec)
            for key, label in (
                ("surface_index", "surface"),
                ("related_surface_index", "related_surface"),
            ):
                if key == "related_surface_index" and not spec.related_surface:
                    continue
                combo = QComboBox()
                combo.addItem("", None)
                for index, surface in compatible:
                    combo.addItem(surface_title_text(surface, index), index)
                combo.setCurrentIndex(combo.findData(item.get(key)))
                if not compatible:
                    combo.addItem(
                        tr("ui.widgets.updater_editor.no_compatible_surface"), None
                    )
                    combo.setEnabled(False)
                combo.currentIndexChanged.connect(
                    lambda _index, combo=combo, key=key: self._save_reference(
                        item,
                        key,
                        combo.currentData(),
                    )
                )
                references.addRow(tr(f"ui.widgets.updater_editor.{label}"), combo)
            column.addLayout(references)
        if item["type"] == "Distance" and self.n_surfaces:
            column.addWidget(
                _distance_params_form(
                    item, self.n_surfaces, lambda: self._notify(item), problem
                )
            )
        elif spec is not None and spec.fields:
            choices = {}
            if item["type"] == "VolFrac":
                from ..application.part_sets import PartSetCatalog

                material = problem.config_material_node(self.model.config)
                choices["elementname"] = list(
                    PartSetCatalog(problem)
                    .for_part(
                        material.part if material is not None else None,
                    )
                    .elements
                )
            form = ParamForm(
                item["params"],
                spec.fields,
                extra_choices=choices,
                helper_names=[node.name for node in problem.helper_variables],
            )
            form.changed.connect(lambda _key: self._notify(item))
            column.addWidget(form)

    def _save_code(self, item, editor) -> None:
        item["params"]["code"] = editor.body()
        self.activated.emit(item)
        self.on_code_change()

    def _save_reference(self, item, key, value) -> None:
        if value != item.get(key):
            item[key] = value
            self._notify(item)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.FocusIn:
            self.activated.emit(self._items_by_widget[watched])
        return super().eventFilter(watched, event)

    def _notify(self, item: dict) -> None:
        self.activated.emit(item)
        self.on_change(item)

    def _add(self, item_type: str, custom_class: str = "") -> None:
        if self.model.add(item_type, custom_class):
            self._notify(self.model.items[-1])

    def _remove(self, item) -> None:
        self.model.remove(item)
        self.activated.emit(None)
        self.on_change()

    def _move(self, item, offset) -> None:
        if self.model.move(item, offset):
            self._notify(item)
