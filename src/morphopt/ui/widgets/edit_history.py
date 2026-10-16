"""Branching operation history and navigation controls for the left pane."""
from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, QTimer, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHeaderView, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ...constants import CONSTANT
from ..application.edit_history import EditHistory, EditHistoryNode
from ..i18n import tr
from ..presentation.edit_history import edit_description
from .collection_controls import ActionButton


class EditHistoryPanel(QWidget):
    jumpRequested = Signal(int)
    undoRequested = Signal()
    redoRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._version: tuple[int, int] | None = None
        self._items: dict[int, QTreeWidgetItem] = {}
        self._current_id: int | None = None
        self._request_id = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        self.title = QLabel(self)
        self.title.setProperty("textRole", "sectionHeading")
        header.addWidget(self.title)
        header.addStretch(1)
        self.undo_button = ActionButton("", self.undoRequested.emit, parent=self)
        self.redo_button = ActionButton("", self.redoRequested.emit, parent=self)
        for button in (self.undo_button, self.redo_button):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            header.addWidget(button)
        layout.addLayout(header)
        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(CONSTANT.UI.LAYOUT.HISTORY.TREE_INDENTATION)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemDoubleClicked.connect(self._request)
        layout.addWidget(self.tree)
        self.apply_language()

    def apply_language(self) -> None:
        self.title.setText(tr("ui.history.panel"))
        self.tree.setToolTip(tr("ui.history.tree_hint"))
        self._version = None

    def set_history(self, history: EditHistory) -> None:
        version = (id(history), history.revision)
        if self._version == version:
            return
        self._version = version
        expanded = {step_id: item.isExpanded() for step_id, item in self._items.items()}
        scroll = self.tree.verticalScrollBar().value()
        current_id = history.current.step_id
        self.title.setToolTip(tr("ui.history.node_count", count=history.node_count, limit=history.max_nodes))
        with QSignalBlocker(self.tree):
            self.tree.clear()
            self._items.clear()

            def build(node: EditHistoryNode) -> QTreeWidgetItem:
                snapshot = node.snapshot
                description = (
                    tr("ui.history.initial")
                    if snapshot.step_id == 0
                    else edit_description(snapshot)
                )
                markers = []
                if snapshot.step_id == current_id:
                    markers.append(tr("ui.history.current"))
                if history.is_saved(snapshot):
                    markers.append(tr("ui.history.saved"))
                text = tr("ui.history.tree_entry", step=snapshot.step_id, description=description)
                if markers:
                    text = tr("ui.history.tree_entry_status", entry=text, status=" / ".join(markers))
                item = QTreeWidgetItem([text])
                item.setData(0, Qt.ItemDataRole.UserRole, snapshot.step_id)
                item.setToolTip(0, tr(
                    "ui.history.tree_entry_tooltip", description=description,
                    time=snapshot.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                ))
                if snapshot.step_id == current_id:
                    font = item.font(0)
                    font.setBold(True)
                    item.setFont(0, font)
                    item.setForeground(0, QColor("#8ac5ff"))
                self._items[snapshot.step_id] = item
                for child_id in node.children:
                    item.addChild(build(history.node(child_id)))
                return item

            self.tree.addTopLevelItem(build(history.root))
            for step_id, item in self._items.items():
                item.setExpanded(expanded.get(step_id, True))
            current = self._items[current_id]
            self.tree.setCurrentItem(current)
            ancestor = current.parent()
            while ancestor is not None:
                ancestor.setExpanded(True)
                ancestor = ancestor.parent()
        if current_id != self._current_id:
            self.tree.scrollToItem(current)
        else:
            self.tree.verticalScrollBar().setValue(scroll)
        self._current_id = current_id

    def _request(self, item: QTreeWidgetItem, _column: int) -> None:
        step_id = item.data(0, Qt.ItemDataRole.UserRole)
        self._request_id += 1
        request_id, version = self._request_id, self._version

        def navigate() -> None:
            if request_id == self._request_id and version == self._version:
                self.jumpRequested.emit(step_id)

        QTimer.singleShot(0, self, navigate)
