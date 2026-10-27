"""Regression tests for combining the western and Chinese font selections."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from matplotlib import font_manager as mpl_fonts
from PySide6.QtGui import QFont, QFontDatabase, QFontInfo, QRawFont
from PySide6.QtWidgets import QApplication

from morphopt.ui.theme import fonts


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _han_family() -> str | None:
    for family in QFontDatabase.families():
        if QRawFont.fromFont(QFont(family)).supportsCharacter(0x4E2D):
            return family
    return None


def test_font_face_scans_name_tables_when_matplotlib_misses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Localized families (e.g. 微软雅黑) are absent from matplotlib's index."""

    def missing(*_args, **_kwargs):
        raise ValueError("family is not indexed")

    monkeypatch.setattr(mpl_fonts, "findfont", missing)
    fonts._font_face.cache_clear()
    try:
        face = fonts._font_face("DejaVu Sans")
    finally:
        fonts._font_face.cache_clear()
    assert face is not None
    assert os.path.basename(face[0]).lower().startswith("dejavusans")


def test_western_alias_masks_han_glyphs() -> None:
    _app()
    family = _han_family()
    if family is None:
        pytest.skip("no installed font provides Han glyphs")
    alias = fonts._western_family(family, "MorphOpt Test Chinese")
    assert alias != family
    assert not QRawFont.fromFont(QFont(alias)).supportsCharacter(0x4E2D)


def test_western_alias_is_unique_per_chinese_family() -> None:
    _app()
    families = QFontDatabase.families()
    assert len(families) > 1
    first = fonts._western_family("DejaVu Sans", families[0])
    second = fonts._western_family("DejaVu Sans", families[1])
    assert first.startswith("MorphOpt Western ")
    assert second.startswith("MorphOpt Western ")
    assert first != second


def test_font_pairs_western_alias_with_chinese_family() -> None:
    app = _app()
    manager = fonts.FontManager()
    manager._defaults = {role: QFont(app.font()) for role in fonts.ROLES}
    manager._western = {role: QFont("DejaVu Sans") for role in fonts.ROLES}
    manager._chinese = {role: "" for role in fonts.ROLES}
    chinese = QFontDatabase.families()[0]
    manager._chinese["body"] = chinese

    families = manager.font("body").families()

    assert len(families) == 2
    assert families[0].startswith("MorphOpt Western ")
    assert families[1] == QFontInfo(QFont(chinese)).family()
