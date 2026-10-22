"""Definition workspace.

Layout:
  center      three tabs:
                1. 编辑   -> a QStackedWidget routed by the selected tree node
                              (controller / properties / helper code / solver / loads /
                               steps / updater / objective pages)
                2. 代码(只读) -> generated ``ThisController`` (auto-synced)
                3. 资产 -> referenced files and category-specific previews
  right       PyVista preview of the initial geometry + per-step loads

File actions and workspace switching belong to MainWindow.

Interchange is the ``*.morph`` JSON (open/export); the runnable ``*.py`` is
generated from the model in the read-only code tab (no .py import).
"""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import QEvent, QObject, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..constants import CONSTANT
from .application import (
    EditorKind,
    EditorRoute,
    ProblemSession,
    route_editor,
)
from .application.edit_history import EditOperation
from .application.fields import fields_for_node
from .application.part_sets import PartSetCatalog
from .i18n import tr
from .model.problem import (
    Node,
    ProblemDefinition,
)
from .presentation.edit_history import edit_description
from .presentation.labels import node_title
from .presentation.navigation import ObjectiveItemTreeNode, node_at_path, node_path
from .refresh import Refreshable, RefreshContext, RefreshCoordinator
from .schemes.base import scheme_label
from .theme import theme_manager
from .widgets.collection_controls import CollectionHeader
from .widgets.controller_editor import ControllerSettingsEditor
from .widgets.custom_classes import (
    CustomClassEditor,
    CustomClassOverview,
    ModelClassSelector,
)
from .widgets.definition_actions import DefinitionActions
from .widgets.definition_manager import DefinitionManagerEditor
from .widgets.edit_history import EditHistoryPanel
from .widgets.history_dialogs import HistoryCapacityDialog
from .widgets.editor import PropertyEditor
from .widgets.editor_pages import EditorPages
from .widgets.helper_editor import HelperCodeEditor
from .widgets.model_tree import ModelTree
from .widgets.objective_editor import ObjectiveEditor
from .widgets.solver_editor import SolverEditor
from .widgets.source_view import GeneratedSourceView
from .widgets.asset_browser import AssetBrowser
from .widgets.load_cases import LoadCaseEditor
from .widgets.updater_editor import UpdaterEditor
from .widgets.viewer import PreviewViewer


