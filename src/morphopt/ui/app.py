"""Application entry point for the MorphOpt UI (PySide6)."""

from __future__ import annotations

import os
import sys


def configure_environment() -> None:
    """Qt / VTK friendly defaults (call before creating QApplication)."""
    if sys.platform.startswith("linux") and not os.environ.get("QT_QPA_PLATFORM"):
        session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
        ssh_session = os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY")
        if ssh_session and os.environ.get("DISPLAY"):
            # SSH forwards X11, even when either desktop uses Wayland.
            platform = "xcb"
        elif session_type == "x11":
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

    from PySide6.QtCore import QEvent, QObject, QPointF, QSettings
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import (
        QAbstractScrollArea,
        QAbstractSpinBox,
        QApplication,
        QComboBox,
        QDial,
        QLineEdit,
        QSlider,
    )

    from .application_icon import (
        configure_application_identity,
        prepare_application_identity,
    )
    from .i18n import localization
    from .theme import theme_manager
    from .theme.fonts import font_manager
    from .theme.visualization import visualization_manager

    prepare_application_identity()
    app = QApplication.instance() or QApplication(argv or sys.argv)

    class WheelInputFilter(QObject):
        """Send wheel input to the page instead of changing a field's value."""

        def eventFilter(self, watched: QObject, event: QEvent) -> bool:
            if event.type() == QEvent.Type.Wheel and isinstance(
                watched, (QComboBox, QAbstractSpinBox, QSlider, QDial, QLineEdit)
            ):
                event.ignore()
                parent = watched.parentWidget()
                while parent is not None:
                    if isinstance(parent, QAbstractScrollArea):
                        viewport = parent.viewport()
                        forwarded = QWheelEvent(
                            QPointF(viewport.mapFromGlobal(event.globalPosition().toPoint())),
                            event.globalPosition(),
                            event.pixelDelta(),
                            event.angleDelta(),
                            event.buttons(),
                            event.modifiers(),
                            event.phase(),
                            event.inverted(),
                            event.source(),
                            event.pointingDevice(),
                        )
                        QApplication.sendEvent(viewport, forwarded)
                        if forwarded.isAccepted():
                            break
                    parent = parent.parentWidget()
                return True
            return False

    if app.findChild(QObject, "wheelInputFilter") is None:
        wheel_filter = WheelInputFilter(app)
        wheel_filter.setObjectName("wheelInputFilter")
        app.installEventFilter(wheel_filter)

    configure_application_identity(app)
    localization.set_locale(
        QSettings("MorphOptUI", "ui").value("language", "zh-CN", str)
    )
    font_manager.restore(app)
    theme_manager.restore(app)
    visualization_manager.restore()
    return app


def main() -> int:
    """Launch the definition page in the main application window."""
    app = create_application()

    from .mainwindow import MainWindow

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
