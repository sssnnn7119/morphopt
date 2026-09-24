from __future__ import annotations

from morphopt.optcore.objfunc import ObjectiveFunction


def test_save_persists_fea_model_for_every_iteration(tmp_path) -> None:
    class Model:
        def __init__(self) -> None:
            self.saved_paths: list[str] = []

        def save_model(self, path: str) -> None:
            self.saved_paths.append(path)

    objective = ObjectiveFunction()
    objective.fe = Model()
    objective.fe_results = []

    objective.save(str(tmp_path), iteration=4)

    assert objective.fe.saved_paths == [
        str(tmp_path / "femodel&results" / "femodel_4")
    ]
