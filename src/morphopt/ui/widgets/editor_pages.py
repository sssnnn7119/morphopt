"""Registry binding editor routes to Qt pages and their bind functions."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from PySide6.QtWidgets import QStackedWidget, QWidget
from PySide6.QtCore import SignalInstance
from ..application.editor_routing import EditorKind, EditorRoute
from ..model.problem import ProblemDefinition


@dataclass(frozen=True)
class EditorPage:
    widget: QWidget
    bind: Callable[[EditorRoute, ProblemDefinition], None]


class EditorPages:
    def __init__(self, stack: QStackedWidget, on_change: Callable | None = None):
        self.stack = stack
        self.on_change = on_change
        self._pages: dict[EditorKind, EditorPage] = {}

    def register(
        self,
        kind: EditorKind,
        widget: QWidget,
        bind: Callable[[EditorRoute, ProblemDefinition], None],
        *, changed: SignalInstance | None = None,
    ) -> None:
        self._pages[kind] = EditorPage(widget, bind)
        self.stack.addWidget(widget)
        if changed is not None and self.on_change is not None:
            changed.connect(self.on_change)

    def select(self, route: EditorRoute, problem: ProblemDefinition) -> None:
        page = self._pages[route.kind]
        page.bind(route, problem)
        self.stack.setCurrentWidget(page.widget)
