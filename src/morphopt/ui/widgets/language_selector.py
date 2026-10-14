"""Qt selector and persistence adapter for the pure localization service."""
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QComboBox
from ..i18n import LocalizationManager, SUPPORTED_LOCALES, localization

_SETTINGS = QSettings("MorphOptUI", "ui")


def restore_locale() -> None:
    """Restore the saved locale at application startup, before building views."""
    localization.set_locale(_SETTINGS.value("language", "zh-CN", str))


class LanguageSelector(QComboBox):
    """A language selector backed by the application localization manager."""

    def __init__(self, parent=None):
        super().__init__(parent)
        for code, label in SUPPORTED_LOCALES.items():
            self.addItem(label, code)
        self.setFixedWidth(110)
        self.set_locale(localization.locale)
        self._unsubscribe_locale = localization.subscribe(self._locale_changed)
        unsubscribe = self._unsubscribe_locale
        self.destroyed.connect(lambda *_args: unsubscribe())
        self.currentIndexChanged.connect(self._apply)

    def _apply(self) -> None:
        code = self.currentData()
        if code:
            localization.set_locale(code)

    def set_locale(self, locale: str) -> None:
        idx = self.findData(LocalizationManager._normalize_locale(locale))
        if idx >= 0 and idx != self.currentIndex():
            self.setCurrentIndex(idx)

    def _locale_changed(self, locale: str) -> None:
        _SETTINGS.setValue("language", locale)
        self.blockSignals(True)
        self.set_locale(locale)
        self.blockSignals(False)
