"""Use installed system fonts consistently in documentation captures."""

from pathlib import Path
from tempfile import TemporaryDirectory

from fontTools.ttLib import TTFont
from PySide6.QtGui import QFontDatabase, QFontInfo, QTextLayout

from morphopt.ui.theme.fonts import ROLES, _font_face, font_manager

SAMPLE = "几何材料压力载荷边界优化过程转换参数定义实例资产"


class CaptureFonts:
    """Apply preferences through the application's shared font manager."""

    def __init__(self):
        families = QFontDatabase.families(QFontDatabase.WritingSystem.SimplifiedChinese)
        chinese = "Noto Sans CJK SC" if "Noto Sans CJK SC" in families else ""
        for role in ROLES:
            font_manager.set_preferences(role, font_manager.default_font(role), chinese)
        face = _font_face(chinese) if chinese else None
        if face:
            self._directory = TemporaryDirectory(prefix='morphopt-doc-font-')
            target = Path(self._directory.name) / 'chinese.otf'
            with TTFont(face[0], fontNumber=face[1]) as font:
                font.save(target)
            from morphopt.ui.widgets import preview_renderer

            # VTK reads only the first TTC face; provide the selected SC face.
            preview_renderer._cjk_font_file = lambda: str(target)

    def audit(self):
        report = {}
        for role in ROLES:
            font = font_manager.font(role)
            layout = QTextLayout(SAMPLE, font)
            layout.beginLayout()
            layout.createLine()
            layout.endLayout()
            report[role] = {
                "western": QFontInfo(font_manager.snapshot(role)[0]).family(),
                "point_size": font.pointSizeF(),
                "han_glyph_families": sorted({
                    run.rawFont().familyName() for run in layout.glyphRuns()
                }),
            }
        return report
