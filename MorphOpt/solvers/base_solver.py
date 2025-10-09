
import FEA

class BaseSolver:
    """
    Base class for all solvers.
    """

    def __init__(self, *args, **kwargs):
        pass

    def initialize(self, iteration: int) -> None:
        """
        Initialize the solver with the given problem.
        """
        pass

    def solve(self):
        """
        Solve the given problem.
        """
        raise NotImplementedError(
            "This method should be overridden by subclasses.")

    @staticmethod
    def init_FEA(inp: FEA.FEA_INP) -> FEA.FEAController:
        """
        Initialize the FEA solver.
        """
        raise NotImplementedError(
            "This method should be overridden by subclasses.")

    @staticmethod
    def _solve_FEA(current_class: 'BaseSolver', path_result,
                   pressure_list: list[float], task_index: int):
        """
        Solve the FEA problem.
        """
        raise NotImplementedError(
            "This method should be overridden by subclasses.")


