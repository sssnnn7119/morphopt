"""Load and render the modular Qt stylesheets used by every theme."""

from dataclasses import fields
from importlib.resources import files
import re

from .palette import ThemePalette
from .styles import STYLESHEET_FILES


_TOKEN_PATTERN = re.compile(r"@([a-z_]+)@")


def theme_stylesheet(palette: ThemePalette) -> str:
    """Assemble QSS fragments and replace them with active theme tokens."""
    package = files("morphopt.ui.theme.styles")
    template = "\n\n".join(
        package.joinpath(filename).read_text(encoding="utf-8")
        for filename in STYLESHEET_FILES
    )
    tokens = {
        field.name: getattr(palette, field.name)
        for field in fields(palette)
        if isinstance(getattr(palette, field.name), (str, int, float))
    }

    def replace_token(match: re.Match[str]) -> str:
        name = match.group(1)
        try:
            return str(tokens[name])
        except KeyError as error:
            raise ValueError(f"Unknown theme stylesheet token: @{name}@") from error

    return _TOKEN_PATTERN.sub(replace_token, template)
