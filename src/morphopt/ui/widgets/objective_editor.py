"""Editor for ordered, weighted objective terms."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from ...constants import CONSTANT
from ..application.load_cases import remove_objectives, unused_cases
from ..i18n import localization, tr
from ..model.node_types.loads import ReferencePointNode
from ..model.problem import ObjectiveNode, ProblemDefinition
from ..presentation.labels import component_title_text, node_title
from ..presentation.navigation import ObjectiveItemTreeNode
from ..refresh import RefreshContext
from ..schemes.base import get_template
from ..schemes.snippets import CodeSnippet
from ..theme import theme_manager
from .workspace_objective import WorkspaceObjectiveEditor
from .case_deletion import confirm_case_cleanup
from .codeeditor import CodeEditor
from .collection_controls import CollectionHeader, ItemActions, set_card_selected
from .template_insert_dialog import TemplateInsertDialog


class JacobianLoadSelector(QToolButton):
    """Multi-select the parameterized loads whose Jacobians are required."""

    selectionChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._load_names: list[str] = []
        self._checks: dict[str, QCheckBox] = {}
        self._menu = QMenu(self)
        self.setMenu(self._menu)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setProperty("menuButton", True)
        self.setFixedHeight(
            theme_manager.palette.layout.widgets.objective_selector_height
        )
        self._update_summary()

    def set_loads(
        self,
        load_names: list[str],
        selected_names: list[str],
        titles: dict[str, str] | None = None,
        required_names: set[str] | None = None,
    ) -> None:
        self._load_names = list(dict.fromkeys(name for name in load_names if name))
        required = required_names or set()
        selected = set(selected_names) | required
        self._menu.clear()
        self._checks.clear()
        for name in self._load_names:
            check = QCheckBox((titles or {}).get(name, name), self._menu)
            check.setChecked(name in selected)
            check.setEnabled(name not in required)
            check.toggled.connect(self._selection_changed)
            action = QWidgetAction(self._menu)
            action.setDefaultWidget(check)
            self._menu.addAction(action)
            self._checks[name] = check
        self.setEnabled(bool(self._load_names))
        self._update_summary()

    def selected_names(self) -> list[str]:
        return [name for name in self._load_names if self._checks[name].isChecked()]

    def _selection_changed(self) -> None:
        self._update_summary()
        self.selectionChanged.emit()

    def _update_summary(self) -> None:
        selected = self.selected_names()
        if not self._load_names:
            self.setText(tr("ui.widgets.objective_editor.no_parameterized_loads"))
            self.setToolTip(
                tr("ui.widgets.objective_editor.add_a_load_with_an_amplitude_first")
            )
        elif not selected:
            self.setText(tr("ui.widgets.objective_editor.none_selected"))
            self.setToolTip(
                tr("ui.widgets.objective_editor.select_loads_requiring_jacobians")
            )
        else:
            self.setText(
                tr(
                    "ui.widgets.objective_editor.value_value_selected",
                    value_0=len(selected),
                    value_1=len(self._load_names),
                )
            )
            self.setToolTip("\n".join(self._checks[name].text() for name in selected))


class ObjectiveEditor(QWidget):
    """Manage an ordered sum of built-in and user-defined objective terms."""

    changed = Signal(object)
    activated = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self._page_scroll = QScrollArea(self)
        self._page_scroll.setWidgetResizable(True)
        self._page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._page_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        outer_layout.addWidget(self._page_scroll)

        self._heading = QLabel()
        self._heading.setProperty("textRole", "sectionHeading")
        layout.addWidget(self._heading)

        self.jacobian_loads = JacobianLoadSelector()
        self.jacobian_loads.selectionChanged.connect(self._save_jacobian)
        form = QFormLayout()
        self._jacobian_label = QLabel()
        form.addRow(self._jacobian_label, self.jacobian_loads)
        layout.addLayout(form)

        self._add_menu = QMenu(self)
        self._add_actions: list[tuple[QAction, str]] = []
        for label_key, term_type in (
            ("displacement_term", CONSTANT.UI.OBJECTIVE.TYPE_DISPLACEMENT),
            ("custom_loss_term", CONSTANT.UI.OBJECTIVE.TYPE_CUSTOM_LOSS),
            ("workspace_term", CONSTANT.UI.OBJECTIVE.TYPE_WORKSPACE),
        ):
            action = self._add_menu.addAction(
                tr(f"ui.widgets.objective_editor.{label_key}")
            )
            self._add_actions.append((action, label_key))
            action.triggered.connect(
                lambda _checked=False, selected_type=term_type: self._add_term(
                    selected_type
                )
            )
        self._term_header = CollectionHeader(
            tr("ui.widgets.objective_editor.objective_terms"), menu=self._add_menu
        )
        layout.addWidget(self._term_header)

        self._hint = QLabel()
        self._hint.setWordWrap(True)
        self._hint.setProperty("textRole", "muted")
        layout.addWidget(self._hint)

        body = QWidget()
        body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._term_layout = QVBoxLayout(body)
        self._term_layout.setContentsMargins(
            *theme_manager.palette.layout.widgets.collection_contents_margins
        )
        self._term_layout.setSpacing(
            theme_manager.palette.layout.widgets.collection_spacing
        )
        self._term_layout.addStretch(1)
        layout.addWidget(body)

        self.metrics_group = QGroupBox()
        metrics_layout = QVBoxLayout(self.metrics_group)
        self._metric_menu = QMenu(self)
        self._metric_actions: list[tuple[QAction, str]] = []
        for label_key, metric_type in (
            ("displacement_metric", CONSTANT.UI.METRIC.TYPE_DISPLACEMENT),
            ("custom_metric", CONSTANT.UI.METRIC.TYPE_CUSTOM),
        ):
            action = self._metric_menu.addAction(
                tr(f"ui.widgets.objective_editor.{label_key}")
            )
            self._metric_actions.append((action, label_key))
            action.triggered.connect(
                lambda _checked=False, selected_type=metric_type: self._add_metric(
                    selected_type
                )
            )
        self._metric_header = CollectionHeader(
            tr("ui.widgets.objective_editor.metric_terms"), menu=self._metric_menu
        )
        metrics_layout.addWidget(self._metric_header)
        self._metric_hint = QLabel()
        self._metric_hint.setWordWrap(True)
        self._metric_hint.setProperty("textRole", "muted")
        metrics_layout.addWidget(self._metric_hint)

        metric_body = QWidget()
        metric_body.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        self._metric_layout = QVBoxLayout(metric_body)
        self._metric_layout.setContentsMargins(
            *theme_manager.palette.layout.widgets.collection_contents_margins
        )
        self._metric_layout.setSpacing(
            theme_manager.palette.layout.widgets.collection_spacing
        )
        self._metric_layout.addStretch(1)
        metrics_layout.addWidget(metric_body)
        layout.addWidget(self.metrics_group)
        layout.addStretch(1)
        self._page_scroll.setWidget(content)

        self._obj: ObjectiveNode | None = None
        self._problem: ProblemDefinition | None = None
        self._snippets: tuple[CodeSnippet, ...] = ()
        self._loading = False
        self._term_signature: tuple[object, ...] | None = None
        self._term_fields: list[dict[str, QWidget]] = []
        self._term_cards: list[QGroupBox] = []
        self._metric_signature: tuple[object, ...] | None = None
        self._metric_fields: list[dict[str, QWidget]] = []
        self._metric_cards: list[QGroupBox] = []
        self._focus_node: ObjectiveItemTreeNode | None = None
        self._term_focus_targets: dict[QWidget, ObjectiveItemTreeNode] = {}
        self._metric_focus_targets: dict[QWidget, ObjectiveItemTreeNode] = {}

    def set_problem(
        self,
        problem: ProblemDefinition,
        focus: ObjectiveItemTreeNode | None = None,
        *,
        scroll_to_focus: bool = True,
    ) -> None:
        self._problem = problem
        self._obj = problem.objective
        self._focus_node = focus
        self._heading.setText(
            node_title(problem, self._obj) if self._obj is not None else ""
        )
        self._term_header.title.setText(
            tr("ui.widgets.objective_editor.objective_terms")
        )
        self._metric_header.title.setText(
            tr("ui.widgets.objective_editor.metric_terms")
        )
        self._jacobian_label.setText(tr("ui.widgets.objective_editor.jacobian_needed"))
        for action, label_key in self._add_actions:
            action.setText(tr(f"ui.widgets.objective_editor.{label_key}"))
        self._term_header.add_button.setMenu(self._add_menu)
        self.metrics_group.setTitle(
            tr("ui.widgets.objective_editor.additional_metrics")
        )
        for action, label_key in self._metric_actions:
            action.setText(tr(f"ui.widgets.objective_editor.{label_key}"))
        self._metric_header.add_button.setMenu(self._metric_menu)

        self._loading = True
        try:
            self._snippets = get_template(problem.scheme).objective_code_snippets()
            if self._obj is not None:
                amplitude_components = problem.amplitude_components()
                workspace_loads = {
                    name for term in self._obj.objective_terms
                    if term.get("type") == CONSTANT.UI.OBJECTIVE.TYPE_WORKSPACE
                    for entry in term.get("inputs", [])
                    for name, _index in entry["parameters"]
                }
                self.jacobian_loads.set_loads(
                    [component.name for component in amplitude_components],
                    [component.name for component in self._obj.jacobian_needed],
                    {
                        component.name: component_title_text(component)
                        for component in amplitude_components
                    },
                    required_names=workspace_loads,
                )
            else:
                self.jacobian_loads.set_loads([], [])
            self._sync_terms()
            self._sync_metrics()
        finally:
            self._loading = False
        self._focus_selection(scroll=scroll_to_focus)

    def refresh_ui(self, context: RefreshContext) -> None:
        selected = (
            context.selected
            if isinstance(context.selected, ObjectiveItemTreeNode)
            else self._focus_node
        )
        self.set_problem(context.problem, selected, scroll_to_focus=False)

    def _focus_selection(self, *, scroll: bool) -> None:
        focus = self._focus_node
        for card in self._term_cards:
            set_card_selected(card, False)
        for card in self._metric_cards:
            set_card_selected(card, False)
        if focus is None or focus.objective_parent is not self._obj:
            return
        cards = (
            self._term_cards if focus.category == "objective" else self._metric_cards
        )
        if not 0 <= focus.index < len(cards):
            return
        card = cards[focus.index]
        set_card_selected(card, True)
        if scroll:
            QTimer.singleShot(
                0,
                lambda target=card: self._page_scroll.ensureWidgetVisible(target, 8, 8),
            )

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.FocusIn and isinstance(watched, QWidget):
            target = self._term_focus_targets.get(watched)
            if target is None:
                target = self._metric_focus_targets.get(watched)
            if target is not None:
                self.activated.emit(target)
        return super().eventFilter(watched, event)

    def _track_focus(
        self,
        widget: QWidget,
        target: ObjectiveItemTreeNode,
        focus_targets: dict[QWidget, ObjectiveItemTreeNode],
    ) -> None:
        for child in (widget, *widget.findChildren(QWidget)):
            child.installEventFilter(self)
            focus_targets[child] = target

    def _reference_points(self) -> list[ReferencePointNode]:
        if self._problem is None:
            return []
        return [
            item
            for item in self._problem.fea_components()
            if isinstance(item, ReferencePointNode) and item.name
        ]

    def _sync_terms(self) -> None:
        terms = self._obj.objective_terms if self._obj is not None else []
        signature = (
            id(self._obj),
            localization.locale,
            tuple(point.name for point in self._reference_points()),
            tuple((load.name, load.num_values) for load in self._problem.amplitude_components()) if self._problem else (),
            tuple(self._problem.steps.step_values) if self._problem and self._problem.steps else (),
            tuple(
                (
                    term.get("type"),
                    term.get("direction", CONSTANT.UI.OBJECTIVE.DEFAULT_DIRECTION),
                )
                for term in terms
            ),
            tuple(snippet.key for snippet in self._snippets),
        )
        self._term_header.add_button.setEnabled(self._obj is not None)
        if signature != self._term_signature:
            self._term_signature = signature
            self._rebuild_terms()
        else:
            self._update_term_controls()

        if self._obj is None:
            self._hint.setText("")
        elif not terms:
            self._hint.setText(tr("ui.widgets.objective_editor.add_an_objective_term"))
        elif not self._reference_points():
            self._hint.setText(
                tr("ui.widgets.objective_editor.add_reference_point_for_displacement")
            )
        else:
            self._hint.setText(
                tr("ui.widgets.objective_editor.weighted_sum_description")
            )

    def _sync_metrics(self) -> None:
        metrics = self._obj.metrics_terms if self._obj is not None else []
        signature = (
            id(self._obj),
            localization.locale,
            tuple(point.name for point in self._reference_points()),
            tuple((load.name, load.num_values) for load in self._problem.amplitude_components()) if self._problem else (),
            tuple(self._problem.steps.step_values) if self._problem and self._problem.steps else (),
            tuple(metric.get("type") for metric in metrics),
        )
        self._metric_header.add_button.setEnabled(self._obj is not None)
        if signature != self._metric_signature:
            self._metric_signature = signature
            self._rebuild_metrics()
        else:
            self._update_metric_controls()

        if not metrics:
            self._metric_hint.setText(
                tr("ui.widgets.objective_editor.add_a_metric_term")
            )
        else:
            self._metric_hint.setText(
                tr("ui.widgets.objective_editor.metric_description")
            )

    def _rebuild_metrics(self) -> None:
        while self._metric_layout.count():
            item = self._metric_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._metric_fields.clear()
        self._metric_cards.clear()
        self._metric_focus_targets.clear()
        metrics = self._obj.metrics_terms if self._obj is not None else []
        if not metrics:
            self._metric_layout.addWidget(
                QLabel(tr("ui.widgets.objective_editor.no_metric_terms"))
            )
        else:
            for index, metric in enumerate(metrics):
                card = self._metric_card(index, metric)
                self._metric_cards.append(card)
                self._metric_layout.addWidget(card)
        self._metric_layout.addStretch(1)
        self._focus_selection(scroll=False)

    def _metric_card(self, index: int, metric: dict) -> QGroupBox:
        assert self._obj is not None
        metric_type = str(metric.get("type") or CONSTANT.UI.METRIC.DEFAULT_TYPE)
        title_key = {
            CONSTANT.UI.METRIC.TYPE_DISPLACEMENT: "displacement_metric",
            CONSTANT.UI.METRIC.TYPE_CUSTOM: "custom_metric",
        }.get(metric_type, "metric_term")
        card = QGroupBox(
            f"{index + 1}. {tr(f'ui.widgets.objective_editor.{title_key}')}"
        )
        layout = QVBoxLayout(card)
        actions = ItemActions(
            index,
            len(self._obj.metrics_terms),
            lambda item=index: self._remove_metric(item),
            lambda delta, item=index: self._move_metric(item, delta),
        )
        layout.addWidget(actions)

        fields: dict[str, QWidget] = {}
        if metric_type == CONSTANT.UI.METRIC.TYPE_DISPLACEMENT:
            form = QFormLayout()
            point_combo = QComboBox()
            point_combo.addItem(
                tr("ui.widgets.objective_editor.select_reference_point"), ""
            )
            for point in self._reference_points():
                point_combo.addItem(point.name, point.name)
            self._set_combo_value(point_combo, metric.get("reference_point_name"))
            form.addRow(tr("ui.widgets.objective_editor.reference_point"), point_combo)
            fields["reference_point_name"] = point_combo

            step_combo = QComboBox()
            step_combo.addItem(tr("ui.widgets.objective_editor.select_load_case"), None)
            for step_name in self._problem.steps.step_values:
                step_combo.addItem(
                    step_name, step_name
                )
            self._set_combo_value(step_combo, metric.get("step_name"))
            form.addRow(tr("ui.widgets.objective_editor.load_case"), step_combo)
            fields["step_name"] = step_combo

            component_combo = QComboBox()
            component_combo.addItem(
                tr("ui.widgets.objective_editor.select_component"), ""
            )
            for component, _index in CONSTANT.UI.OBJECTIVE.DISPLACEMENT_COMPONENTS:
                component_combo.addItem(
                    tr(f"ui.widgets.objective_editor.component_{component}"), component
                )
            self._set_combo_value(component_combo, metric.get("component"))
            form.addRow(
                tr("ui.widgets.objective_editor.displacement_component"),
                component_combo,
            )
            fields["component"] = component_combo
            layout.addLayout(form)
        elif metric_type == CONSTANT.UI.METRIC.TYPE_CUSTOM:
            editor = CodeEditor(
                tr("ui.widgets.objective_editor.custom_metric_body"),
                completion_context="get_metrics",
            )
            if self._problem is not None:
                editor.set_completion_context("get_metrics", self._problem)
            self._set_editor_body(editor, str(metric.get("body") or ""))
            editor.edit.textChanged.connect(
                lambda item=index, widget=editor: self._save_metric_body(item, widget)
            )
            layout.addWidget(editor)
            fields["body"] = editor

        self._metric_fields.append(fields)
        target = ObjectiveItemTreeNode(self._obj, "metric", index, metric)
        self._track_focus(actions, target, self._metric_focus_targets)
        for widget in fields.values():
            self._track_focus(widget, target, self._metric_focus_targets)
        for key, widget in fields.items():
            if key == "body":
                continue
            if isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(
                    lambda _index, item=index, field=key, control=widget: (
                        self._update_metric(item, field, control.currentData())
                    )
                )
        return card

    def _update_metric_controls(self) -> None:
        if self._obj is None:
            return
        for index, fields in enumerate(self._metric_fields):
            if index >= len(self._obj.metrics_terms):
                break
            metric = self._obj.metrics_terms[index]
            for key, widget in fields.items():
                if widget.hasFocus() or key == "body":
                    continue
                if isinstance(widget, QComboBox):
                    with QSignalBlocker(widget):
                        self._set_combo_value(widget, metric.get(key))

    def _update_metric(self, index: int, key: str, value: object) -> None:
        if self._loading or self._obj is None:
            return
        if not 0 <= index < len(self._obj.metrics_terms):
            return
        if key == "step_name":
            value = str(value) if value is not None else None
        else:
            value = str(value or "")
        metric = self._obj.metrics_terms[index]
        if metric.get(key) == value:
            return
        metric[key] = value
        self.changed.emit(self._obj)

    def _save_metric_body(self, index: int, editor: CodeEditor) -> None:
        if self._loading or self._obj is None:
            return
        if not 0 <= index < len(self._obj.metrics_terms):
            return
        self._obj.metrics_terms[index]["body"] = editor.body()
        self.changed.emit(self._obj)

    def _add_metric(self, metric_type: str) -> None:
        if self._obj is None:
            return
        metric: dict[str, object] = {"type": metric_type}
        if metric_type == CONSTANT.UI.METRIC.TYPE_DISPLACEMENT:
            metric.update(
                {
                    "reference_point_name": "",
                    "step_name": None,
                    "component": "",
                }
            )
        else:
            metric["body"] = ""
        self._obj.metrics_terms.append(metric)
        self._metric_signature = None
        self._sync_metrics()
        self.changed.emit(self._obj)

    def _remove_metric(self, index: int) -> None:
        if self._obj is None:
            return
        if not self._delete_terms([self._obj.metrics_terms[index]]):
            return
        self._metric_signature = None
        self._sync_metrics()
        self.changed.emit(self._obj)

    def _move_metric(self, index: int, delta: int) -> None:
        if self._obj is None:
            return
        metrics = self._obj.metrics_terms
        destination = index + delta
        if not 0 <= destination < len(metrics):
            return
        metrics[index], metrics[destination] = metrics[destination], metrics[index]
        self._metric_signature = None
        self._sync_metrics()
        self.changed.emit(self._obj)

    def _rebuild_terms(self) -> None:
        while self._term_layout.count():
            item = self._term_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._term_fields.clear()
        self._term_cards.clear()
        self._term_focus_targets.clear()
        terms = self._obj.objective_terms if self._obj is not None else []
        if not terms:
            self._term_layout.addWidget(
                QLabel(tr("ui.widgets.objective_editor.no_objective_terms"))
            )
        else:
            for index, term in enumerate(terms):
                card = self._term_card(index, term)
                self._term_cards.append(card)
                self._term_layout.addWidget(card)
        self._term_layout.addStretch(1)
        self._focus_selection(scroll=False)

    def _term_card(self, index: int, term: dict) -> QGroupBox:
        assert self._obj is not None
        term_type = str(term.get("type") or CONSTANT.UI.OBJECTIVE.DEFAULT_TYPE)
        title_key = {
            CONSTANT.UI.OBJECTIVE.TYPE_DISPLACEMENT: "displacement_term",
            CONSTANT.UI.OBJECTIVE.TYPE_CUSTOM_LOSS: "custom_loss_term",
            CONSTANT.UI.OBJECTIVE.TYPE_WORKSPACE: "workspace_term",
        }.get(term_type, "objective_term")
        card = QGroupBox(
            f"{index + 1}. {tr(f'ui.widgets.objective_editor.{title_key}')}"
        )
        layout = QVBoxLayout(card)
        actions = ItemActions(
            index,
            len(self._obj.objective_terms),
            lambda item=index: self._remove_term(item),
            lambda delta, item=index: self._move_term(item, delta),
        )
        layout.addWidget(actions)

        form = QFormLayout()
        fields: dict[str, QWidget] = {}
        if term_type == CONSTANT.UI.OBJECTIVE.TYPE_DISPLACEMENT:
            direction = QComboBox()
            for label_key, value in (
                ("direction_target", CONSTANT.UI.OBJECTIVE.DIRECTION_TARGET),
                ("direction_maximize", CONSTANT.UI.OBJECTIVE.DIRECTION_MAXIMIZE),
                ("direction_minimize", CONSTANT.UI.OBJECTIVE.DIRECTION_MINIMIZE),
            ):
                direction.addItem(tr(f"ui.widgets.objective_editor.{label_key}"), value)
            self._set_combo_value(
                direction,
                term.get("direction", CONSTANT.UI.OBJECTIVE.DEFAULT_DIRECTION),
            )
            form.addRow(tr("ui.widgets.objective_editor.direction"), direction)
            fields["direction"] = direction

            point_combo = QComboBox()
            point_combo.addItem(
                tr("ui.widgets.objective_editor.select_reference_point"), ""
            )
            for point in self._reference_points():
                point_combo.addItem(point.name, point.name)
            self._set_combo_value(point_combo, term.get("reference_point_name"))
            form.addRow(tr("ui.widgets.objective_editor.reference_point"), point_combo)
            fields["reference_point_name"] = point_combo

            step_combo = QComboBox()
            step_combo.addItem(tr("ui.widgets.objective_editor.select_load_case"), None)
            for step_name in self._problem.steps.step_values:
                step_combo.addItem(
                    step_name, step_name
                )
            self._set_combo_value(step_combo, term.get("step_name"))
            form.addRow(tr("ui.widgets.objective_editor.load_case"), step_combo)
            fields["step_name"] = step_combo

            component_combo = QComboBox()
            component_combo.addItem(
                tr("ui.widgets.objective_editor.select_component"), ""
            )
            for component, _index in CONSTANT.UI.OBJECTIVE.DISPLACEMENT_COMPONENTS:
                component_combo.addItem(
                    tr(f"ui.widgets.objective_editor.component_{component}"), component
                )
            self._set_combo_value(component_combo, term.get("component"))
            form.addRow(
                tr("ui.widgets.objective_editor.displacement_component"),
                component_combo,
            )
            fields["component"] = component_combo

        displacement_target = (
            term_type == CONSTANT.UI.OBJECTIVE.TYPE_DISPLACEMENT
            and term.get("direction", CONSTANT.UI.OBJECTIVE.DEFAULT_DIRECTION)
            == CONSTANT.UI.OBJECTIVE.DIRECTION_TARGET
        )
        if displacement_target:
            target = self._numeric_field(
                CONSTANT.UI.OBJECTIVE.TARGET_MINIMUM,
                CONSTANT.UI.OBJECTIVE.TARGET_MAXIMUM,
                term.get("target", CONSTANT.UI.OBJECTIVE.DEFAULT_TARGET),
            )
            target_label = (
                "displacement_target_value"
                if term_type == CONSTANT.UI.OBJECTIVE.TYPE_DISPLACEMENT
                else "target_value"
            )
            form.addRow(tr(f"ui.widgets.objective_editor.{target_label}"), target)
            fields["target"] = target

        weight = self._numeric_field(
            CONSTANT.UI.OBJECTIVE.WEIGHT_MINIMUM,
            CONSTANT.UI.OBJECTIVE.WEIGHT_MAXIMUM,
            term.get("weight", CONSTANT.UI.OBJECTIVE.DEFAULT_WEIGHT),
        )
        form.addRow(tr("ui.widgets.objective_editor.weight"), weight)
        fields["weight"] = weight
        layout.addLayout(form)

        if term_type == CONSTANT.UI.OBJECTIVE.TYPE_WORKSPACE and self._problem is not None:
            workspace = WorkspaceObjectiveEditor(term, self._problem)
            workspace.changed.connect(lambda: self.changed.emit(self._obj))
            layout.addWidget(workspace)
            fields["workspace"] = workspace

        if term_type == CONSTANT.UI.OBJECTIVE.TYPE_CUSTOM_LOSS:
            editor = CodeEditor(
                tr("ui.widgets.objective_editor.custom_loss_body"),
                completion_context="_objective_function",
            )
            if self._problem is not None:
                editor.set_completion_context("_objective_function", self._problem)
            self._set_editor_body(editor, str(term.get("body") or ""))
            editor.edit.textChanged.connect(
                lambda item=index, widget=editor: self._save_term_body(item, widget)
            )
            layout.addWidget(self._snippet_controls(editor))
            layout.addWidget(editor)
            fields["body"] = editor

        self._term_fields.append(fields)
        target = ObjectiveItemTreeNode(self._obj, "objective", index, term)
        self._track_focus(actions, target, self._term_focus_targets)
        for widget in fields.values():
            self._track_focus(widget, target, self._term_focus_targets)
        for key, widget in fields.items():
            if key == "body":
                continue
            if isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(
                    lambda _index, item=index, field=key, control=widget: (
                        self._update_term(item, field, control.currentData())
                    )
                )
            elif isinstance(widget, QDoubleSpinBox):
                widget.valueChanged.connect(
                    lambda value, item=index, field=key: self._update_term(
                        item, field, value
                    )
                )
        return card

    def _snippet_controls(self, editor: CodeEditor) -> QWidget:
        controls = QWidget()
        row = QHBoxLayout(controls)
        row.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        combo = QComboBox()
        for snippet in self._snippets:
            combo.addItem(tr(snippet.name_key), snippet)
        combo.setCurrentIndex(0 if combo.count() else -1)
        button = QPushButton(tr("ui.widgets.objective_editor.insert_snippet"))
        button.setEnabled(bool(combo.count()))
        button.clicked.connect(
            lambda _checked=False, target=editor, selector=combo: self._insert_template(
                target, selector
            )
        )
        row.addWidget(QLabel(tr("ui.widgets.objective_editor.template")))
        row.addWidget(combo, 1)
        row.addWidget(button)
        controls.setVisible(bool(combo.count()))
        return controls

    @staticmethod
    def _numeric_field(minimum: float, maximum: float, value: object) -> QDoubleSpinBox:
        field = QDoubleSpinBox()
        field.setRange(minimum, maximum)
        field.setDecimals(CONSTANT.UI.OBJECTIVE.FIELD_DECIMALS)
        field.setValue(float(value))
        return field

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(max(index, 0))

    @staticmethod
    def _set_editor_body(editor: CodeEditor, body: str) -> None:
        if editor.body() != body:
            editor.set_body(body)

    def _update_term_controls(self) -> None:
        if self._obj is None:
            return
        for index, fields in enumerate(self._term_fields):
            if index >= len(self._obj.objective_terms):
                break
            term = self._obj.objective_terms[index]
            for key, widget in fields.items():
                if widget.hasFocus() or key == "body":
                    continue
                if isinstance(widget, QComboBox):
                    with QSignalBlocker(widget):
                        self._set_combo_value(widget, term.get(key))
                elif isinstance(widget, WorkspaceObjectiveEditor):
                    widget.refresh_status()
                elif isinstance(widget, QDoubleSpinBox):
                    value = term.get(key)
                    if value is not None:
                        with QSignalBlocker(widget):
                            widget.setValue(float(value))

    def _update_term(self, index: int, key: str, value: object) -> None:
        if self._loading or self._obj is None:
            return
        if not 0 <= index < len(self._obj.objective_terms):
            return
        if key == "step_name":
            value = str(value) if value is not None else None
        elif key in {"target", "weight"}:
            value = float(value)
        elif key == "direction":
            value = str(value)
        else:
            value = str(value or "")
        term = self._obj.objective_terms[index]
        if term.get(key) == value:
            return
        term[key] = value
        if key == "direction":
            self._term_signature = None
            self._sync_terms()
        self.changed.emit(self._obj)

    def _save_term_body(self, index: int, editor: CodeEditor) -> None:
        if (
            self._loading
            or self._obj is None
            or not 0 <= index < len(self._obj.objective_terms)
        ):
            return
        self._obj.objective_terms[index]["body"] = editor.body()
        self.changed.emit(self._obj)

    def _save_jacobian(self) -> None:
        if self._loading or self._obj is None or self._problem is None:
            return
        self._problem.set_jacobian_components(self.jacobian_loads.selected_names())
        self.changed.emit(self._obj)

    def _add_term(self, term_type: str) -> None:
        if self._obj is None:
            return
        term: dict[str, object] = {
            "type": term_type,
            "weight": CONSTANT.UI.OBJECTIVE.DEFAULT_WEIGHT,
        }
        if term_type == CONSTANT.UI.OBJECTIVE.TYPE_DISPLACEMENT:
            term.update(
                {
                    "reference_point_name": "",
                    "step_name": None,
                    "component": "",
                    "direction": CONSTANT.UI.OBJECTIVE.DEFAULT_DIRECTION,
                    "target": CONSTANT.UI.OBJECTIVE.DEFAULT_TARGET,
                }
            )
        elif term_type == CONSTANT.UI.OBJECTIVE.TYPE_WORKSPACE:
            term.update(kind="workspace_plane", reference_point_name="", inputs=[], gauss_order=2, normalization=1.0, case_names=[])
        else:
            term["body"] = ""
        self._obj.objective_terms.append(term)
        self._term_signature = None
        self._sync_terms()
        self.changed.emit(self._obj)

    def _delete_terms(self, terms: list[dict]) -> bool:
        remove_unused = confirm_case_cleanup(self, unused_cases(self._problem, terms))
        if remove_unused is None:
            return False
        remove_objectives(self._problem, terms, remove_unused)
        return True

    def _remove_term(self, index: int) -> None:
        if self._obj is None:
            return
        if not self._delete_terms([self._obj.objective_terms[index]]):
            return
        self._term_signature = None
        self._sync_terms()
        self.changed.emit(self._obj)

    def _move_term(self, index: int, delta: int) -> None:
        if self._obj is None:
            return
        terms = self._obj.objective_terms
        destination = index + delta
        if not 0 <= destination < len(terms):
            return
        terms[index], terms[destination] = terms[destination], terms[index]
        self._term_signature = None
        self._sync_terms()
        self.changed.emit(self._obj)

    def _insert_template(self, editor: CodeEditor, combo: QComboBox) -> None:
        index = combo.currentIndex()
        if index < 0 or self._problem is None:
            return
        snippet = combo.itemData(index)
        if snippet is None:
            return
        dialog = TemplateInsertDialog(snippet, self._problem, self)
        if not dialog.exec():
            return
        source = snippet.render(dialog.parameter_values())
        editor.insert_snippet(source, at_cursor=True)
