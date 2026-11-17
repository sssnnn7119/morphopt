"""Shared headers and item actions for collection editors."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QWidget,
)

from ..i18n import tr
from ..theme import theme_manager


def set_card_selected(card: QGroupBox, selected: bool) -> None:
    """Update only this card's selection border, without restyling its children.

    Args:
        card (QGroupBox): Interface-card widget whose state or geometry is being updated.
        selected (bool): Selection retained or applied while the view is rebuilt.
    """
    if card.property("collectionSelected") != selected:
        card.setProperty("collectionSelected", selected)
        card.style().unpolish(card)
        card.style().polish(card)
        card.update()


class ActionButton(QToolButton):
    """Compact editor action; colors and states come from the application theme."""

    def __init__(
        self,
        text: str,
        callback: Callable[[], object] | None = None,
        *,
        danger: bool = False,
        tooltip: str = "",
        parent: QWidget | None = None,
    ) -> None:
        """Initialize ActionButton and its configuration state.

        Args:
            text (str): Text displayed, parsed, or inserted by this operation.
            callback (Callable[[], object] | None): Callback invoked with the operation's documented
                result or change event.
            danger (bool): Style the action as destructive when True.
            tooltip (str): Explanatory text displayed when the pointer rests on the control.
            parent (QWidget | None): Parent Qt widget; None creates a top-level widget.
        """
        super().__init__(parent)
        self.setText(text)
        self.setToolTip(tooltip or text)
        self.setProperty("actionRole", "danger" if danger else "secondary")
        self.setFixedHeight(theme_manager.palette.layout.widgets.action_button_height)
        if callback is not None:
            self.clicked.connect(lambda _checked=False: callback())


class AddButton(ActionButton):
    """A single add action, or a menu when several item types are available."""

    def __init__(
        self,
        callback: Callable[[], object] | None = None,
        *,
        menu: QMenu | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize AddButton and its configuration state.

        Args:
            callback (Callable[[], object] | None): Callback invoked with the operation's documented
                result or change event.
            menu (QMenu | None): Qt menu populated with the applicable actions.
            parent (QWidget | None): Parent Qt widget; None creates a top-level widget.
        """
        super().__init__(tr("ui.common.add"), callback, parent=parent)
        if menu is not None:
            self.setMenu(menu)
            self.setProperty("menuButton", True)
            self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)


class CollectionHeader(QWidget):
    """Collection title on the left, add and optional item actions on the right."""

    def __init__(
        self,
        title: str,
        add: Callable[[], object] | None = None,
        *,
        menu: QMenu | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize CollectionHeader and its configuration state.

        Args:
            title (str): User-facing title of the view, section, or action.
            add (Callable[[], object] | None): Callback or flag enabling construction of a
                collection item.
            menu (QMenu | None): Qt menu populated with the applicable actions.
            parent (QWidget | None): Parent Qt widget; None creates a top-level widget.
        """
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        row.setSpacing(theme_manager.palette.layout.widgets.action_grid_spacing)
        self.title = QLabel(title)
        self.title.setProperty("textRole", "sectionHeading")
        row.addWidget(self.title)
        row.addStretch(1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(
            theme_manager.palette.layout.widgets.action_grid_spacing
        )
        row.addLayout(self.actions)
        self.add_button = AddButton(add, menu=menu)
        row.addWidget(self.add_button)


class ItemActions(QWidget):
    """Right-aligned move and delete controls shared by cards and row editors."""

    def __init__(
        self,
        index: int,
        count: int,
        remove: Callable[[], object],
        move: Callable[[int], object] | None = None,
        *,
        allow_remove: bool = True,
        remove_tooltip: str = "",
        parent: QWidget | None = None,
    ) -> None:
        """Initialize ItemActions and its configuration state.

        Args:
            index (int): Zero-based position within the relevant collection.
            count (int): Number of repeated objects or records requested.
            remove (Callable[[], object]): Callback deleting the selected collection item.
            move (Callable[[int], object] | None): Callback changing the item's position in its
                owning collection.
            allow_remove (bool): Expose the remove action for the selected entry when True.
            remove_tooltip (str): Tooltip explaining the remove action and any dependent deletion.
            parent (QWidget | None): Parent Qt widget; None creates a top-level widget.
        """
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        row.setSpacing(theme_manager.palette.layout.widgets.action_grid_spacing)
        row.addStretch(1)
        self.up_button = (
            ActionButton("↑", partial(move, -1), tooltip=tr("ui.common.move_up"))
            if move is not None
            else None
        )
        self.down_button = (
            ActionButton("↓", partial(move, 1), tooltip=tr("ui.common.move_down"))
            if move is not None
            else None
        )
        for button in (self.up_button, self.down_button):
            if button is not None:
                button.setFixedWidth(
                    theme_manager.palette.layout.widgets.item_action_button_width
                )
                row.addWidget(button)
        self.delete_button = ActionButton(
            tr("ui.common.delete"),
            remove,
            danger=True,
            tooltip=remove_tooltip,
        )
        row.addWidget(self.delete_button)
        self.set_position(index, count, allow_remove=allow_remove)

    def set_position(
        self, index: int, count: int, *, allow_remove: bool = True
    ) -> None:
        """Set position.

        Args:
            index (int): Zero-based position within the relevant collection.
            count (int): Number of repeated objects or records requested.
            allow_remove (bool): Expose the remove action for the selected entry when True.
        """
        if self.up_button is not None:
            self.up_button.setEnabled(0 < index < count)
        if self.down_button is not None:
            self.down_button.setEnabled(0 <= index < count - 1)
        self.delete_button.setEnabled(allow_remove and 0 <= index < count)
