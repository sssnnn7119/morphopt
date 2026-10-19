from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from morphopt.ui import application_icon as identity


@pytest.mark.parametrize("hresult", (0, -2147467259))
def test_windows_identity_uses_unicode_and_handles_native_api_failure(monkeypatch, caplog, hresult):
    setter = Mock(return_value=hresult)
    loader = Mock(return_value=SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=setter))
    monkeypatch.setattr(identity, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(ctypes, "WinDLL", loader, raising=False)

    assert identity._configure_windows_taskbar() is (hresult == 0)
    loader.assert_called_once_with("shell32", use_last_error=True)
    setter.assert_called_once_with(identity.WINDOWS_APP_ID)
    assert setter.argtypes == [ctypes.c_wchar_p]
    assert setter.restype is ctypes.c_int32
    if hresult:
        assert "0x80004005" in caplog.text


def test_missing_windows_shell_api_is_nonfatal(monkeypatch, caplog):
    monkeypatch.setattr(identity, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(ctypes, "WinDLL", Mock(side_effect=OSError("missing shell API")), raising=False)
    assert not identity._configure_windows_taskbar()
    assert "Windows taskbar identity" in caplog.text


def test_other_platforms_do_not_load_windows_dll(monkeypatch):
    loader = Mock(side_effect=AssertionError("Windows DLL requested on another platform"))
    monkeypatch.setattr(identity, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(ctypes, "WinDLL", loader, raising=False)
    assert not identity._configure_windows_taskbar()
    loader.assert_not_called()


@pytest.mark.parametrize("hresult", (0, -2147467259))
def test_windows_identity_precedes_qt_and_icons_render_at_taskbar_sizes(hresult, tmp_path):
    # The native Windows function is simulated; SVG loading and rendering are real.
    code = '''
import ctypes, json, os
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication
from morphopt.ui import app, application_icon
calls = []
class Setter:
    def __call__(self, identity):
        assert QApplication.instance() is None, "Windows identity set after Qt initialization"
        calls.append(identity)
        return int(os.environ["MORPHOPT_TEST_HRESULT"])
setter = Setter()
ctypes.WinDLL = lambda *args, **kwargs: SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=setter)
application_icon.sys = SimpleNamespace(platform="win32")
app.configure_environment = lambda: None
application = app.create_application(["morphopt-ui"])
assert calls == [application_icon.WINDOWS_APP_ID]
assert application.applicationName() == "MorphOpt"
icon = application.windowIcon()
assert not icon.isNull()
for size in (16, 32, 48, 256, 512, 1024):
    pixmap = icon.pixmap(size, size)
    assert not pixmap.isNull()
    assert pixmap.width() == size
    image = pixmap.toImage()
    assert image.pixelColor(size // 2, size // 5).alpha() > 0
    assert image.pixelColor(0, 0).alpha() == 0
print(json.dumps({"identity_before_qt": True, "svg_rendered": True}))
'''
    environment = dict(
        os.environ, QT_QPA_PLATFORM="offscreen", MORPHOPT_TEST_HRESULT=str(hresult),
        XDG_DATA_HOME=str(tmp_path / "data"),
    )
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    completed = subprocess.run(
        [sys.executable, "-c", code], env=environment, capture_output=True,
        text=True, timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.splitlines()[-1])["identity_before_qt"]
    assert not (tmp_path / "data/applications/morphopt.desktop").exists()


def test_linux_command_line_windows_inherit_svg_without_desktop_registration(tmp_path):
    code = '''
import json
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow
from morphopt.ui import app, application_icon
application_icon.sys = SimpleNamespace(platform="linux")
app.configure_environment = lambda: None
application = app.create_application(["morphopt-ui"])
assert application.desktopFileName() == ""
assert application.applicationName() == "MorphOpt"
for window in (QMainWindow(), QDialog()):
    icon = window.windowIcon()
    assert not icon.isNull()
    image = icon.pixmap(64, 64).toImage()
    assert image.pixelColor(32, 12).alpha() > 0
    assert image.pixelColor(0, 0).alpha() == 0
print(json.dumps({"svg_inherited": True}))
'''
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", XDG_DATA_HOME=str(tmp_path / "data"))
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    completed = subprocess.run(
        [sys.executable, "-c", code], env=environment, capture_output=True,
        text=True, timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.splitlines()[-1])["svg_inherited"]
    assert not (tmp_path / "data/applications").exists()
