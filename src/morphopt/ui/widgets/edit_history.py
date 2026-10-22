"""Branching operation history and navigation controls for the left pane."""

from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import QModelIndex, QSignalBlocker, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from ..application.edit_history import EditHistory
from ..i18n import tr
from ..presentation.edit_history import edit_description
from ..theme import theme_manager
from .collection_controls import ActionButton

_STEP_ID_ROLE = Qt.ItemDataRole.UserRole
_GRAPH_LANE_ROLE = Qt.ItemDataRole.UserRole + 1
_GraphEdge = tuple[int, int, int, int]
_GraphSegment = tuple[int, int, bool, bool]


class _HistoryGraphList(QListWidget):
    """Flat history rows with a fixed-width Git-style graph gutter."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.graph_width = 0
        self._segments_by_row: dict[int, list[_GraphSegment]] = {}

    def set_graph(self, max_lane: int, edges: list[_GraphEdge]) -> None:
        graph = theme_manager.palette.layout.history
        self.graph_width = (
            graph.graph_left_margin
            + max_lane * graph.graph_lane_spacing
            + graph.graph_lane_spacing
            + graph.graph_right_margin
        )
        segments_by_row: dict[int, list[_GraphSegment]] = defaultdict(list)
        for parent_row, child_row, parent_lane, child_lane in edges:
            for row in range(parent_row, child_row + 1):
                segments_by_row[row].append(
                    (
                        parent_lane,
                        child_lane,
                        row == parent_row,
                        row == child_row,
                    )
                )
        self._segments_by_row = dict(segments_by_row)
        self.viewport().update()


class _HistoryGraphDelegate(QStyledItemDelegate):
    """Paints graph lanes separately from the aligned history descriptions."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        view_option = QStyleOptionViewItem(option)
        self.initStyleOption(view_option, index)
        text = view_option.text
        view_option.text = ""
        style = view_option.widget.style() if view_option.widget is not None else None

        painter.save()
        if style is not None:
            style.drawControl(
                QStyle.ControlElement.CE_ItemViewItem,
                view_option,
                painter,
                view_option.widget,
            )

        graph_list = self.parent()
        if not isinstance(graph_list, _HistoryGraphList):
            painter.restore()
            return

        graph = theme_manager.palette.layout.history
        row = index.row()
        top = option.rect.top()
        bottom = option.rect.bottom()
        middle = (top + bottom) // 2

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for (
            parent_lane,
            child_lane,
            is_parent_row,
            is_child_row,
        ) in graph_list._segments_by_row.get(row, ()):
            color = self._lane_color(child_lane)
            pen = QPen(color, graph.graph_line_width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            parent_x = self._lane_x(option.rect.left(), parent_lane)
            child_x = self._lane_x(option.rect.left(), child_lane)
            if is_parent_row:
                painter.drawLine(int(child_x), middle, int(child_x), bottom)
                painter.drawLine(int(parent_x), middle, int(child_x), middle)
            elif is_child_row:
                painter.drawLine(int(child_x), top, int(child_x), middle)
            else:
                painter.drawLine(int(child_x), top, int(child_x), bottom)

        lane = int(index.data(_GRAPH_LANE_ROLE) or 0)
        node_x = self._lane_x(option.rect.left(), lane)
        current = view_option.font.bold()
        radius = graph.graph_current_node_radius if current else graph.graph_node_radius
        node_color = self._lane_color(lane)
        painter.setPen(QPen(node_color, graph.graph_line_width))
        painter.setBrush(node_color)
        painter.drawEllipse(
            int(node_x - radius),
            int(middle - radius),
            radius * 2,
            radius * 2,
        )

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        text_color_role = (
            QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text
        )
        painter.setPen(view_option.palette.color(text_color_role))
        painter.setFont(view_option.font)
        text_rect = option.rect.adjusted(
            graph_list.graph_width + graph.graph_text_gap,
            0,
            -graph.graph_text_gap,
            0,
        )
        label = QFontMetrics(view_option.font).elidedText(
            text,
            Qt.TextElideMode.ElideRight,
            max(0, text_rect.width()),
        )
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            label,
        )
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        size = super().sizeHint(option, index)
        size.setHeight(theme_manager.palette.layout.history.row_height)
        return size

    @staticmethod
    def _lane_x(left: int, lane: int) -> int:
        graph = theme_manager.palette.layout.history
        return left + graph.graph_left_margin + lane * graph.graph_lane_spacing

    @staticmethod
    def _lane_color(lane: int) -> QColor:
        colors = theme_manager.palette.history_branch_colors
        return QColor(colors[lane % len(colors)])


