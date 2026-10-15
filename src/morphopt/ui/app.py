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
QTreeWidget::item, QListWidget::item { padding: 3px 2px; }
QTreeWidget::item:selected, QTableWidget::item:selected, QListWidget::item:selected {
    background-color: #315b7e; color: #fff; }
QHeaderView::section { background-color: #262a33; color: #e0e0e0;
    border: 1px solid #2b2f38; padding: 4px; }
QTabWidget::pane { border: 1px solid #2b2f38; }
QTabBar::tab { background: #1a1a1a; color: #aaa; padding: 6px 12px;
    border-top-left-radius: 4px; border-top-right-radius: 4px; }
QTabBar::tab:selected { background: #0d47a1; color: #fff; }
QPushButton, QToolButton { background-color: #27374c; color: #edf3fa;
    border: 1px solid #40536b; padding: 5px 12px; border-radius: 4px;
    min-height: 18px; }
QPushButton:hover, QToolButton:hover { background-color: #354b65; border-color: #59728e; }
QPushButton:pressed, QToolButton:pressed { background-color: #213045; }
QPushButton:checked { background-color: #315b7e; border-color: #59728e; }
QPushButton[actionRole="primary"], QToolButton[actionRole="primary"] {
    background-color: #0d47a1; border-color: #1959b5; color: #fff; }
QPushButton[actionRole="primary"]:hover, QToolButton[actionRole="primary"]:hover {
    background-color: #1565c0; }
QPushButton[actionRole="danger"], QToolButton[actionRole="danger"] {
    background-color: #753539; border-color: #94494d; color: #fbe6e7; }
QPushButton[actionRole="danger"]:hover, QToolButton[actionRole="danger"]:hover {
    background-color: #934347; }
QPushButton:disabled, QToolButton:disabled { background-color: #252b34;
    border-color: #343c48; color: #6c7888; }
QPushButton[buttonLayout="prominent"] { padding: 6px 18px; font-weight: 600; }
QPushButton[buttonLayout="choice"] { text-align: left; padding: 8px 12px; }
QToolButton::menu-indicator { subcontrol-origin: padding; subcontrol-position: right center;
    right: 4px; }
QToolButton[menuButton="true"] { padding-right: 20px; }
QLabel[textRole="sectionHeading"] { font-size: 14px; font-weight: 600; color: #dce5f0; }
QGroupBox { border: 1px solid #324052; border-radius: 4px; margin-top: 10px;
    padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left;
    left: 10px; padding: 0px 4px; color: #dce5f0; }
QGroupBox[collectionSelected="true"] { border-color: #397ac2; }
QMenu::item { padding: 6px 20px; }
QMenu::item:selected { background-color: #354b65; }
QMenu::item:disabled { color: #6c7888; }
QMenu::separator { height: 1px; background: #324052; margin: 4px 8px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: #262a33; color: #e0e0e0;
    border: 1px solid #3a3f4a; padding: 3px; }
QComboBox { combobox-popup: 0; qproperty-maxVisibleItems: 12; }
QComboBox QAbstractItemView { background: #1c1f26; color: #e0e0e0;
    border: 1px solid #3a3f4a; selection-background-color: #0d47a1; }
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

    from .widgets.language_selector import restore_locale
    restore_locale()

    from .mainwindow import MainWindow

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
