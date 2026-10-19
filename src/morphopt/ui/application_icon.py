"""Application identity and icon shared by every MorphOpt workspace."""

import logging
import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication, QIcon

ICON_PATH = Path(__file__).with_name("assets") / "morphopt.svg"
WINDOWS_APP_ID = "MorphOpt.MorphOpt"
_LOGGER = logging.getLogger(__name__)


def _configure_windows_taskbar() -> bool:
    """Give running windows a stable taskbar identity without installing launchers."""
    if sys.platform != "win32":
        return False

    import ctypes

    try:
        shell = ctypes.WinDLL("shell32", use_last_error=True)
        setter = shell.SetCurrentProcessExplicitAppUserModelID
        setter.argtypes = [ctypes.c_wchar_p]
        setter.restype = ctypes.c_int32
        result = setter(WINDOWS_APP_ID)
        if result != 0:
            raise OSError(f"SetCurrentProcessExplicitAppUserModelID: HRESULT 0x{result & 0xffffffff:08X}")
        return True
    except (AttributeError, OSError):
        _LOGGER.warning("Could not set the MorphOpt Windows taskbar identity", exc_info=True)
        return False


def application_icon() -> QIcon:
    """Let Qt render the same SVG at native icon sizes on every platform."""
    return QIcon(str(ICON_PATH))


def prepare_application_identity() -> None:
    """Prepare process metadata without writing desktop files or shortcuts."""
    QGuiApplication.setApplicationName("MorphOpt")
    if sys.platform == "win32":
        _configure_windows_taskbar()


def configure_application_identity(app) -> None:
    """Set the process-wide window icon after QApplication exists."""
    app.setWindowIcon(application_icon())
