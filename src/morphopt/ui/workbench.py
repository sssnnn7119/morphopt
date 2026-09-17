"""UI workbench coordinating the model tree and editor area."""

from .model.problem import ProblemModel


class Workbench:
    """Small façade for the future Qt workbench implementation."""

    def __init__(self, problem: ProblemModel | None = None) -> None:
        self.problem = problem
        """Problem model currently displayed by the workbench."""
