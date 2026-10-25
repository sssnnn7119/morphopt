"""Named surface and node sets belonging to one Part."""

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from ..application.part_sets import PartSets
from ..i18n import tr


class PartSetList(QTreeWidget):
    selected = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        self.setMaximumHeight(260)
        self.setHeaderLabel(tr("ui.part_sets.click_to_highlight"))
        self.currentItemChanged.connect(self._select)
        self.itemPressed.connect(self._reselect)
        self._sets = None

    def _select(self, item, _previous=None):
        value = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        self.selected.emit(*(value or ("", "")))

    def _reselect(self, item, _column):
        if item is self.currentItem():
            self._select(item)

    def set_sets(self, sets: PartSets) -> None:
        self.setHeaderLabel(tr("ui.part_sets.click_to_highlight"))
        if sets == self._sets:
            return
        self._sets = sets
        current = self.currentItem()
        previous = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        selected = None
        with QSignalBlocker(self):
            self.clear()
            for kind in ("surfaces", "nodes"):
                names = tuple(dict.fromkeys(getattr(sets, kind)))
                group = QTreeWidgetItem([tr(f"ui.part_sets.{kind}", count=len(names))])
                self.addTopLevelItem(group)
                for name in names:
                    item = QTreeWidgetItem([name])
                    item.setData(0, Qt.ItemDataRole.UserRole, (kind, name))
                    group.addChild(item)
                    if previous == (kind, name):
                        selected = item
                group.setExpanded(True)
            self.setCurrentItem(selected)
        if previous and selected is None:
            self.selected.emit("", "")

    def set_error(self, error: Exception) -> None:
        self._sets = None
        with QSignalBlocker(self):
            self.clear()
            item = QTreeWidgetItem([tr("ui.part_sets.unavailable")])
            item.setToolTip(0, str(error))
            self.addTopLevelItem(item)
