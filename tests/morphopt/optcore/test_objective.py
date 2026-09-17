"""test objective tests."""

from morphopt.optcore.objective import ObjectiveFunction


def test_empty_objective_is_scalar():
    objective = ObjectiveFunction()
    objective.initialize()
    objective.reinitialize(0, {}, ())
    objective.build_evaluation()
    assert float(objective.get_objective()) == 0.0
