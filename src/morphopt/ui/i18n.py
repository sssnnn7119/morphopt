"""Key based localization for the MorphOpt UI."""

from __future__ import annotations

import json
import logging
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_LOGGER = logging.getLogger(__name__)
SUPPORTED_LOCALES = ("zh-CN", "en-US")
_FALLBACK_LOCALE = "en-US"
_RESOURCE_DIR = Path(__file__).with_name("locales")


class LocalizationManager:
    """Load keyed string tables, format messages, and notify locale listeners."""

    def __init__(self, locale: str = "zh-CN", fallback_locale: str = _FALLBACK_LOCALE):
        self._locale = self._normalize_locale(locale)
        self.fallback_locale = self._normalize_locale(fallback_locale)
        self._tables: dict[str, dict[str, str]] = {}
        self._listeners: list[weakref.WeakMethod | weakref.ReferenceType] = []
        self._missing_keys: set[str] = set()

    @property
    def locale(self) -> str:
        return self._locale

    @staticmethod
    def _normalize_locale(locale: str) -> str:
        aliases = {"zh": "zh-CN", "en": "en-US"}
        normalized = aliases.get(locale, locale)
        return normalized if normalized in SUPPORTED_LOCALES else "zh-CN"

    def load_locale(self, locale: str) -> dict[str, str]:
        """Load a locale file once and return its string table."""
        locale = self._normalize_locale(locale)
        if locale not in self._tables:
            path = _RESOURCE_DIR / f"{locale}.json"
            with path.open("r", encoding="utf-8") as resource:
                table = json.load(resource)
            if not isinstance(table, dict) or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in table.items()
            ):
                raise ValueError(f"Invalid localization table: {path}")
            self._tables[locale] = table
        return self._tables[locale]

    def set_locale(self, locale: str) -> None:
        locale = self._normalize_locale(locale)
        if locale == self._locale:
            return
        self.load_locale(locale)
        self._locale = locale
        self._notify_locale_changed()

    def subscribe(self, callback: Callable[[str], None]) -> Callable[[], None]:
        """Subscribe to locale changes and return a function that unsubscribes."""
        reference = (
            weakref.WeakMethod(callback)
            if getattr(callback, "__self__", None) is not None
            else weakref.ref(callback)
        )
        self._listeners.append(reference)

        def unsubscribe() -> None:
            if reference in self._listeners:
                self._listeners.remove(reference)

        return unsubscribe

    def _notify_locale_changed(self) -> None:
        live: list[weakref.WeakMethod | weakref.ReferenceType] = []
        for reference in self._listeners:
            callback = reference()
            if callback is None:
                continue
            live.append(reference)
            callback(self._locale)
        self._listeners = live

    def tr(self, key: str, **values: object) -> str:
        """Resolve ``key`` in the active table, then the fallback table."""
        text = self.load_locale(self._locale).get(key)
        if text is None:
            text = self.load_locale(self.fallback_locale).get(key)
        if text is None:
            if key not in self._missing_keys:
                _LOGGER.warning("Missing localization key: %s", key)
                self._missing_keys.add(key)
            return key
        if not values:
            return text
        try:
            return text.format(**values)
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            _LOGGER.error("Cannot format localization key %s: %s", key, exc)
            return text


localization = LocalizationManager()


@dataclass(frozen=True)
class LocalizedMessage:
    """Keep validation messages as keys until a view requests their text."""

    key: str
    values: dict[str, object]

    def __str__(self) -> str:
        return localization.tr(self.key, **self.values)

    def __repr__(self) -> str:
        # KeyError renders its single argument with repr rather than str.
        return repr(str(self))


def localized_message(key: str, **values: object) -> LocalizedMessage:
    return LocalizedMessage(key, values)


def tr(key: str, **values: object) -> str:
    """Translate a stable message key and interpolate named values."""
    return localization.tr(key, **values)


def set_locale(locale: str) -> None:
    """Set the active locale and notify subscribed UI components."""
    localization.set_locale(locale)
