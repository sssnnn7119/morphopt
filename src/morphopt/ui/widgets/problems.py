"""Compact access to the diagnostics already owned by the model tree."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHeaderView, QStyle, QStyledItemDelegate, QToolButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..i18n import tr
from ..model.problem import Node
from ..theme import theme_manager


class _ProblemDelegate(QStyledItemDelegate):
    """Show complete explanations while keeping location paths compact."""

    def sizeHint(self, option, index) -> QSize:
        size = super().sizeHint(option, index)
        if index.column() == 1:
            width = max(1, self.parent().columnWidth(1))
            wrapped = option.fontMetrics.boundingRect(
                QRect(0, 0, width, 0), Qt.TextFlag.TextWordWrap, index.data(),
            )
            size.setHeight(max(size.height(), wrapped.height()))
        return size


class ProblemsButton(QToolButton):
    nodeRequested = Signal(object)

    def __init__(
        self,
        diagnostics: Callable[[], tuple[tuple[Node, str, str], ...]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._diagnostics = diagnostics
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning))
        self.clicked.connect(self._show_problems)
        self.apply_language()

    def refresh(self, *_args: object) -> None:
        count = len(self._diagnostics())
        self.setText(tr("ui.problems.count", count=count))
        self.setEnabled(bool(count))

    def apply_language(self) -> None:
        self.setToolTip(tr("ui.problems.open_hint"))
        self.refresh()

    def _show_problems(self) -> None:
        entries = self._diagnostics()
        if not entries:
            return
        dialog = QDialog(self)
        dialog.setObjectName("modelProblemsDialog")
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowTitle(tr("ui.problems.title", count=len(entries)))
        dialog.resize(*theme_manager.palette.layout.workbench.problems_dialog_size)
        layout = QVBoxLayout(dialog)
        tree = QTreeWidget()
        tree.setProperty("problemList", True)
        tree.setAlternatingRowColors(True)
        tree.setRootIsDecorated(False)
        tree.setWordWrap(True)
        tree.setItemDelegate(_ProblemDelegate(tree))
        tree.setColumnCount(2)
        tree.setHeaderLabels([tr("ui.problems.location"), tr("ui.problems.message")])
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        tree.setColumnWidth(0, theme_manager.palette.layout.workbench.left_minimum_width)
        for node, location, message in entries:
            item = QTreeWidgetItem([location, message])
            item.setData(0, Qt.ItemDataRole.UserRole, node)
            item.setToolTip(0, location)
            item.setToolTip(1, message)
            tree.addTopLevelItem(item)

        def locate(item: QTreeWidgetItem, _column: int) -> None:
            node = item.data(0, Qt.ItemDataRole.UserRole)
            dialog.accept()
            self.nodeRequested.emit(node)

        tree.itemClicked.connect(locate)
        layout.addWidget(tree)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("ui.common.close"))
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.open()
