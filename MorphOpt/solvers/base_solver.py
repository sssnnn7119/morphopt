import os
import sys

import numpy as np
import torch

import FEA

from .FE_result import FE_result

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

    def solve(self) -> FE_result:
        """
        Solve the given problem.
        """
        raise NotImplementedError(
            "This method should be overridden by subclasses.")

    @staticmethod
    def init_FEA(inp: FEA.FEA_INP) -> FEA.Main.FEA_Main:
        """
        Initialize the FEA solver.
        """
        raise NotImplementedError(
            "This method should be overridden by subclasses.")

    @staticmethod
    def _solve_FEA(current_class: 'BaseSolver', path_result,
                   pressure_list: list[float], U_dim: list[int]):
        """
        Solve the FEA problem.
        """
        raise NotImplementedError(
            "This method should be overridden by subclasses.")


