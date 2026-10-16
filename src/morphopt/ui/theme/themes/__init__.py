"""Built-in themes. Add a palette module and register it here to extend the UI."""

from .dark import DARK
from .light import LIGHT

BUILTIN_THEMES = {
    "dark": DARK,
    "light": LIGHT,
}

__all__ = ["BUILTIN_THEMES", "DARK", "LIGHT"]
