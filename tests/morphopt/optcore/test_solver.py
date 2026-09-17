"""test solver tests."""

from morphopt.optcore.controller import _AssemblyController
from morphopt.optcore.solver import Solver


def test_solver_empty_case():
    solver = Solver()
    solver.initialize(0)
    solver.reinitialize(0)
    controller = _AssemblyController(object(), 0)
    solver.build_solvers(controller)
    solver.solve(controller)
    assert solver.get_results() == ()
