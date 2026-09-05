"""Lightweight bilingual (中文 / English) support for the MorphOpt UI.

Usage
-----
* ``T("中文", "English")`` returns the text for the current language.
* ``LanguageSelector`` is a small combo box; on change it switches the
  language and calls the given callback so the UI can re-apply texts.
* The language is remembered between sessions via ``QSettings``.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QComboBox

_ZH = "zh"
_EN = "en"
_APP = "MorphOptUI"


def _settings() -> QSettings:
    return QSettings(_APP, "ui")


def lang() -> str:
    return _settings().value("language", _ZH, str)


def set_lang(code: str) -> None:
    code = _EN if code == _EN else _ZH
    _settings().setValue("language", code)


def is_en() -> bool:
    return lang() == _EN


def T(zh: str, en: str) -> str:
    """Pick the Chinese or English variant for the current language."""
    return pick(zh, en)


def pick(primary: str, secondary: str | None = None) -> str:
    """Select a display string by the current language.

    ``primary``  is the Chinese master text (or a language-neutral English term
    when the entry is not localized); ``secondary`` is the English variant when
    it differs from ``primary``.  Use this in place, next to the data it
    describes (no external translation table).
    """
    return secondary if (is_en() and secondary) else primary


class LanguageSelector(QComboBox):
    """A 中文 / English switch; emits ``languageChanged`` after applying."""

    def __init__(self, on_change=None, parent=None):
        super().__init__(parent)
        self.addItem("中文", _ZH)
        self.addItem("English", _EN)
        self.setFixedWidth(110)
        self._on_change = on_change
        self.set_lang(lang())
        self.currentIndexChanged.connect(self._apply)

    def _apply(self) -> None:
        set_lang(self.currentData())
        if self._on_change is not None:
            self._on_change()

    def set_lang(self, code: str) -> None:
        idx = self.findData(code)
        if idx >= 0 and idx != self.currentIndex():
            self.setCurrentIndex(idx)
