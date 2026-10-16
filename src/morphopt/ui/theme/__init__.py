"""Extensible application theme package.

Add a palette under :mod:`morphopt.ui.theme.themes`, register it in that package's
``BUILTIN_THEMES``, and add its translated label to the locale resources.
"""

from .manager import ThemeManager
from .palette import (
    DEFAULT_LAYOUT_STYLE,
    ChartStyle,
    CodeEditorPalette,
    HistoryLayout,
    LayoutStyle,
    ObserverLayout,
    QuickstartLayout,
    QuickstartPreviewStyle,
    ThemePalette,
    UpdaterEditorLayout,
    ViewerGeometryStyle,
    ViewerLoadsStyle,
    ViewerRenderStyle,
    ViewerStyle,
    WidgetLayout,
    WorkbenchLayout,
)
from .themes import BUILTIN_THEMES

theme_manager = ThemeManager(BUILTIN_THEMES)


def register_theme(name: str, palette: ThemePalette) -> None:
    """Register a theme for the current application session."""
    theme_manager.register_theme(name, palette)


__all__ = [
    "DEFAULT_LAYOUT_STYLE",
    "ChartStyle",
    "CodeEditorPalette",
    "HistoryLayout",
    "LayoutStyle",
    "ObserverLayout",
    "QuickstartLayout",
    "QuickstartPreviewStyle",
    "ThemeManager",
    "ThemePalette",
    "UpdaterEditorLayout",
    "ViewerGeometryStyle",
    "ViewerLoadsStyle",
    "ViewerRenderStyle",
    "ViewerStyle",
    "WidgetLayout",
    "WorkbenchLayout",
    "register_theme",
    "theme_manager",
]
