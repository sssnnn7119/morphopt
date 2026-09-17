"""Read persisted history without importing the full runtime graph."""

from __future__ import annotations

import json
from pathlib import Path
from morphopt.optcore.controller import Controller
from morphopt.optcore.protocols import JsonObject


def read_history(folder_path: str | Path) -> JsonObject:
    folder = Path(folder_path)
    path = folder / "history.json" if folder.name == "logs" else folder / "logs" / "history.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_controller(result_path: str | Path, iteration: int | None = None) -> Controller:
    """Recreate a controller and parse history from the run ``logs`` folder."""

    path = Path(result_path)
    run_root = path.parent.parent if path.parent.name == "checkpoints" else path
    controller = Controller(result_root=run_root.parent, optimization_name=run_root.name)
    controller._result_path = run_root
    controller.initialize()
    controller.get_history().load(run_root, iteration)
    if path.parent.name == "checkpoints":
        controller.load(path, iteration if iteration is not None else controller.get_history().get_current_iteration() or 0)
    return controller
