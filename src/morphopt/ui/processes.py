"""Shared environment for UI-managed Python workers."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import QProcess


def worker_environment() -> dict[str, str]:
    """Match worker output to the UI's UTF-8 decoder on Windows and Linux."""
    environment = dict(os.environ)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUNBUFFERED"] = "1"
    environment.setdefault("PYVISTA_QT_BINDING", "pyside6")
    return environment


def start_worker(process: QProcess, request: str | Path) -> None:
    """Launch the shared worker with UTF-8 output and merged diagnostic channels."""
    from PySide6.QtCore import QProcess, QProcessEnvironment

    environment = QProcessEnvironment()
    for key, value in worker_environment().items():
        environment.insert(key, value)
    process.setProcessEnvironment(environment)
    process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
    process.start(sys.executable, ["-u", "-m", "morphopt.ui.worker", str(request)])
