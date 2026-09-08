"""Application entry point for the MorphOpt UI (PySide6)."""

from __future__ import annotations

import os
import sys

_DARK_QSS = """
QMainWindow, QDialog, QWidget { background-color: #121212; color: #e0e0e0; }
QMenuBar, QToolBar, QMenu { background-color: #1a1a1a; color: #e0e0e0; }
QStatusBar { background-color: #1a1a1a; color: #aaa; }
QTreeWidget, QTreeView, QTableWidget, QListWidget, QPlainTextEdit, QTextEdit {
    background-color: #1c1f26; color: #e0e0e0; border: 1px solid #2b2f38; }
QHeaderView::section { background-color: #262a33; color: #e0e0e0;
    border: 1px solid #2b2f38; padding: 4px; }
QTabWidget::pane { border: 1px solid #2b2f38; }
QTabBar::tab { background: #1a1a1a; color: #aaa; padding: 6px 12px;
    border-top-left-radius: 4px; border-top-right-radius: 4px; }
QTabBar::tab:selected { background: #0d47a1; color: #fff; }
QPushButton { background-color: #0d47a1; color: #fff; border: none;
    padding: 5px 14px; border-radius: 3px; }
QPushButton:hover { background-color: #1565c0; }
QPushButton:disabled { background-color: #333; color: #777; }
QLineEdit, QComboBox, QSpinBox { background: #262a33; color: #e0e0e0;
    border: 1px solid #3a3f4a; padding: 3px; }
QCheckBox { color: #e0e0e0; }
QScrollBar:vertical { background: #1a1a1a; width: 10px; }
QScrollBar::handle:vertical { background: #3a3f4a; border-radius: 5px; }
QSplitter::handle { background: #2b2f38; }
"""


def configure_environment() -> None:
    """Qt / VTK friendly defaults (call before creating QApplication)."""
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    os.environ.setdefault("PYVISTA_QT_BINDING", "pyside6")
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "True")


def create_application(argv: list[str] | None = None):
    """Create the shared QApplication with MorphOpt's process-wide settings."""
    configure_environment()

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setStyleSheet(_DARK_QSS)
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
