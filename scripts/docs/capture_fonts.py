"""Apply the documentation font policy within a screenshot process."""

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from fontTools.ttLib import TTFont
from PySide6.QtGui import QFont, QFontDatabase, QTextLayout
from PySide6.QtWidgets import QPlainTextEdit, QWidget

FAMILY = "Noto Sans CJK SC"
SAMPLE = "几何材料压力载荷边界优化过程转换参数定义实例资产"


def glyph_runs(font):
    layout = QTextLayout(SAMPLE, font)
    layout.beginLayout()
    layout.createLine()
    layout.endLayout()
    runs = [
        {"family": run.rawFont().familyName(), "style": run.rawFont().styleName()}
        for run in layout.glyphRuns()
    ]
    if not runs or any(run["family"] != FAMILY for run in runs):
        raise RuntimeError(f"Unexpected Chinese font: {font.toString()}: {runs}")
    return runs


class CaptureFonts:
    """Keep Qt and VTK on the installed SC family, including its TTC face."""

    def __init__(self, app):
        if FAMILY not in QFontDatabase.families():
            raise RuntimeError(f"Install the documentation font: {FAMILY}")
        source, index = subprocess.check_output(
            ["fc-match", "-f", "%{file}\n%{index}", FAMILY], text=True
        ).splitlines()
        self._directory = TemporaryDirectory(prefix="morphopt-capture-fonts-")
        self.path = Path(self._directory.name) / "NotoSansCJKSC-Regular.otf"
        with TTFont(source, fontNumber=int(index)) as font:
            if font["name"].getDebugName(1) != FAMILY:
                raise RuntimeError("Fontconfig did not select the SC face")
            font.save(self.path)

        app.setFont(QFont(FAMILY, 10))
        from morphopt.ui.widgets import preview_renderer

        # VTK selects the first face of a TTC; supply the extracted SC face.
        preview_renderer._cjk_font_file = lambda: str(self.path)
        self.report = {
            "family": FAMILY,
            "point_size": 10,
            "vtk_font_file": self.path.name,
            "source_collection": Path(source).name,
            "glyph_runs": {},
        }
        for weight in (400, 600, 700):
            font = QFont(FAMILY, 10)
            font.setWeight(QFont.Weight(weight))
            self.report["glyph_runs"][str(weight)] = glyph_runs(font)

    def apply_to_window(self, window):
        """Retain widget sizes and weights; specify CJK fallback for code."""
        for widget in window.findChildren(QWidget):
            font = widget.font()
            font.setFamilies(
                ["Hack", FAMILY] if isinstance(widget, QPlainTextEdit) else [FAMILY]
            )
            widget.setFont(font)

    def audit(self, window):
        fonts = {widget.font().toString(): widget.font()
                 for widget in window.findChildren(QWidget)}
        self.report["sampled_widget_fonts"] = {
            name: glyph_runs(font) for name, font in fonts.items()
        }
        return self.report
