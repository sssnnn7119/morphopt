"""Compact selector for the application color theme."""

from PySide6.QtWidgets import QComboBox

from ..i18n import localization, tr
from ..theme import theme_manager


class ThemeSelector(QComboBox):
    """Select and persist a registered application theme."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(theme_manager.palette.layout.theme_selector_width)
        self.currentIndexChanged.connect(self._apply)
        self._unsubscribe_theme = theme_manager.subscribe(self._theme_changed)
        self._unsubscribe_catalog = theme_manager.subscribe_catalog(self._catalog_changed)
        self._unsubscribe_locale = localization.subscribe(self._language_changed)
        self.destroyed.connect(lambda *_args: self._unsubscribe_theme())
        self.destroyed.connect(lambda *_args: self._unsubscribe_catalog())
        self.destroyed.connect(lambda *_args: self._unsubscribe_locale())
        self._language_changed(localization.locale)
        self._theme_changed(theme_manager.name)

    def _language_changed(self, _locale: str) -> None:
        selected = theme_manager.name
        self.blockSignals(True)
        self.clear()
        for name in theme_manager.names:
            self.addItem(tr(f"ui.theme.{name}"), name)
        self.setToolTip(tr("ui.theme.appearance"))
        self.setCurrentIndex(max(0, self.findData(selected)))
        self.blockSignals(False)

    def _theme_changed(self, name: str) -> None:
        self.blockSignals(True)
        self.setCurrentIndex(max(0, self.findData(name)))
        self.blockSignals(False)

    def _catalog_changed(self, _names: tuple[str, ...]) -> None:
        self._language_changed(localization.locale)

    def _apply(self, _index: int) -> None:
        name = self.currentData()
        if name:
            theme_manager.set_theme(name)
