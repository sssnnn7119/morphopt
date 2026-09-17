"""Minimal V4 main window shell."""

from __future__ import annotations

from .model.problem import ProblemModel
from .workbench import Workbench


class MainWindow:
    """Top-level UI shell shared by definition and observation workflows."""

    def __init__(self, problem: ProblemModel | None = None) -> None:
        self.problem = problem
        """Active UI problem model."""
        self.workbench: Workbench | None = None
        """Lazily-created editor/observer workbench."""

    def show(self) -> None:
        # TODO: Replace with the V4 Qt MainWindow once model tree widgets land.
        return None