class EditHistoryPanel(QWidget):
    jumpRequested = Signal(int)
    undoRequested = Signal()
    redoRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._version: tuple[int, int] | None = None
        self._items: dict[int, QListWidgetItem] = {}
        self._current_id: int | None = None
        self._request_id = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
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

        self.history_list = _HistoryGraphList(self)
        self.history_list.setItemDelegate(_HistoryGraphDelegate(self.history_list))
        self.history_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.history_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.history_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.history_list.setUniformItemSizes(True)
        self.history_list.itemDoubleClicked.connect(self._request)
        layout.addWidget(self.history_list)
        self.apply_language()

    def apply_language(self) -> None:
        self.title.setText(tr("ui.history.panel"))
        self.history_list.setToolTip(tr("ui.history.tree_hint"))
        self._version = None

    def apply_theme(self) -> None:
        current = self.history_list.currentItem()
        if current is not None:
            current.setForeground(QColor(theme_manager.palette.accent_hover))

    def set_history(self, history: EditHistory) -> None:
        version = (id(history), history.revision)
        if self._version == version:
            return
        self._version = version
        scroll = self.history_list.verticalScrollBar().value()
        current_id = history.current.step_id
        self.title.setToolTip(
            tr(
                "ui.history.node_count",
                count=history.node_count,
                limit=history.max_nodes,
            )
        )

        rows, lanes = self._layout_nodes(history, current_id)
        row_by_id = {step_id: row for row, (step_id, _lane) in enumerate(rows)}
        edges: list[_GraphEdge] = []
        for step_id, _lane in rows:
            parent_id = history.node(step_id).parent_id
            if parent_id is not None:
                edges.append(
                    (
                        row_by_id[parent_id],
                        row_by_id[step_id],
                        lanes[parent_id],
                        lanes[step_id],
                    )
                )

        max_lane = max(lanes.values(), default=0)
        with QSignalBlocker(self.history_list):
            self.history_list.clear()
            self._items.clear()
            for step_id, lane in rows:
                snapshot = history.node(step_id).snapshot
                description = (
                    tr("ui.history.initial")
                    if step_id == 0
                    else edit_description(snapshot)
                )
                markers = []
                if step_id == current_id:
                    markers.append(tr("ui.history.current"))
                if history.is_saved(snapshot):
                    markers.append(tr("ui.history.saved"))
                text = tr(
                    "ui.history.tree_entry",
                    step=step_id,
                    description=description,
                )
                if markers:
                    text = tr(
                        "ui.history.tree_entry_status",
                        entry=text,
                        status=" / ".join(markers),
                    )
                item = QListWidgetItem(text)
                item.setData(_STEP_ID_ROLE, step_id)
                item.setData(_GRAPH_LANE_ROLE, lane)
                item.setToolTip(
                    tr(
                        "ui.history.tree_entry_tooltip",
                        description=description,
                        time=snapshot.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    )
                )
                if step_id == current_id:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(QColor(theme_manager.palette.accent_hover))
                self.history_list.addItem(item)
                self._items[step_id] = item

            self.history_list.set_graph(max_lane, edges)
            current = self._items[current_id]
            self.history_list.setCurrentItem(current)

        if current_id != self._current_id:
            self.history_list.scrollToItem(current)
        else:
            self.history_list.verticalScrollBar().setValue(scroll)
        self._current_id = current_id

    @staticmethod
    def _layout_nodes(
        history: EditHistory, current_id: int
    ) -> tuple[list[tuple[int, int]], dict[int, int]]:
        """Put the current path in lane zero and each side branch to its right."""
        main_path: list[int] = []
        step_id = current_id
        while True:
            main_path.append(step_id)
            parent_id = history.node(step_id).parent_id
            if parent_id is None:
                break
            step_id = parent_id
        main_path.reverse()
        next_on_main = dict(zip(main_path, main_path[1:]))
        rows: list[tuple[int, int]] = []
        lanes: dict[int, int] = {}

        pending = [(main_path[0], 0, True)]
        while pending:
            step, lane, on_main = pending.pop()
            rows.append((step, lane))
            lanes[step] = lane
            node = history.node(step)
            primary_child = next_on_main.get(step) if on_main else node.preferred_child
            if not on_main and primary_child not in node.children:
                primary_child = node.children[-1] if node.children else None
            branches = [child for child in node.children if child != primary_child]
            if primary_child is not None:
                pending.append((primary_child, lane, on_main))
            for offset, child in reversed(list(enumerate(branches, start=1))):
                pending.append((child, lane + offset, False))

        if len(rows) != history.node_count or len(lanes) != history.node_count:
            raise RuntimeError(
                "History graph layout did not include every node exactly once."
            )
        return rows, lanes

    def _request(self, item: QListWidgetItem) -> None:
        step_id = item.data(_STEP_ID_ROLE)
        self._request_id += 1
        request_id, version = self._request_id, self._version

        def navigate() -> None:
            if request_id == self._request_id and version == self._version:
                self.jumpRequested.emit(step_id)

        QTimer.singleShot(0, self, navigate)
