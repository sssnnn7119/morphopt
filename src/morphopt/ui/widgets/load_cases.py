"""Ordered named load-case cards with one row per parameterized load."""
from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel, QLineEdit, QMessageBox, QScrollArea, QVBoxLayout, QWidget

from ..application.editing import LoadCaseSession
from ..application.load_cases import case_objectives, unused_cases, workspace_case_status
from ..i18n import tr
from ..model.problem import FEAComponentNode, ProblemDefinition, StepsNode
from ..presentation.navigation import ObjectiveItemTreeNode
from ..presentation.labels import component_title_text
from ..refresh import RefreshContext
from ..theme import theme_manager
from .case_deletion import confirm_case_cleanup
from .collection_controls import CollectionHeader, ItemActions


class LoadCaseEditor(QWidget):
    changed = Signal(object)
    objectiveRequested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self._header = CollectionHeader(tr("ui.load_cases.title"), self._add)
        layout.addWidget(self._header)
        self._workspace_status = QLabel()
        self._workspace_status.setWordWrap(True)
        self._workspace_status.setTextFormat(Qt.TextFormat.RichText)
        self._workspace_status.linkActivated.connect(self._open_workspace)
        layout.addWidget(self._workspace_status)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self._cards = QVBoxLayout(body)
        self._cards.addStretch(1)
        scroll.setWidget(body)
        layout.addWidget(scroll)
        self._node: StepsNode | None = None
        self._problem: ProblemDefinition | None = None
        self._structure: tuple | None = None
        self._fields: dict[tuple[str, object], QLineEdit] = {}

    def edit_node(self, node: StepsNode, problem: ProblemDefinition) -> None:
        self._node, self._problem = node, problem
        self.session = LoadCaseSession(node, problem)
        summaries = []
        if problem.objective:
            for index, term in enumerate(problem.objective.objective_terms):
                if term.get("type") == "workspace":
                    title = escape(tr("ui.load_cases.workspace_link", index=index + 1))
                    status = escape(workspace_case_status(term, problem))
                    summaries.append(f'<a href="{index}">{title}</a>: {status}')
        self._workspace_status.setText("<br>".join(summaries))
        self._workspace_status.setVisible(bool(summaries))
        loads = problem.amplitude_components()
        structure = (id(node), tuple(node.step_values), tuple((id(load), load.name, load.num_values) for load in loads))
        if structure != self._structure:
            self._structure = structure
            self._fields.clear()
            while self._cards.count() > 1:
                item = self._cards.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            names = list(node.step_values)
            for index, name in enumerate(names):
                card = QGroupBox(name)
                layout = QVBoxLayout(card)
                layout.addWidget(ItemActions(index, len(names), lambda key=name: self._remove(key), lambda delta, key=name: self._move(key, delta)))
                form = QFormLayout()
                title = QLineEdit(name)
                title.editingFinished.connect(lambda key=name, edit=title: self._rename(key, edit))
                form.addRow(tr("ui.load_cases.name"), title)
                for component in loads:
                    edit = QLineEdit()
                    edit.setPlaceholderText(", ".join("0" for _ in range(component.num_values)))
                    edit.editingFinished.connect(lambda key=name, load=component, field=edit: self._save(key, load, field))
                    self._fields[name, component] = edit
                    form.addRow(component_title_text(component), edit)
                layout.addLayout(form)
                self._cards.insertWidget(self._cards.count() - 1, card)
        for (name, component), edit in self._fields.items():
            if not edit.hasFocus():
                values = node.step_values[name].get(component, [0.0] * component.num_values)
                edit.setText(", ".join(str(value) for value in values))

    def _open_workspace(self, link: str) -> None:
        index = int(link)
        objective = self._problem.objective
        self.objectiveRequested.emit(ObjectiveItemTreeNode(
            objective, "objective", index, objective.objective_terms[index],
        ))

    def refresh_ui(self, context: RefreshContext) -> None:
        if context.problem.steps is not None:
            self.edit_node(context.problem.steps, context.problem)

    def _emit(self) -> None:
        self.edit_node(self._node, self._problem)
        self.changed.emit(self._node)

    def _add(self) -> None:
        if self._node is not None:
            self.session.add()
            self._emit()

    def _rename(self, name: str, edit: QLineEdit) -> None:
        if name not in self._node.step_values:
            return
        try:
            self.session.rename(name, edit.text())
        except ValueError as error:
            QMessageBox.warning(self, tr("ui.load_cases.name"), str(error))
            edit.setText(name)
            return
        self._emit()

    def _move(self, name: str, delta: int) -> None:
        if self.session.move(name, delta):
            self._emit()

    def _remove(self, name: str) -> None:
        terms = case_objectives(self._problem, name)
        remove_terms = False
        remove_unused = False
        if terms:
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Icon.Question)
            dialog.setWindowTitle(tr("ui.load_cases.title"))
            dialog.setText(tr("ui.load_cases.remove_references", name=name, count=len(terms)))
            dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            dialog.button(QMessageBox.StandardButton.Yes).setText(tr("ui.load_cases.delete_objectives"))
            dialog.button(QMessageBox.StandardButton.No).setText(tr("ui.load_cases.clear_references"))
            dialog.setDefaultButton(QMessageBox.StandardButton.No)
            reply = dialog.exec()
            if reply not in (QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No):
                return
            remove_terms = reply == QMessageBox.StandardButton.Yes
            if remove_terms:
                siblings = [case for case in unused_cases(self._problem, terms) if case != name]
                remove_unused = confirm_case_cleanup(self, siblings)
                if remove_unused is None:
                    return
        self.session.remove(name, remove_objectives=remove_terms, remove_unused=remove_unused)
        self._emit()

    def _save(self, name: str, component: FEAComponentNode, edit: QLineEdit) -> None:
        if name in self._node.step_values and self.session.set_value(name, component, edit.text()):
            self.changed.emit(self._node)
