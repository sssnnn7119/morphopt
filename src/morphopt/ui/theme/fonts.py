"""Application typography preferences shared by widgets and charts."""

from functools import lru_cache
import hashlib
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from fontTools.ttLib import TTCollection, TTFont
from matplotlib import font_manager as mpl_fonts
from PySide6.QtCore import QEvent, QObject, QSettings, Signal
from PySide6.QtGui import QFont, QFontDatabase, QFontInfo
from PySide6.QtWidgets import QApplication, QLabel

ROLES = ("body", "tree", "heading", "code", "chart")
_font_directory = TemporaryDirectory(prefix="morphopt-fonts-", ignore_cleanup_errors=True)


def _face_metadata(font: TTFont) -> tuple[set[str], int]:
    names: set[str] = set()
    for record in font["name"].names:
        if record.nameID in (1, 16):
            try:
                names.add(record.toUnicode().strip().casefold())
            except (AttributeError, UnicodeDecodeError):
                continue
    try:
        weight = font["OS/2"].usWeightClass
    except (AttributeError, KeyError):
        weight = 400
    return names, weight


def _search_font_face(family: str) -> tuple[str, int] | None:
    """Scan installed font files for a family name Qt resolved locally."""
    target = family.casefold()
    paths = {str(entry.fname) for entry in mpl_fonts.fontManager.ttflist}
    paths.update(mpl_fonts.findSystemFonts())
    best: tuple[str, int] | None = None
    best_distance = sys.maxsize
    for path in sorted(paths):
        try:
            if path.lower().endswith((".ttc", ".otc")):
                fonts = TTCollection(path, lazy=True).fonts
            else:
                fonts = [TTFont(path, lazy=True)]
        except Exception:
            continue
        try:
            for index, font in enumerate(fonts):
                names, weight = _face_metadata(font)
                distance = abs(weight - 400)
                if target in names and distance < best_distance:
                    best, best_distance = (path, index), distance
        except Exception:
            continue
        finally:
            for font in fonts:
                font.close()
        if best_distance == 0:
            break
    return best


@lru_cache(maxsize=32)
def _font_face(family: str) -> tuple[str, int] | None:
    """Locate the font file and face index that render ``family``."""
    try:
        found = mpl_fonts.findfont(
            mpl_fonts.FontProperties(family=[family]), fallback_to_default=False
        )
        return str(found), int(getattr(found, "face_index", 0) or 0)
    except ValueError:
        pass
    except Exception:
        return None
    # Matplotlib's cache can predate newly installed fonts and only indexes
    # primary family names, so it misses localized aliases such as 微软雅黑.
    try:
        return _search_font_face(family)
    except Exception:
        return None


@lru_cache(maxsize=32)
def _western_family(family: str, chinese: str) -> str:
    """Mask Han glyphs in the western font so Qt can select the Chinese font.

    The alias encodes the Chinese family because Qt caches the fallback engine
    of a primary family: a new alias is what makes a changed Chinese font take
    effect immediately instead of after a restart.
    """
    face = _font_face(family)
    if face is None:
        return family
    path, index = face
    try:
        font = TTFont(path, fontNumber=index)
    except Exception:
        return family
    try:
        cmap_tables = [
            table for table in font["cmap"].tables
            if table.isUnicode() and isinstance(getattr(table, "cmap", None), dict)
        ]
        def is_han(code: int) -> bool:
            return (
                0x3400 <= code <= 0x9FFF
                or 0xF900 <= code <= 0xFAFF
                or 0x20000 <= code <= 0x323AF
            )

        for table in cmap_tables:
            table.cmap = {code: glyph for code, glyph in table.cmap.items() if not is_han(code)}
        digest = hashlib.sha1(f"{path}\0{index}\0{chinese}".encode("utf-8")).hexdigest()[:16]
        alias = f"MorphOpt Western {digest}"
        for record in font["name"].names:
            if record.nameID in (1, 4, 6, 16, 21):
                value = alias.replace(" ", "-") if record.nameID == 6 else alias
                record.string = value.encode(record.getEncoding() or "utf-16-be", errors="replace")
        output = Path(_font_directory.name) / f"western-{digest}.ttf"
        font.save(output)
    except Exception:
        return family
    finally:
        font.close()
    font_id = QFontDatabase.addApplicationFontFromData(output.read_bytes())
    if font_id < 0:
        return family
    families = QFontDatabase.applicationFontFamilies(font_id)
    if not families:
        return family
    try:
        mpl_fonts.fontManager.addfont(str(output))
    except Exception:
        pass
    return families[0]


