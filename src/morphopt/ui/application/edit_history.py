"""Branching document history with explicit capacity management, without Qt."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from functools import cached_property
from hashlib import sha256
from typing import Literal

from ...constants import CONSTANT

EditOperation = Literal["added", "deleted", "modified"]


@dataclass(frozen=True)
class EditSnapshot:
    state: bytes
    description: str = ""
    selection: tuple[int, ...] | None = None
    step_id: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    operation: EditOperation = "modified"

    @cached_property
    def digest(self) -> bytes:
        return sha256(self.state).digest()


@dataclass
class EditHistoryNode:
    snapshot: EditSnapshot
    parent_id: int | None = None
    children: list[int] = field(default_factory=list)
    preferred_child: int | None = None


class EditHistory:
    """Edits create children; visiting an old state never removes its future.

    Reaching the node limit never discards snapshots. The UI asks whether to
    clear the history or increase its capacity; clearing retains the current state.
    """

    def __init__(self, *, max_nodes: int | None = None) -> None:
        max_nodes = (
            max_nodes if max_nodes is not None else CONSTANT.UI.HISTORY.MAX_NODES
        )
        if max_nodes < 1:
            raise ValueError("History node limit must be positive.")
        self.max_nodes = max_nodes
        self._nodes: dict[int, EditHistoryNode] = {}
        self._root_id = 0
        self._current_id = 0
        self._next_step_id = 1
        self._merge_key: object | None = None
        self._saved_digest: bytes | None = None
        self._revision = 0

    @property
    def root(self) -> EditHistoryNode:
        return self._nodes[self._root_id]

    @property
    def current_node(self) -> EditHistoryNode:
        return self._nodes[self._current_id]

    @property
    def current(self) -> EditSnapshot:
        return self.current_node.snapshot

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def at_capacity(self) -> bool:
        return self.node_count >= self.max_nodes

    def set_max_nodes(self, max_nodes: int) -> None:
        """Set the capacity without deleting any history nodes."""
        if max_nodes < 1:
            raise ValueError("History node limit must be positive.")
        if self.max_nodes != max_nodes:
            self.max_nodes = max_nodes
            self._revision += 1

    def clear(self) -> None:
        """Retain only the current snapshot and preserve its saved-state marker."""
        self._nodes = {self._current_id: EditHistoryNode(self.current)}
        self._root_id = self._current_id
        self._revision += 1
        self.break_merge()

    @property
    def can_undo(self) -> bool:
        return self.current_node.parent_id is not None

    @property
    def can_redo(self) -> bool:
        return self.current_node.preferred_child is not None

    @property
    def undo_description(self) -> str:
        return self.current.description if self.can_undo else ""

    @property
    def redo_description(self) -> str:
        return self.target(1).description if self.can_redo else ""

    @property
    def is_modified(self) -> bool:
        return not self.is_saved(self.current)

    def node(self, step_id: int) -> EditHistoryNode:
        return self._nodes[step_id]

    def contains(self, step_id: int) -> bool:
        return step_id in self._nodes

    def reset(self, snapshot: EditSnapshot) -> None:
        snapshot = replace(snapshot, step_id=0)
        self._nodes = {0: EditHistoryNode(snapshot)}
        self._root_id = self._current_id = 0
        self._next_step_id = 1
        self._saved_digest = snapshot.digest
        self._revision += 1
        self.break_merge()

    def mark_saved(self) -> None:
        self._saved_digest = self.current.digest
        self._revision += 1
        self.break_merge()

    def is_saved(self, snapshot: EditSnapshot) -> bool:
        return snapshot.digest == self._saved_digest

    def break_merge(self) -> None:
        self._merge_key = None

    def remember_selection(self, selection: tuple[int, ...] | None) -> None:
        self.current_node.snapshot = replace(self.current, selection=selection)

    def commit(
        self, snapshot: EditSnapshot, *, merge_key: object | None = None
    ) -> bool:
        if snapshot.state == self.current.state:
            return False
        current = self.current_node
        if (
            merge_key is not None
            and merge_key == self._merge_key
            and self.can_undo
            and not current.children
        ):
            current.snapshot = replace(
                snapshot,
                step_id=self._current_id,
                created_at=self.current.created_at,
            )
            parent_id = current.parent_id
            assert parent_id is not None
            parent = self.node(parent_id)
            if snapshot.state == parent.snapshot.state:
                parent.children.remove(self._current_id)
                parent.preferred_child = (
                    parent.children[-1] if parent.children else None
                )
                del self._nodes[self._current_id]
                self._current_id = parent.snapshot.step_id
                merge_key = None
        else:
            snapshot = replace(snapshot, step_id=self._next_step_id)
            self._next_step_id += 1
            self._nodes[snapshot.step_id] = EditHistoryNode(snapshot, self._current_id)
            current.children.append(snapshot.step_id)
            current.preferred_child = snapshot.step_id
            self._current_id = snapshot.step_id
        self._merge_key = merge_key
        self._revision += 1
        return True

    def select(self, step_id: int) -> None:
        child = self.node(step_id)
        while child.parent_id is not None:
            parent = self.node(child.parent_id)
            parent.preferred_child = child.snapshot.step_id
            child = parent
        if self._current_id != step_id:
            self._current_id = step_id
            self._revision += 1
        self.break_merge()

    def target(self, offset: int) -> EditSnapshot:
        if offset == -1:
            step_id = self.current_node.parent_id
        elif offset == 1:
            step_id = self.current_node.preferred_child
        else:
            raise ValueError("History direction must be -1 or 1.")
        if step_id is None:
            raise IndexError("No document history in that direction.")
        return self.node(step_id).snapshot