class Workbench(QWidget):
    notify = Signal(str)
    startOptimizationRequested = Signal(object)

    def __init__(self, problem: ProblemDefinition, parent=None):
        super().__init__(parent)
        self._restoring = False
        self._history_ready = False
        self._synchronized_for_refresh = False
        self._text_edit_key: int | None = None
        self.session = ProblemSession(problem)
        self.session.history.set_max_nodes(QSettings("MorphOptUI", "ui").value(
            "history/max_nodes", CONSTANT.UI.HISTORY.MAX_NODES, int,
        ))
        self._history_capacity_queued = False
        self._history_capacity_dialog: HistoryCapacityDialog | None = None
        self.part_sets = PartSetCatalog(problem)
        self._last_selected: Node | None = None
        self.refresh_coordinator = RefreshCoordinator(self._prepare_refresh, self)
        self.refresh_coordinator.failed.connect(self._on_refresh_failed)
        self.refresh_coordinator.finished.connect(
            lambda context: self.notify.emit(context.problem.label)
        )
        self._build_ui()
        self._register_refreshables()
        self.reload()
        self.session.reset_history()
        self._history_ready = True
        self._update_history_actions()
        QApplication.instance().installEventFilter(self)

    @property
    def problem(self) -> ProblemDefinition:
        """The canonical definition owned by this workbench's session."""
        return self.session.problem

    # ------------------------------------------------------------- layout
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(*theme_manager.palette.layout.zero_margins)

        split = QSplitter(Qt.Orientation.Horizontal)

        # ---- left tree
        self.actions = DefinitionActions(self)
        self.tree = ModelTree(actions=self.actions)
        self.tree.nodeSelected.connect(self._on_node_selected)
        self.tree.itemClicked.connect(self._on_model_item_clicked)
        self.actions.changed.connect(self._on_structural_change)
        self.actions.selectionRequested.connect(self._on_node_selected)
        self.tree.classMethodAddRequested.connect(self._add_custom_method)
        self.history_panel = EditHistoryPanel(self)
        self.history_panel.jumpRequested.connect(self._jump_to_history_step)
        self.history_panel.undoRequested.connect(self.undo)
        self.history_panel.redoRequested.connect(self.redo)
        self._undo_button = self.history_panel.undo_button
        self._redo_button = self.history_panel.redo_button
        self._tree_split = QSplitter(Qt.Orientation.Vertical)
        self._tree_split.addWidget(self.tree)
        self._tree_split.addWidget(self.history_panel)
        self._tree_split.setSizes(
            list(theme_manager.palette.layout.workbench.left_split_sizes)
        )
        self._tree_split.setChildrenCollapsible(False)
        split.addWidget(self._tree_split)

        # ---- center: editor, generated source and assets
        center = QTabWidget()
        self._center = center

        self._stack = QStackedWidget()
        self._repopulate_stack()
        edit_page = QWidget()
        edit_layout = QVBoxLayout(edit_page)
        edit_layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self.class_selector = ModelClassSelector()
        self.class_selector.changed.connect(self._on_model_change)
        edit_layout.addWidget(self.class_selector)
        edit_layout.addWidget(self._stack, 1)
        center.addTab(edit_page, tr("ui.workbench.edit"))

        self.code_view = GeneratedSourceView()
        self.code_view.setReadOnly(True)
        self.code_view.setFont(
            QFont(
                theme_manager.palette.code_editor.font_family,
                theme_manager.palette.code_editor.font_size,
            )
        )
        center.addTab(self.code_view, tr("ui.workbench.code_read_only"))
        self.asset_view = AssetBrowser()
        center.addTab(self.asset_view, tr("ui.workbench.assets"))
        center.setMinimumWidth(
            theme_manager.palette.layout.workbench.editor_minimum_width
        )
        split.addWidget(center)

        # ---- right preview
        self.viewer = PreviewViewer()
        split.addWidget(self.viewer)

        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setStretchFactor(2, 1)
        split.setSizes(list(theme_manager.palette.layout.workbench.main_split_sizes))
        outer.addWidget(split, 1)

        self._msg = QLabel(self)
        self._msg.setProperty("textRole", "muted")
        outer.addWidget(self._msg)

    # --------------------------------------------------------- center stack
    def _repopulate_stack(self) -> None:
        """(Re)build the editor pages of the center "编辑" tab.

        Recreates the (cheap, form-only) editors in place so all their
        localized texts are regenerated in the current language.  All data
        lives on the model nodes, so nothing is lost.  The PyVista preview
        viewport and the tree are *not* rebuilt here.
        """
        stack = self._stack
        if stack.count():
            self.pages.disconnect_changes()
        while stack.count():
            w = stack.widget(0)
            w.hide()
            stack.removeWidget(w)
            w.deleteLater()

        self.prop_editor = PropertyEditor(stack)
        self.controller_editor = ControllerSettingsEditor(stack)
        self.controller_editor.labelChanged.connect(self._apply_name)
        self.controller_editor.resultFolderChanged.connect(self._apply_path)
        self.controller_editor.deviceChanged.connect(self._save_device)
        self.solver_editor = SolverEditor(stack)
        self.load_cases = LoadCaseEditor(stack)
        self.load_cases.objectiveRequested.connect(self._on_node_selected)
        self.load_cases.objectiveRequested.connect(self.tree.select_node)
        self.updater_editor = UpdaterEditor(stack)
        self.updater_editor.activated.connect(self._on_editor_activated)
        self.geometry_editor = DefinitionManagerEditor(
            "geometry", self.actions, parent=stack, sets=self.part_sets
        )
        self.loads_editor = DefinitionManagerEditor(
            "loads", self.actions, parent=stack, sets=self.part_sets
        )
        self.materials_editor = DefinitionManagerEditor(
            "materials", self.actions, parent=stack, sets=self.part_sets
        )
        self.helper_variables_editor = DefinitionManagerEditor(
            "helper_variables", self.actions, parent=stack
        )
        self.helper_functions_editor = DefinitionManagerEditor(
            "helper_functions", self.actions, parent=stack
        )
        for editor in (
            self.prop_editor,
            self.geometry_editor,
            self.loads_editor,
            self.materials_editor,
            self.helper_variables_editor,
            self.helper_functions_editor,
        ):
            editor.activated.connect(self._on_editor_activated)
        self.objective_editor = ObjectiveEditor(stack)
        self.objective_editor.activated.connect(self._on_editor_activated)
        self.custom_class_editor = CustomClassEditor(stack)
        self.custom_class_overview = CustomClassOverview(self.actions, stack)
        self.custom_class_overview.nodeSelected.connect(self._on_node_selected)
        self.optimizer_overview = self._make_optimizer_overview()
        self.helper_page = HelperCodeEditor(self.actions, parent=stack)
        self.helper_page.edit_node(None, self.problem)
        self.custom_class_editor.nodeSelected.connect(self._on_node_selected)
        self._register_editor_pages()

    def _make_optimizer_overview(self) -> QWidget:
        """Create an updater by choosing its concrete component target."""
        overview = QWidget(self._stack)
        layout = QVBoxLayout(overview)
        targets = QMenu(overview)
        targets.aboutToShow.connect(lambda: self.actions.populate_updater_menu(targets))
        header = CollectionHeader(
            tr("ui.widgets.model_tree.container.updater"), menu=targets
        )
        header.add_button.setToolTip(tr("ui.component.add_updater"))
        layout.addWidget(header)
        description = QLabel(
            tr(
                "ui.workbench.optimization_definition_this_section_contains_the_optimization_objective"
            )
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignTop)
        description.setContentsMargins(
            *deepcopy(theme_manager.palette.layout.workbench.description_margins)
        )
        layout.addWidget(description)
        layout.addStretch(1)
        return overview

    # ------------------------------------------------------------- reload
    def reload(self) -> None:
        self.actions.set_problem(self.problem)
        self._select_editor(self._last_selected)
        self.refresh_coordinator.refresh_now()

    def refresh_ui(self, context: RefreshContext) -> None:
        self._update_caption()

    def _update_caption(self) -> None:
        title = tr(
            "ui.naming.problem_title",
            name=self.problem.label,
            scheme=scheme_label(self.problem.scheme),
        )
        if self.session.history.is_modified:
            title = tr("ui.history.modified", title=title)
        self.setWindowTitle(title)

    # ------------------------------------------------------------ language
    def apply_language(self) -> None:
        """Re-apply the current language to the whole definition page in place.

        Unlike the old behaviour this does *not* destroy and recreate the whole
        workbench (which recreated the PyVista viewport and blackened the
        observer's GL pages).  The shell texts, the model-tree titles and the
        centre editors are all refreshed; the preview viewport keeps its state.
        """
        self.flush_edits()
        self._update_caption()
        self._center.setTabText(0, tr("ui.workbench.edit"))
        self._center.setTabText(1, tr("ui.workbench.code_read_only"))
        self._center.setTabText(2, tr("ui.workbench.assets"))
        # Refresh the model-tree titles and the centre editors in the new
        # language.  Only the cheap form editors are re-created (data lives on
        # the model nodes); the PyVista preview viewport is left untouched.
        self.tree.apply_language()
        self.class_selector.apply_language()
        center_idx = self._center.currentIndex()
        self._repopulate_stack()
        self._register_refreshables()
        self._select_editor(self._last_selected)
        self._center.setCurrentIndex(center_idx)

        self.viewer.apply_language()
        self.asset_view.apply_language()
        self.history_panel.apply_language()
        self._update_history_actions()

    def apply_theme(self) -> None:
        """Refresh theme-aware rendering and history visuals."""
        self.tree.apply_theme()
        self.code_view.setFont(
            QFont(
                theme_manager.palette.code_editor.font_family,
                theme_manager.palette.code_editor.font_size,
            )
        )
        self.viewer.apply_theme()
        self.asset_view.apply_theme()
        self.history_panel.apply_theme()

    # -------------------------------------------- name / output-path slots

    def _apply_name(self, value: str) -> None:
        v = value.strip()
        if self.session.set_label(v):
            self._update_caption()
            self._on_model_change(self.problem.root)
            self.notify.emit(tr("ui.workbench.optimization_name_value", value_0=v))
        else:
            self.controller_editor.set_name(self.problem.label)

    def _apply_path(self, value: str) -> None:
        v = value.strip()
        if self.session.set_result_folder(v):
            self._on_model_change(self.problem.root)

    def _save_device(self, text: str) -> None:
        """Persist the global compute device on the definition."""
        text = (text or "").strip()
        if not text:
            return
        if self.session.set_device(text):
            self._on_model_change(self.problem.root)
            self.notify.emit(tr("ui.workbench.device_value", value_0=text))

    # ------------------------------------------------------ node selection
    def _on_model_item_clicked(self, item, _column: int) -> None:
        # currentItemChanged does not fire when the selected row is clicked again.
        if self._center.currentIndex() != 0:
            node = item.data(0, Qt.ItemDataRole.UserRole)
            if node is not None:
                self._on_node_selected(node)

    def _on_node_selected(self, node: Node | None) -> None:
        if self._restoring:
            return
        self._last_selected = node
        if self.sender() is not self.actions:
            self._remember_selection()
        if self._center.currentWidget() is self.code_view:
            self._center.setCurrentIndex(0)
        if node is not None and node.kind in {
            "custom_class",
            "method_override",
            "custom_function",
        }:
            self.tree.select_node(node)
        if (
            node is not None
            and node.kind in {"method_override", "custom_function"}
            and self._stack.currentWidget() is self.custom_class_editor
            and self.custom_class_editor.current_method is node
        ):
            return
        self._select_editor(node)

    def _on_editor_activated(self, node: Node) -> None:
        if self._restoring:
            return
        self._last_selected = node
        self._remember_selection()
        self.tree.select_node(node)

    def _add_custom_method(self, node: Node) -> None:
        self._on_node_selected(node)
        self.custom_class_editor.add_member()

    def _register_editor_pages(self) -> None:
        self.pages = EditorPages(self._stack, self._on_model_change)
        self.pages.register(
            EditorKind.CONTROLLER,
            self.controller_editor,
            lambda _route, problem: self.controller_editor.edit_problem(problem),
            refreshable=self.controller_editor,
        )
        self.pages.register(
            EditorKind.CUSTOM_CLASSES,
            self.custom_class_overview,
            lambda route, problem: self.custom_class_overview.set_problem(
                problem, route.node
            ),
            refreshable=self.custom_class_overview,
        )
        for kind, editor in (
            (EditorKind.CUSTOM_CLASS, self.custom_class_editor),
            (EditorKind.SOLVER, self.solver_editor),
            (EditorKind.STEPS, self.load_cases),
        ):
            self.pages.register(
                kind,
                editor,
                lambda route, problem, editor=editor: editor.edit_node(
                    route.node, problem
                ),
                changed=editor.changed,
                refreshable=editor,
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
                refreshable=editor,
            )
        for kind, editor in (
            (EditorKind.HELPER_VARIABLES, self.helper_variables_editor),
            (EditorKind.HELPER_FUNCTIONS, self.helper_functions_editor),
        ):
            self.pages.register(
                kind,
                editor,
                lambda route, problem, editor=editor: editor.edit_node(
                    None, problem, focus=route.focus
                ),
                changed=editor.changed,
                refreshable=editor,
            )
        self.pages.register(
            EditorKind.UPDATER,
            self.updater_editor,
            lambda route, problem: self.updater_editor.edit_node(
                route.node, problem, focus=route.focus
            ),
            changed=self.updater_editor.changed,
            refreshable=self.updater_editor,
        )
        self.pages.register(
            EditorKind.OBJECTIVE,
            self.objective_editor,
            lambda route, problem: self.objective_editor.set_problem(
                problem,
                (
                    route.focus
                    if isinstance(route.focus, ObjectiveItemTreeNode)
                    else None
                ),
            ),
            changed=self.objective_editor.changed,
            refreshable=self.objective_editor,
        )
        self.pages.register(
            EditorKind.HELPER_CODE,
            self.helper_page,
            lambda route, problem: self.helper_page.edit_node(route.node, problem),
            changed=self.helper_page.changed,
            refreshable=self.helper_page,
        )
        self.pages.register(
            EditorKind.OPTIMIZER_OVERVIEW,
            self.optimizer_overview,
            lambda route, problem: None,
        )
        self.pages.register(
            EditorKind.PROPERTIES,
            self.prop_editor,
            self._bind_properties,
            changed=self.prop_editor.changed,
            refreshable=self.prop_editor,
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
        title = node_title(problem, node)
        self.prop_editor.edit_node(
            node,
            fields=fields,
            code_slots=code_slots,
            extra_choices=extra,
            subtitle=self._subtitle(node),
            title=title,
            completion_problem=problem,
        )

    @staticmethod
    def _subtitle(node: Node) -> str:
        if node.kind == "surface":
            return tr(
                "ui.workbench.surface_0_outer_within_each_part_surfaces_1_cavities_flip_the_preview_up"
            )
        if node.kind == "geometry":
            return tr(
                "ui.workbench.define_the_optimization_s_initial_configuration_here_every_geometry_inte"
            )
        if node.kind == "part":
            if node.get_field("type") == "CADPart":
                return tr(
                    "ui.workbench.use_the_buttons_below_or_the_context_menu_to_add_features_boolean_and_tr"
                )
            return tr(
                "ui.workbench.edit_the_part_registration_name_here_it_owns_one_part_and"
            )
        if node.kind == "instance":
            return tr(
                "ui.workbench.translation_and_rotation_use_torchfea_exponential_coordinates_rotation_i"
            )
        return ""

    # ------------------------------------------------------ change refresh
    def _register_refreshables(self) -> None:
        self.refresh_coordinator.set_components(
            [
                self,
                self.tree,
                self.class_selector,
                self.pages,
                self.code_view,
                self.asset_view,
                self.viewer,
            ]
        )

    def _prepare_refresh(self, changes: tuple[Node | None, ...]) -> RefreshContext:
        # Restored snapshots already contain their canonical definition.
        if not self._restoring and not self._synchronized_for_refresh:
            self.session.synchronize()
        self._synchronized_for_refresh = False
        self.part_sets.invalidate()
        return RefreshContext(
            self.problem,
            selected=self._last_selected,
            changed_nodes=tuple(node for node in changes if node is not None),
            full=None in changes,
            restoring=self._restoring,
        )

    def _on_refresh_failed(self, component: Refreshable, error: Exception) -> None:
        self.notify.emit(
            tr(
                "ui.refresh.failed",
                component=type(component).__name__,
                error=error,
            )
        )

    def set_problem(self, problem: ProblemDefinition) -> None:
        self._finish_text_edit()
        self.refresh_coordinator.cancel()
        self._synchronized_for_refresh = False
        self._text_edit_key = None
        self._history_ready = False
        self.session.replace(problem)
        self.part_sets.bind(problem)
        self._last_selected = None
        self._repopulate_stack()
        self._register_refreshables()
        self.reload()
        self.session.reset_history()
        self._history_ready = True
        self._update_history_actions()

    # ----------------------------------------------------- document history
    @staticmethod
    def _text_input(widget: QWidget | None) -> bool:
        return (
            isinstance(widget, (QLineEdit, QPlainTextEdit, QTextEdit))
            and not widget.isReadOnly()
        )

    @staticmethod
    def _local_undo_available(widget: QWidget | None, *, redo: bool) -> bool:
        if isinstance(widget, QLineEdit) and not widget.isReadOnly():
            return widget.isRedoAvailable() if redo else widget.isUndoAvailable()
        if isinstance(widget, (QPlainTextEdit, QTextEdit)) and not widget.isReadOnly():
            document = widget.document()
            return document.isRedoAvailable() if redo else document.isUndoAvailable()
        return False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not isinstance(watched, QWidget) or not self.isVisible():
            return super().eventFilter(watched, event)
        if (
            watched is not self
            and watched is not self.window()
            and not self.isAncestorOf(watched)
        ):
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.FocusOut:
            self.session.history.break_merge()
            self._text_edit_key = None
        if event.type() == QEvent.Type.FocusIn:
            self._text_edit_key = id(watched) if self._text_input(watched) else None
            if isinstance(watched, QLineEdit) and not watched.property(
                "historyObserved"
            ):
                watched.setProperty("historyObserved", True)
                watched.textEdited.connect(self._update_history_actions)
                watched.editingFinished.connect(self._update_history_actions)
        if event.type() == QEvent.Type.MouseButtonPress:
            # Tool buttons and popup menus can leave a code editor focused.
            # Their changes must not merge with that editor's typing session.
            text = watched if self._text_input(watched) else watched.parentWidget()
            self._text_edit_key = id(text) if self._text_input(text) else None
            if self._text_edit_key is None:
                self.session.history.break_merge()
        if isinstance(event, QKeyEvent):
            if event.type() == QEvent.Type.KeyPress:
                self._text_edit_key = id(watched) if self._text_input(watched) else None
            # Native text undo stays local to the focused input. All other
            # widgets use document history, without competing window shortcuts.
            undo = event.matches(QKeySequence.StandardKey.Undo)
            redo = event.matches(QKeySequence.StandardKey.Redo)
            if (undo or redo) and not self._local_undo_available(
                QApplication.focusWidget(), redo=redo
            ):
                if event.type() == QEvent.Type.ShortcutOverride:
                    event.accept()
                    return True
                if event.type() == QEvent.Type.KeyPress:
                    self.redo() if redo else self.undo()
                    return True
            if (
                event.type() == QEvent.Type.KeyPress
                and isinstance(watched, QLineEdit)
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            ):
                self.session.history.break_merge()
            if event.type() == QEvent.Type.KeyRelease and self._text_input(watched):
                self._update_history_actions()
        return super().eventFilter(watched, event)

    def _remember_selection(self) -> None:
        if self._history_ready and not self._restoring:
            self.session.history.remember_selection(
                node_path(self.problem, self._last_selected)
            )

    def _on_structural_change(
        self, node: Node | None = None, operation: EditOperation = "modified"
    ) -> None:
        self._on_model_change(node, structural=True, operation=operation)

    def _on_model_change(
        self,
        node: Node | None = None,
        *,
        structural: bool = False,
        operation: EditOperation = "modified",
    ) -> None:
        if self._restoring:
            return
        if self._history_ready:
            self.session.synchronize()
            self._synchronized_for_refresh = True
            focus = QApplication.focusWidget()
            merge_key = (
                self._text_edit_key
                if not structural
                and self._text_input(focus)
                and self._text_edit_key == id(focus)
                else None
            )
            target = (
                (node.name or node_title(self.problem, node))
                if node is not None
                else self.problem.label
            )
            previous_count = self.session.history.node_count
            self.session.record_edit(
                target,
                selection=node_path(self.problem, self._last_selected),
                merge_key=merge_key,
                operation=operation,
            )
            self._update_history_actions()
            if self.session.history.node_count > previous_count:
                self._schedule_history_capacity_check()
        if structural:
            self.refresh_coordinator.refresh_now(node)
        else:
            self.refresh_coordinator.request(node)

    def _schedule_history_capacity_check(self) -> None:
        if (
            self._history_capacity_queued
            or self._history_capacity_dialog is not None
            or not self.session.history.at_capacity
        ):
            return
        self._history_capacity_queued = True
        QTimer.singleShot(0, self, self._check_history_capacity)

    def _check_history_capacity(self) -> None:
        self._history_capacity_queued = False
        if self._history_capacity_dialog is None and self.session.history.at_capacity:
            self._resolve_history_capacity(self.session.history.max_nodes)

    def set_history_limit(self, max_nodes: int) -> None:
        """Apply a user-selected limit; ask before clearing existing history."""
        self._finish_text_edit()
        if max_nodes < self.session.history.node_count:
            self._resolve_history_capacity(max_nodes)
        else:
            self._store_history_limit(max_nodes)

    def _store_history_limit(self, max_nodes: int) -> None:
        self.session.history.set_max_nodes(max_nodes)
        QSettings("MorphOptUI", "ui").setValue("history/max_nodes", max_nodes)
        self._update_history_actions()

    def _resolve_history_capacity(self, requested_limit: int) -> None:
        self._finish_text_edit()
        history = self.session.history
        if history.node_count < requested_limit:
            self._store_history_limit(requested_limit)
            return
        dialog = HistoryCapacityDialog(history.node_count, requested_limit, self)
        self._history_capacity_dialog = dialog
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            if dialog.choice == "clear":
                history.clear()
                self._store_history_limit(requested_limit)
            elif dialog.choice == "expand":
                self._store_history_limit(dialog.new_limit.value())
        finally:
            self._history_capacity_dialog = None
            dialog.deleteLater()

    def _update_history_actions(self) -> None:
        history = self.session.history
        self.history_panel.set_history(history)
        focus = QApplication.focusWidget()
        pending_input = (
            isinstance(focus, QLineEdit)
            and self.isAncestorOf(focus)
            and not focus.isReadOnly()
            and focus.isUndoAvailable()
        )
        undo_description = (
            edit_description(history.current)
            if history.can_undo
            else tr("ui.history.current_input")
        )
        redo_description = (
            edit_description(history.target(1)) if history.can_redo else ""
        )
        for button, key, enabled, description, shortcut in (
            (
                self._undo_button,
                "undo",
                history.can_undo or pending_input,
                undo_description,
                "Ctrl+Z",
            ),
            (
                self._redo_button,
                "redo",
                history.can_redo,
                redo_description,
                "Ctrl+Shift+Z",
            ),
        ):
            button.setText(tr(f"ui.history.{key}"))
            button.setEnabled(enabled)
            button.setToolTip(
                tr(
                    f"ui.history.{key}_detail",
                    description=description,
                    shortcut=shortcut,
                )
                if enabled
                else tr(f"ui.history.{key}_empty")
            )
        self._update_caption()

    def _finish_text_edit(self) -> None:
        focus = QApplication.focusWidget()
        if focus is not None and self.isAncestorOf(focus):
            # QLineEdit writes many fields on editingFinished, including table
            # delegates. Commit them before saving or choosing a history entry.
            focus.clearFocus()
        self.session.history.break_merge()

    def flush_edits(self) -> None:
        self._finish_text_edit()
        self.refresh_coordinator.flush()

    def mark_saved(self) -> None:
        # File serialization can normalize references. Keep the saved marker
        # attached to the exact state that was written, rather than an index.
        previous_count = self.session.history.node_count
        self.session.record_edit(
            self.problem.label,
            selection=node_path(self.problem, self._last_selected),
        )
        self.session.history.mark_saved()
        self._update_history_actions()
        if self.session.history.node_count > previous_count:
            self._schedule_history_capacity_check()

    def undo(self) -> None:
        self._restore_edit(-1)

    def redo(self) -> None:
        self._restore_edit(1)

    def _restore_edit(self, offset: int) -> None:
        self._finish_text_edit()
        history = self.session.history
        if not (history.can_undo if offset < 0 else history.can_redo):
            return
        self._restore_history_step(history.target(offset).step_id)

    def _jump_to_history_step(self, step_id: int) -> None:
        self._finish_text_edit()
        # Input commits may trigger history-capacity choices; resolve the ID afterwards.
        if not self.session.history.contains(step_id):
            self.notify.emit(tr("ui.history.unavailable"))
            self._update_history_actions()
            return
        if step_id != self.session.history.current.step_id:
            self._restore_history_step(step_id)

    def _restore_history_step(self, step_id: int) -> None:
        self.refresh_coordinator.cancel()
        self._synchronized_for_refresh = False
        self._text_edit_key = None
        tree_state = self.tree.capture_view()
        page = self._stack.currentWidget()
        page_index = self._stack.currentIndex()
        scroll = [
            (area.verticalScrollBar().value(), area.horizontalScrollBar().value())
            for area in page.findChildren(QAbstractScrollArea)
        ]
        tab = self._center.currentIndex()
        self._restoring = True
        updates_enabled = self.updatesEnabled()
        self.setUpdatesEnabled(False)
        try:
            # Decode only the selected snapshot, even when skipping many steps.
            snapshot = self.session.restore_edit_step(step_id)
            self.part_sets.bind(self.problem)
            self.actions.set_problem(self.problem)
            self._last_selected = node_at_path(self.problem, snapshot.selection)
            # Inactive pages also hold model objects. Recreate the form pages
            # once on replay so none can later write to the previous document.
            self._repopulate_stack()
            self._register_refreshables()
            self._select_editor(self._last_selected)
            self.refresh_coordinator.refresh_now()
            self.tree.restore_view(tree_state)
            self._center.setCurrentIndex(tab)
            page = self._stack.currentWidget()

            def restore_scroll() -> None:
                if (
                    self._stack.currentWidget() is not page
                    or self._stack.currentIndex() != page_index
                ):
                    return
                for area, (vertical, horizontal) in zip(
                    page.findChildren(QAbstractScrollArea), scroll
                ):
                    area.verticalScrollBar().setValue(vertical)
                    area.horizontalScrollBar().setValue(horizontal)

            # Collection editors schedule scrolling to a selected card. Restore
            # the user's offsets after that layout, only while this page lives.
            restore_scroll()
            QTimer.singleShot(0, page, restore_scroll)
        except Exception as error:
            self.notify.emit(tr("ui.history.restore_failed", error=error))
        finally:
            self._restoring = False
            self._update_history_actions()
            self.setUpdatesEnabled(updates_enabled)

    # --------------------------------------------------------- task transfer
    def start_optimization(self) -> None:
        self.flush_edits()
        try:
            self.session.validate_references()
        except Exception as exc:
            QMessageBox.warning(
                self,
                tr("ui.workbench.incomplete_optimization_definition"),
                str(exc),
            )
            return
        self.startOptimizationRequested.emit(self.problem)

    def set_message(self, text: str) -> None:
        self._msg.setText(text)
