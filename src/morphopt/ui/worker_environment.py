"""Shared environment for UI-managed Python workers."""

from __future__ import annotations

import os
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


def configure_worker_process(process: QProcess) -> None:
    """Apply the same Python environment to Qt-managed workers."""
    from PySide6.QtCore import QProcessEnvironment

    environment = QProcessEnvironment()
    for key, value in worker_environment().items():
        environment.insert(key, value)
    process.setProcessEnvironment(environment)
