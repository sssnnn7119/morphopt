"""Theme registration, persistence, and application-wide change events."""

import weakref
from collections.abc import Callable

from .palette import ThemePalette
from .stylesheet import theme_stylesheet


class ThemeManager:
    """Own registered themes and notify components when the active theme changes."""

    def __init__(
        self,
        themes: dict[str, ThemePalette],
        *,
        default: str = "dark",
    ) -> None:
        if default not in themes:
            raise ValueError(f"Default theme {default!r} is not registered.")
        self._themes = dict(themes)
        self._default = default
        self._name = default
        self._listeners: list[weakref.WeakMethod | weakref.ReferenceType] = []
        self._catalog_listeners: list[weakref.WeakMethod | weakref.ReferenceType] = []

    @property
    def name(self) -> str:
        """Name of the currently selected theme."""
        return self._name

    @property
    def names(self) -> tuple[str, ...]:
        """Registered theme names in selector order."""
        return tuple(self._themes)

    @property
    def palette(self) -> ThemePalette:
        """Complete immutable visual configuration for the active theme."""
        return self._themes[self._name]

    def register_theme(self, name: str, palette: ThemePalette) -> None:
        """Register an additional theme before or during application use."""
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Theme name cannot be empty.")
        if normalized_name in self._themes:
            raise ValueError(f"Theme {normalized_name!r} is already registered.")
        if not isinstance(palette, ThemePalette):
            raise TypeError("palette must be a ThemePalette instance.")
        self._themes[normalized_name] = palette
        self._notify_catalog()

    def restore(self, app) -> None:
        """Apply the last selected theme before constructing the main window."""
        from PySide6.QtCore import QSettings

        name = QSettings("MorphOptUI", "ui").value("theme", self._default, str)
        self.apply(app, name, persist=False)

    def set_theme(self, name: str) -> None:
        """Apply a registered theme to the live application and persist the choice."""
        if name not in self._themes:
            raise ValueError(f"Theme {name!r} is not registered.")
        self.apply(None, name, persist=True)

    def apply(self, app=None, name: str | None = None, *, persist: bool) -> None:
        """Apply a registered theme, falling back only for stale saved settings."""
        if name not in self._themes:
            name = self._default
        changed = name != self._name
        self._name = name
        if app is None:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(theme_stylesheet(self.palette))
        if persist:
            from PySide6.QtCore import QSettings

            QSettings("MorphOptUI", "ui").setValue("theme", name)
        if changed:
            self._notify()

    def subscribe(self, callback: Callable[[str], None]) -> Callable[[], None]:
        """Subscribe to active-theme changes; return a function to unsubscribe."""
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

    def subscribe_catalog(
        self,
        callback: Callable[[tuple[str, ...]], None],
    ) -> Callable[[], None]:
        """Subscribe to registration changes in the available-theme catalog."""
        reference = (
            weakref.WeakMethod(callback)
            if getattr(callback, "__self__", None) is not None
            else weakref.ref(callback)
        )
        self._catalog_listeners.append(reference)

        def unsubscribe() -> None:
            if reference in self._catalog_listeners:
                self._catalog_listeners.remove(reference)

        return unsubscribe

    def _notify(self) -> None:
        live = []
        for reference in self._listeners:
            callback = reference()
            if callback is not None:
                live.append(reference)
                callback(self._name)
        self._listeners = live

    def _notify_catalog(self) -> None:
        live = []
        for reference in self._catalog_listeners:
            callback = reference()
            if callback is not None:
                live.append(reference)
                callback(self.names)
        self._catalog_listeners = live
