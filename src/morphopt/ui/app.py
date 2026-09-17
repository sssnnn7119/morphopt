"""Qt application bootstrap kept separate from the optimization runtime."""

from __future__ import annotations

from typing import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # pragma: no cover - depends on optional UI stack
        raise RuntimeError("PySide6 is required to launch morphopt.ui") from exc
    application = QApplication(list(argv or ()))
    from .mainwindow import MainWindow

    window = MainWindow()
    window.show()
    return application.exec()

