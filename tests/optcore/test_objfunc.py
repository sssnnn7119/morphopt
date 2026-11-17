from __future__ import annotations

from morphopt.optcore.objfunc import ObjectiveFunction
import torch


def test_history_uses_the_evaluated_objective_without_recomputing():
    class Objective(ObjectiveFunction):
        calls = 0

        def __init__(self):
            super().__init__()
            self.response = torch.tensor(2.0, requires_grad=True)

        def objective_function(self):
            self.calls += 1
            return self.response.square()

        def get_metrics(self):
            return {"angle": torch.tensor([0.3])}

    objective = Objective()
    value = objective.evaluate()
    assert value.requires_grad and objective.value.grad_fn is None
    torch.testing.assert_close(torch.autograd.grad(value, objective.response)[0], torch.tensor(4.0))
    with torch.no_grad():
        objective.response.fill_(3.0)
        value.fill_(99.0)
    for _ in range(2):
        record = objective.history_data()
        assert record["objective"] == 4.0
        assert abs(record["metrics"]["angle"] - 0.3) < 1e-7
    assert objective.calls == 1


def test_save_persists_fea_model_for_every_iteration(tmp_path) -> None:
    class Model:
        def __init__(self) -> None:
            self.saved_paths: list[str] = []

        def save_model(self, path: str) -> None:
            self.saved_paths.append(path)

    objective = ObjectiveFunction()
    objective.fe = Model()
    objective.fe_results = []

    (tmp_path / "femodel&results").mkdir()
    objective.save(str(tmp_path), iteration=4)

    assert objective.fe.saved_paths == [
        str(tmp_path / "femodel&results" / "femodel_4")
    ]
