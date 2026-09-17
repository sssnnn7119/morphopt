from pathlib import Path
from .problem import ProblemModel


def load_problem(path: str | Path) -> ProblemModel:
    # TODO: Load a versioned V4 task definition.
    Path(path)
    return ProblemModel()
