"""Optional Qt user interface entry points."""

from __future__ import annotations

from typing import Sequence


def run_app(argv: Sequence[str] | None = None) -> int:
    """Launch the V4 UI when Qt is installed."""

    from .app import main

    return main(argv)


__all__ = ["run_app"]

