"""Load-case collection using the common interface-card editor."""

from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel

from ..application.load_cases import workspace_case_status
from ..i18n import tr
from ..model.problem import LoadCaseNode, ProblemDefinition, StepsNode
from ..presentation.navigation import ObjectiveItemTreeNode
from .definition_manager import DefinitionManagerEditor


class LoadCaseEditor(DefinitionManagerEditor):
    objectiveRequested = Signal(object)

    def __init__(self, actions, parent=None) -> None:
        super().__init__("steps", actions, parent)
        self._workspace_status = QLabel()
        self._workspace_status.setWordWrap(True)
        self._workspace_status.setTextFormat(Qt.TextFormat.RichText)
        self._workspace_status.linkActivated.connect(self._open_workspace)
        self.layout().insertWidget(2, self._workspace_status)

    def edit_node(
        self, node: StepsNode | None, problem: ProblemDefinition,
        focus: LoadCaseNode | None = None, *, scroll_to_focus: bool = True,
    ) -> None:
        summaries = []
        if problem.objective:
            for index, term in enumerate(problem.objective.objective_terms):
                if term.get("type") == "workspace":
                    title = escape(tr("ui.load_cases.workspace_link", index=index))
                    status = escape(workspace_case_status(term, problem))
                    summaries.append(f'<a href="{index}">{title}</a>: {status}')
        self._workspace_status.setText("<br>".join(summaries))
        self._workspace_status.setVisible(bool(summaries))
        super().edit_node(node, problem, focus, scroll_to_focus=scroll_to_focus)

    def _open_workspace(self, link: str) -> None:
        index = int(link)
        objective = self._problem.objective
        self.objectiveRequested.emit(ObjectiveItemTreeNode(
            objective, "objective", index, objective.objective_terms[index],
        ))
