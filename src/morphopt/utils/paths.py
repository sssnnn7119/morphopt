"""Portable names shared by result creation and UI result discovery."""

import re
from pathlib import Path


def write_result_launcher(folder: Path) -> None:
    """Write both desktop launchers so archives can move between Windows and Linux."""
    command = r"""@echo off
setlocal DisableDelayedExpansion
for %%I in (morphopt-ui.exe) do if not "%%~$PATH:I"=="" (
    start "" "%%~$PATH:I" --result "%~dp0."
    exit /b
)
chcp 65001 >nul
if exist "%USERPROFILE%\.conda\environments.txt" (
    for /f "usebackq delims=" %%E in ("%USERPROFILE%\.conda\environments.txt") do (
        if exist "%%E\Scripts\morphopt-ui.exe" (
            set "PATH=%%E;%%E\Library\bin;%%E\Scripts;%PATH%"
            start "" "%%E\Scripts\morphopt-ui.exe" --result "%~dp0."
            exit /b
        )
    )
)
echo MorphOpt UI was not found on PATH or in the registered Conda environments.
pause
exit /b 1
"""
    (folder / "Open MorphOpt.cmd").write_text(command, encoding="utf-8", newline="\r\n")
    command = (
        'if command -v morphopt-ui >/dev/null; then exec morphopt-ui --result "$1"; fi; '
        'while IFS= read -r prefix || [ -n "$prefix" ]; do '
        'if [ -x "$prefix/bin/morphopt-ui" ]; then '
        'export PATH="$prefix/bin:$PATH"; exec "$prefix/bin/morphopt-ui" --result "$1"; '
        'fi; done < "$HOME/.conda/environments.txt"; '
        'notify-send MorphOpt "MorphOpt UI was not found on PATH or in the registered Conda environments."; exit 1'
    )
    # Desktop entries unescape the value before parsing the double-quoted Exec argument.
    quoted = re.sub(r'(["`$\\])', r"\\\1", command).replace("\\", "\\\\")
    launcher = folder / "Open MorphOpt.desktop"
    launcher.write_text(
        "[Desktop Entry]\nType=Application\nName=Open MorphOpt result\n"
        "Name[zh_CN]=打开 MorphOpt 优化结果\nTerminal=false\n"
        f'Exec=sh -c "{quoted}" morphopt %k\n',
        encoding="utf-8",
        newline="\n",
    )
    launcher.chmod(launcher.stat().st_mode | 0o111)


def sanitize_name(name: str) -> str:
    """Return a single filename component valid on Windows and Linux.

    Args:
        name (str): Name identifying the item in its owning collection.

    Returns:
        str: A single filename component valid on Windows and Linux.
    """
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(" .")
    if not name:
        return "problem"
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "CONIN$",
        "CONOUT$",
        *(f"{prefix}{index}" for prefix in ("COM", "LPT") for index in "123456789¹²³"),
    }
    if name.split(".")[0].rstrip(" ").upper() in reserved:
        name = "_" + name
    return name
