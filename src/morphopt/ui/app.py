"""Application entry point for the MorphOpt UI (PySide6)."""

from __future__ import annotations

import os
import sys


def configure_environment() -> None:
    """Qt / VTK friendly defaults (call before creating QApplication)."""
    if sys.platform.startswith("linux"):
        session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
        if session_type == "x11":
            platform = "xcb"
        elif session_type == "wayland" or os.environ.get("WAYLAND_DISPLAY"):
            platform = "wayland"
        else:
            platform = "xcb"
        os.environ["QT_QPA_PLATFORM"] = platform
    os.environ.setdefault("PYVISTA_QT_BINDING", "pyside6")
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "True")


def create_application(argv: list[str] | None = None):
    """Create the shared QApplication with MorphOpt's process-wide settings."""
    configure_environment()

    from PySide6.QtWidgets import QApplication

    from .application_icon import (
        configure_application_identity,
        prepare_application_identity,
    )
    from .theme import theme_manager

    prepare_application_identity()
    app = QApplication.instance() or QApplication(argv or sys.argv)
    configure_application_identity(app)
    theme_manager.restore(app)
    return app


def main() -> int:
    """Launch the definition page in the main application window."""
    app = create_application()

    from .widgets.language_selector import restore_locale

    restore_locale()

    from .mainwindow import MainWindow

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
