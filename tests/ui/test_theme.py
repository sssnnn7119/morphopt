from PySide6.QtWidgets import QApplication, QGroupBox

from morphopt.ui.theme.manager import ThemeManager
from morphopt.ui.theme.themes import DARK, LIGHT


def test_builtin_themes_apply_stylesheets_with_numeric_tokens() -> None:
    app = QApplication.instance() or QApplication([])
    manager = ThemeManager({"dark": DARK, "light": LIGHT})

    for name in manager.names:
        manager.apply(app, name, persist=False)
        stylesheet = app.styleSheet()
        assert stylesheet
        assert "@section_heading_size@" not in stylesheet
        assert "@dialog_title_size@" not in stylesheet
        title = QGroupBox("collection item")
        title.ensurePolished()
        assert title.font().weight() >= 700