class FontManager(QObject):
    changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._defaults: dict[str, QFont] = {}
        self._western: dict[str, QFont] = {}
        self._chinese: dict[str, str] = {}

    def restore(self, app: QApplication) -> None:
        body = QFont(app.font())
        self._defaults = {role: QFont(body) for role in ROLES}
        settings = QSettings("MorphOptUI", "ui")
        for role in ROLES:
            font = QFont()
            saved = settings.value(f"fonts/{role}/western", "", str)
            self._western[role] = (
                font if saved and font.fromString(saved) else QFont(self._defaults[role])
            )
            self._chinese[role] = settings.value(f"fonts/{role}/chinese", "", str)
        app.installEventFilter(self)
        self._apply("body")

    def _ensure_role(self, role: str) -> None:
        """Allow widgets to query fonts before ``restore`` ran (e.g. in tests)."""
        if role in self._western:
            return
        app = QApplication.instance()
        fallback = QFont(app.font()) if app is not None else QFont()
        self._defaults.setdefault(role, QFont(fallback))
        self._western.setdefault(role, QFont(fallback))
        self._chinese.setdefault(role, "")

    def snapshot(self, role: str) -> tuple[QFont, str]:
        self._ensure_role(role)
        return QFont(self._western[role]), self._chinese[role]

    def default_font(self, role: str) -> QFont:
        self._ensure_role(role)
        return QFont(self._defaults[role])

    def compose(self, font: QFont, chinese_family: str = "") -> QFont:
        """Return a display font with Han glyphs supplied by the chosen family."""
        result = QFont(font)
        if not chinese_family:
            return result
        chinese = QFontInfo(QFont(chinese_family)).family()
        western = _western_family(QFontInfo(result).family(), chinese)
        families = [western]
        if chinese and chinese != western:
            families.append(chinese)
        result.setFamilies(families)
        return result

    def font(self, role: str) -> QFont:
        self._ensure_role(role)
        return self.compose(self._western[role], self._chinese[role])

    def set_preferences(self, role: str, western: QFont, chinese: str) -> None:
        self._ensure_role(role)
        self._western[role] = QFont(western)
        self._chinese[role] = chinese
        settings = QSettings("MorphOptUI", "ui")
        if western == self._defaults[role]:
            settings.remove(f"fonts/{role}/western")
        else:
            settings.setValue(f"fonts/{role}/western", western.toString())
        if chinese:
            settings.setValue(f"fonts/{role}/chinese", chinese)
        else:
            settings.remove(f"fonts/{role}/chinese")
        self._apply(role)

    def _apply(self, role: str) -> None:
        app = QApplication.instance()
        if app is None:
            return
        if role == "body":
            app.setFont(self.font(role))
            # Re-polish styled widgets so they inherit the new application font.
            app.setStyleSheet(app.styleSheet())
            for widget in app.allWidgets():
                self._apply_heading(widget)
            self.changed.emit("tree")
            self.changed.emit("code")
        elif role == "heading":
            for widget in app.allWidgets():
                self._apply_heading(widget)
        self.changed.emit(role)

    def _apply_heading(self, widget: QObject) -> None:
        if isinstance(widget, QLabel) and widget.property("textRole") in (
            "sectionHeading",
            "dialogTitle",
        ):
            widget.setFont(self.font("heading"))

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if self._defaults and event.type() in (
            QEvent.Type.Polish,
            QEvent.Type.DynamicPropertyChange,
        ):
            self._apply_heading(obj)
        return False


font_manager = FontManager()


@lru_cache(maxsize=32)
def _chart_families(preferred: tuple[str, ...]) -> tuple[str, ...]:
    windows = ("Microsoft YaHei UI", "Microsoft YaHei", "DengXian", "SimHei", "SimSun")
    others = ("Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei", "PingFang SC")
    fallback = windows + others if sys.platform == "win32" else others + windows
    installed = {entry.name.casefold(): entry.name for entry in mpl_fonts.fontManager.ttflist}
    families = (
        installed[name.casefold()]
        for name in (*preferred, "DejaVu Sans", *fallback)
        if name.casefold() in installed
    )
    return tuple(dict.fromkeys(families))


def chart_font() -> mpl_fonts.FontProperties:
    font = font_manager.font("chart")
    return mpl_fonts.FontProperties(family=list(_chart_families(tuple(font.families()))))
