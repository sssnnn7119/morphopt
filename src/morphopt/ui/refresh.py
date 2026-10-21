"""Shared refresh contract and ordered, coalesced UI updates."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from PySide6.QtCore import QObject, QTimer, Signal

from ..constants import CONSTANT
from .model.problem import Node, ProblemDefinition


@dataclass(frozen=True)
class RefreshContext:
    """One synchronized definition snapshot shared by all refresh participants."""

    problem: ProblemDefinition
    selected: Node | None = None
    changed_nodes: tuple[Node, ...] = ()
    full: bool = True
    restoring: bool = False

    @property
    def geometry_changed(self) -> bool:
        unrelated = {
            "fea_component",
            "loads",
            "loads_group",
            "steps",
            "solver",
            "objective",
            "updater",
            "problem",
            "params_class",
        }
        return self.full or any(
            node.kind not in unrelated and not node.kind.startswith("updater_")
            for node in self.changed_nodes
        )

    @property
    def loads_changed(self) -> bool:
        return self.geometry_changed or any(
            node.kind in {"fea_component", "loads", "loads_group", "steps"}
            for node in self.changed_nodes
        )


class Refreshable(Protocol):
    """A component refreshes its own presentation without editing the model."""

    def refresh_ui(self, context: RefreshContext) -> None: ...


class RefreshCoordinator(QObject):
    """Synchronize once, then refresh registered components in order.

    A change keeps its source node even when that node was deleted. An unknown
    source requests a full refresh and cannot be lost when changes coalesce.
    """

    failed = Signal(object, object)
    finished = Signal(object)

    def __init__(
        self,
        prepare: Callable[[tuple[Node | None, ...]], RefreshContext],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._prepare = prepare
        self._components: list[Refreshable] = []
        self._pending: list[Node | None] = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(CONSTANT.UI.TIMING.REFRESH_DEBOUNCE_MS)
        self._timer.timeout.connect(self.flush)

    def set_components(self, components: Sequence[Refreshable]) -> None:
        self._components = list(components)

    def request(self, node: Node | None = None) -> None:
        self._pending.append(node)
        self._timer.start()

    def refresh_now(self, node: Node | None = None) -> None:
        self._pending.append(node)
        self.flush()

    def cancel(self) -> None:
        """Discard pending sources before replacing their owning document."""
        self._timer.stop()
        self._pending.clear()

    def flush(self) -> None:
        self._timer.stop()
        if not self._pending:
            return
        changes, self._pending = tuple(self._pending), []
        context = self._prepare(changes)
        success = True
        for component in self._components:
            try:
                component.refresh_ui(context)
            except Exception as exc:
                # Report the traceback and keep independent views up to date.
                logging.getLogger(__name__).exception(
                    "UI refresh failed in %s", type(component).__name__
                )
                self.failed.emit(component, exc)
                success = False
        if success:
            self.finished.emit(context)
