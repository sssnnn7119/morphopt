"""Definition workbench (v2).

Layout:
  header      Quickstart + name + output folder
  center      two tabs:
                1. 编辑   -> a QStackedWidget routed by the selected tree node
                              (properties / helper code / solver / loads /
                               steps / updater / objective pages)
                2. 代码(只读) -> generated ``ThisController`` (auto-synced)
  right       PyVista preview of the initial geometry + per-step loads
  footer      ▶ 进入优化器 (hand the definition to the observer page)

Interchange is the ``*.morph`` JSON (open/export); the runnable ``*.py`` is
generated from the model in the read-only code tab (no .py import).
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .application import (
    EditorKind,
    EditorRoute,
    MissingImportedModelError,
    ProblemSession,
    route_editor,
)
from .i18n import tr
from .model.problem import (
    Node,
    ProblemDefinition,
)
from .schemes.base import scheme_label
from .widgets.editor import PropertyEditor
from .widgets.editor_pages import EditorPages
from .application.fields import fields_for_node
from .application.part_sets import PartSetCatalog
from .widgets.definition_manager import DefinitionManagerEditor
from .widgets.model_tree import ModelTree
from .widgets.definition_actions import DefinitionActions
from .presentation.labels import container_title

from .widgets.objective_editor import ObjectiveEditor
from .widgets.custom_classes import CustomClassEditor, CustomClassTree, ModelClassSelector
from .widgets.codeeditor import HelperCodeEditor
from .widgets.solver_editor import SolverEditor
from .application.devices import detect_devices
from .widgets.stepmatrix import StepMatrix
from .application.imported_models import ImportedModelLibrary
from .widgets.updater_editor import UpdaterEditor
from .widgets.viewer import PreviewViewer


class Workbench(QWidget):
    notify = Signal(str)
    #: emitted with the finished problem when the user wants the observer page
    importToObserver = Signal(object)
    #: definition-level file / problem actions (fulfilled by the MainWindow)
    quickstartRequested = Signal()
    openMorphRequested = Signal()
    exportMorphRequested = Signal()
    exportRunPyRequested = Signal()

    def __init__(self, problem: ProblemDefinition, parent=None):
        super().__init__(parent)
        self.session = ProblemSession(problem)
        self.part_sets = PartSetCatalog(problem)
        self._last_selected: Node | None = None
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(250)
        self._rebuild_timer.timeout.connect(self._on_any_change)
        self._build_ui()
        self.reload()

    @property
    def problem(self) -> ProblemDefinition:
        """The canonical definition owned by this workbench's session."""
        return self.session.problem

    # ------------------------------------------------------------- layout
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # definition actions (definition-page content, not a global toolbar) --
        actbar = QHBoxLayout()
        self._act_buttons: dict[str, QPushButton] = {}
        actions = [
            (
                "quickstart",
                tr('ui.workbench.quickstart'),
                tr('ui.workbench.create_a_problem_from_a_starting_structure_and_design_goal'),
                self.quickstartRequested.emit,
            ),
            (
                "open",
                tr('ui.workbench.open_morph'),
                tr('ui.workbench.open_an_existing_morph_definition'),
                self.openMorphRequested.emit,
            ),
            (
                "export",
                tr('ui.workbench.export_morph'),
                tr('ui.workbench.save_the_current_definition_as_morph'),
                self.exportMorphRequested.emit,
            ),
            (
                "runpy",
                tr('ui.workbench.export_run_py'),
                tr('ui.workbench.generate_a_headless_runnable_py_from_the_current_definition'),
                self.exportRunPyRequested.emit,
            ),
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
        self._lbl_name = QLabel(tr('ui.workbench.optimization_name'))
        head.addWidget(self._lbl_name)
        self._name_edit = QLineEdit()
        self._name_edit.setFixedWidth(180)
        self._name_edit.setToolTip(
            tr('ui.workbench.problem_name_opt_label_used_when_exporting_running')
        )
        self._name_edit.editingFinished.connect(self._apply_name)
        head.addWidget(self._name_edit)
        head.addSpacing(10)
        self._lbl_path = QLabel(tr('ui.workbench.output_folder'))
        head.addWidget(self._lbl_path)
        self._path_edit = QLineEdit()
        self._path_edit.setMinimumWidth(120)
        self._path_edit.setToolTip(
            tr('ui.workbench.result_output_directory_controller_path_result_folder')
        )
        self._path_edit.editingFinished.connect(self._apply_path)
        head.addWidget(self._path_edit, 1)
        btn_dir = QPushButton("…")
        btn_dir.setFixedWidth(30)
        btn_dir.clicked.connect(self._browse_path)
        head.addWidget(btn_dir)
        head.addSpacing(12)
        # global compute device (used by start_optimization and the Updater)
        self._lbl_device = QLabel(tr('ui.workbench.device'))
        head.addWidget(self._lbl_device)
        self._device = QComboBox()
        self._device.setEditable(True)
        self._device.setFixedWidth(150)
        self._device.addItem("cpu")
        for dev in detect_devices():
            if dev != "cpu":
                self._device.addItem(dev)
        self._device.setToolTip(
            tr('ui.workbench.global_compute_device_cpu_cuda_0_used_by_start_optimization_and_the_upda')
        )
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
        self.actions = DefinitionActions(self)
        self.tree = ModelTree(actions=self.actions)
        self.tree.nodeSelected.connect(self._on_node_selected)
        self.tree.itemClicked.connect(self._on_model_item_clicked)
        self.tree.treeChanged.connect(self._schedule_rebuild)
        self.custom_tree = CustomClassTree()
        self.custom_tree.nodeSelected.connect(self._on_node_selected)
        self.custom_tree.treeChanged.connect(self._schedule_rebuild)
        self.custom_tree.overrideRequested.connect(self._override_method)
        self._tree_split = QSplitter(Qt.Orientation.Vertical)
        self._tree_split.addWidget(self.tree)
        self._tree_split.addWidget(self.custom_tree)
        self._tree_split.setSizes([500, 220])
        self._tree_split.setChildrenCollapsible(False)
        split.addWidget(self._tree_split)

        # ---- center: 编辑 (stacked) + 代码(只读)
        center = QTabWidget()
        self._center = center

        self._stack = QStackedWidget()
        self._repopulate_stack()
        edit_page = QWidget()
        edit_layout = QVBoxLayout(edit_page)
        edit_layout.setContentsMargins(0, 0, 0, 0)
        self.class_selector = ModelClassSelector()
        self.class_selector.changed.connect(self._schedule_rebuild)
        edit_layout.addWidget(self.class_selector)
        edit_layout.addWidget(self._stack, 1)
        center.addTab(edit_page, tr('ui.workbench.edit'))

        self.code_view = QPlainTextEdit()
        self.code_view.setReadOnly(True)
        self.code_view.setFont(QFont("DejaVu Sans Mono", 10))
        center.addTab(self.code_view, tr('ui.workbench.code_read_only'))
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
        self._b_import = QPushButton(tr('ui.workbench.send_to_observer'))
        self._b_import.setToolTip(
            tr('ui.workbench.hand_the_current_definition_to_the_observer_page_to_start_or_continue')
        )
        self._b_import.setStyleSheet(
            "background-color:#00695c; font-weight:600; padding:6px 18px;"
        )
        self._b_import.clicked.connect(self._submit_to_observer)
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
        self.geometry_editor = DefinitionManagerEditor("geometry", self.actions, sets=self.part_sets)
        self.loads_editor = DefinitionManagerEditor("loads", self.actions, sets=self.part_sets)
        self.materials_editor = DefinitionManagerEditor("materials", self.actions, sets=self.part_sets)
        self.objective_editor = ObjectiveEditor()
        self.custom_class_editor = CustomClassEditor()
        self.optimizer_overview = self._make_optimizer_overview()
        self.helper_page = HelperCodeEditor(self.actions)
        self.helper_page.edit_node(None, self.problem)
        self.updater_editor.codeChanged.connect(self.refresh_code)
        self.geometry_editor.changed.connect(self._sync_single_imported_part)
        self.custom_class_editor.nodeSelected.connect(self._on_node_selected)
        self._register_editor_pages()

    def _make_optimizer_overview(self) -> QWidget:
        """Landing page with the two supported optimizer-add actions."""
        overview = QWidget()
        layout = QVBoxLayout(overview)
        description = QLabel(
            tr('ui.workbench.optimization_definition_this_section_contains_the_optimization_objective')
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignTop)
        description.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(description)
        buttons = QHBoxLayout()
        add_geometry = QPushButton(tr('ui.workbench.geometry_optimizer'))
        add_geometry.clicked.connect(
            lambda _checked=False: self.actions.add_geometry_updater()
        )
        buttons.addWidget(add_geometry)
        add_materials = QPushButton(tr('ui.workbench.material_optimizer'))
        add_materials.clicked.connect(
            lambda _checked=False: self.actions.add_materials_updater()
        )
        buttons.addWidget(add_materials)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addStretch(1)
        return overview

    # ------------------------------------------------------------- reload
    def reload(self) -> None:
        self.session.synchronize()
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
        imported = self.problem.imported_model_part_node()
        self.tree.set_problem(self.problem)
        self.custom_tree.set_problem(self.problem)
        self.objective_editor.set_problem(self.problem)
        self._select_editor(self._last_selected)
        if imported is not None:
            issue = ImportedModelLibrary.validate_link(imported)
            if issue is not None:
                QMessageBox.warning(
                    self,
                    tr('ui.widgets.torchfea_model_editor.torchfea_model_link_cleared'),
                    issue,
                )
        self.refresh_code()
        try:
            self.viewer.set_problem(self.problem)
        except (TypeError, ValueError) as exc:
            self.notify.emit(tr('ui.workbench.preview_unavailable_value', value_0=exc))

    def _update_caption(self) -> None:
        self.title.setText(
            f"[{scheme_label(self.problem.scheme)}]  {self.problem.label}"
        )

    # ------------------------------------------------------------ language
    def apply_language(self) -> None:
        """Re-apply the current language to the whole definition page in place.

        Unlike the old behaviour this does *not* destroy and recreate the whole
        workbench (which recreated the PyVista viewport and blackened the
        observer's GL pages).  The shell texts, the model-tree titles and the
        centre editors are all refreshed; the preview viewport keeps its state.
        """
        act_text = {
            "quickstart": (
                tr('ui.workbench.quickstart'),
                tr('ui.workbench.create_a_problem_from_a_starting_structure_and_design_goal'),
            ),
            "open": (
                tr('ui.workbench.open_morph'),
                tr('ui.workbench.open_an_existing_morph_definition'),
            ),
            "export": (
                tr('ui.workbench.export_morph'),
                tr('ui.workbench.save_the_current_definition_as_morph'),
            ),
            "runpy": (
                tr('ui.workbench.export_run_py'),
                tr('ui.workbench.generate_a_headless_runnable_py_from_the_current_definition'),
            ),
        }
        for key, (text, tip) in act_text.items():
            b = self._act_buttons.get(key)
            if b is not None:
                b.setText(text)
                b.setToolTip(tip)
        self._lbl_name.setText(tr('ui.workbench.optimization_name'))
        self._lbl_path.setText(tr('ui.workbench.output_folder'))
        self._lbl_device.setText(tr('ui.workbench.device'))
        self._name_edit.setToolTip(
            tr('ui.workbench.problem_name_opt_label_used_when_exporting_running')
        )
        self._path_edit.setToolTip(
            tr('ui.workbench.result_output_directory_controller_path_result_folder')
        )
        self._device.setToolTip(
            tr('ui.workbench.global_compute_device_cpu_cuda_0_used_by_start_optimization_and_the_upda')
        )
        self._update_caption()
        self._center.setTabText(0, tr('ui.workbench.edit'))
        self._center.setTabText(1, tr('ui.workbench.code_read_only'))
        self._b_import.setText(tr('ui.workbench.send_to_observer'))
        self._b_import.setToolTip(
            tr('ui.workbench.hand_the_current_definition_to_the_observer_page_to_start_or_continue')
        )

        # Refresh the model-tree titles and the centre editors in the new
        # language.  Only the cheap form editors are re-created (data lives on
        # the model nodes); the PyVista preview viewport is left untouched.
        self.tree.apply_language()
        self.custom_tree.apply_language()
        self.class_selector.apply_language()
        center_idx = self._center.currentIndex()
        self._repopulate_stack()
        self._select_editor(self._last_selected)
        self._center.setCurrentIndex(center_idx)

        self.viewer.apply_language()

    # -------------------------------------------- name / output-path slots

    def _apply_name(self) -> None:
        v = self._name_edit.text().strip()
        if self.session.set_label(v):
            self._update_caption()
            self.refresh_code()
            self.notify.emit(tr('ui.workbench.optimization_name_value', value_0=v))
        else:
            self._name_edit.setText(self.problem.label)

    def _apply_path(self) -> None:
        v = self._path_edit.text().strip()
        if self.session.set_result_folder(v):
            self.refresh_code()

    def _save_device(self, text: str) -> None:
        """Persist the global compute device on the definition."""
        if self._device_block:
            return
        text = (text or "").strip()
        if not text:
            return
        if self.session.set_device(text):
            self.refresh_code()
            self.notify.emit(tr('ui.workbench.device_value', value_0=text))

    def _browse_path(self) -> None:
        start = self._path_edit.text() or os.getcwd()
        folder = QFileDialog.getExistingDirectory(
            self, tr('ui.workbench.select_output_folder'), start
        )
        if folder:
            self._path_edit.setText(folder)
            if self.session.set_result_folder(folder):
                self.refresh_code()

    def refresh_code(self, *, synchronize: bool = True) -> None:
        try:
            self.code_view.setPlainText(self.session.source(synchronize=synchronize))
        except Exception as exc:  # pragma: no cover
            self.code_view.setPlainText(f"# code generation failed:\n{exc}")

    # ------------------------------------------------------ node selection
    def _on_model_item_clicked(self, item, _column: int) -> None:
        # currentItemChanged does not fire when the selected row is clicked again.
        if self._center.currentWidget() is self.code_view:
            node = item.data(0, Qt.ItemDataRole.UserRole)
            if node is not None:
                self._on_node_selected(node)

    def _on_node_selected(self, node: Node) -> None:
        self._last_selected = node
        if self._center.currentWidget() is self.code_view:
            self._center.setCurrentIndex(0)
        if node is not None and node.kind in {"custom_class", "method_override"}:
            current = self.custom_tree.tree.currentItem()
            if current is None or current.data(0, Qt.ItemDataRole.UserRole) is not node:
                self.custom_tree.rebuild(select=node)
        if (node is not None and node.kind == "method_override"
                and self._stack.currentWidget() is self.custom_class_editor
                and self.custom_class_editor.current_method is node):
            return
        self._select_editor(node)

    def _override_method(self, node: Node) -> None:
        self._on_node_selected(node)
        self.custom_class_editor.add_override()

    def _register_editor_pages(self) -> None:
        self.pages = EditorPages(self._stack, self._schedule_rebuild)
        for kind, editor in (
            (EditorKind.CUSTOM_CLASS, self.custom_class_editor),
            (EditorKind.SOLVER, self.solver_editor),
            (EditorKind.STEPS, self.step_matrix),
        ):
            self.pages.register(
                kind,
                editor,
                lambda route, problem, editor=editor: editor.edit_node(route.node, problem),
                changed=editor.changed,
            )
        for kind, editor, section in (
            (EditorKind.GEOMETRY, self.geometry_editor, "geometry"),
            (EditorKind.LOADS, self.loads_editor, "loads"),
            (EditorKind.MATERIALS, self.materials_editor, "materials"),
        ):
            self.pages.register(
                kind,
                editor,
                lambda route, problem, editor=editor, section=section: editor.edit_node(
                    problem.section(section),
                    problem,
                    focus=route.focus,
                ),
                changed=editor.changed,
            )
        self.pages.register(
            EditorKind.UPDATER,
            self.updater_editor,
            lambda route, problem: self.updater_editor.edit_node(route.node, problem, focus=route.focus),
            changed=self.updater_editor.changed,
        )
        self.pages.register(
            EditorKind.OBJECTIVE,
            self.objective_editor,
            lambda route, problem: self.objective_editor.set_problem(problem),
            changed=self.objective_editor.changed,
        )
        self.pages.register(
            EditorKind.HELPER_CODE,
            self.helper_page,
            lambda route, problem: self.helper_page.edit_node(route.node, problem),
            changed=self.helper_page.changed,
        )
        self.pages.register(EditorKind.OPTIMIZER_OVERVIEW, self.optimizer_overview, lambda route, problem: None)
        self.pages.register(
            EditorKind.PROPERTIES,
            self.prop_editor,
            self._bind_properties,
            changed=self.prop_editor.changed,
        )

    def _select_editor(self, node: Node | None) -> None:
        self.class_selector.edit_node(node, self.problem)
        route = route_editor(node)
        for kind, editor in (
            (EditorKind.GEOMETRY, self.geometry_editor),
            (EditorKind.LOADS, self.loads_editor),
            (EditorKind.MATERIALS, self.materials_editor),
        ):
            if route.kind is not kind:
                editor.invalidate()
        self.pages.select(route, self.problem)

    def _bind_properties(self, route: EditorRoute, problem: ProblemDefinition) -> None:
        node = route.node
        if node is None:
            return
        fields, code_slots, extra = fields_for_node(node, problem, sets=self.part_sets)
        title = container_title(node.kind) if node.kind in {"geometry", "problem", "params_class"} else None
        self.prop_editor.edit_node(
            node,
            fields=fields,
            code_slots=code_slots,
            extra_choices=extra,
            subtitle=self._subtitle(node),
            title=title,
            completion_problem=problem,
        )

    def _sync_single_imported_part(self, _node: Node) -> None:
        """Select unambiguous imported material targets without name conventions."""
        self.session.sync_imported_material_targets()

    @staticmethod
    def _subtitle(node: Node) -> str:
        if node.kind == "surface":
            return tr('ui.workbench.surface_0_outer_within_each_part_surfaces_1_cavities_flip_the_preview_up')
        if node.kind == "geometry":
            return tr('ui.workbench.define_the_optimization_s_initial_configuration_here_every_geometry_inte')
        if node.kind == "part_interface":
            if node.get_field("type") == "CADPartInterface":
                return tr('ui.workbench.use_the_buttons_below_or_the_context_menu_to_add_features_boolean_and_tr')
            return tr('ui.workbench.edit_the_geometry_interface_registration_name_here_it_owns_one_part_and')
        if node.kind == "instance":
            return tr('ui.workbench.translation_and_rotation_use_torchfea_exponential_coordinates_rotation_i')
        return ""

    # ------------------------------------------------------ change refresh
    def _schedule_rebuild(self, *_args) -> None:
        self._rebuild_timer.start()

    def _on_any_change(self) -> None:
        # Coalesce all editor signals into one refresh after re-binding the
        # model's object-reference graph.  Tree labels, open forms, generated
        # code, and the preview therefore observe the same model snapshot.
        self.session.synchronize()
        self.part_sets.invalidate()
        self.refresh_code(synchronize=False)
        try:
            self.viewer.set_problem(self.problem)
        except (TypeError, ValueError) as exc:
            self.notify.emit(tr('ui.workbench.preview_unavailable_value', value_0=exc))
        self.objective_editor.set_problem(self.problem)
        # refresh tree summaries (e.g. load param rows) and the visible editor
        self.tree.rebuild(select=self._last_selected, notify=False)
        self.custom_tree.rebuild(select=self._last_selected)
        if self._last_selected is not None:
            self._select_editor(self._last_selected)
        self.notify.emit(self.problem.label)

    def set_problem(self, problem: ProblemDefinition) -> None:
        self.session.replace(problem)
        self.part_sets.bind(problem)
        self._last_selected = None
        self.reload()

    # --------------------------------------------------------- footer slots
    def _submit_to_observer(self) -> None:
        try:
            self.session.validate_for_run()
        except MissingImportedModelError:
            QMessageBox.warning(
                self,
                tr('ui.workbench.torchfea_model_required'),
                tr('ui.workbench.select_a_model_directory_and_import_a_valid_npz_model_from_the_initial_g'),
            )
            return
        except Exception as exc:
            QMessageBox.warning(
                self,
                tr('ui.workbench.incomplete_optimization_definition'),
                str(exc),
            )
            return
        self.importToObserver.emit(self.problem)

    def set_message(self, text: str) -> None:
        self._msg.setText(text)
