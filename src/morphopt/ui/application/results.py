"""Read-only access to an optimization result directory."""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def _cpu_torch_defaults():
    """Create result-view objects on CPU without leaking process defaults."""
    import torch

    previous_dtype = torch.get_default_dtype()
    previous_device = torch.get_default_device()
    torch.set_default_dtype(torch.float64)
    torch.set_default_device("cpu")
    try:
        yield
    finally:
        torch.set_default_dtype(previous_dtype)
        torch.set_default_device(previous_device)


def controller_class_from_folder(path_result: str):
    """Import ``ThisController`` from a result folder's frozen main script."""
    main = Path(path_result) / "scripts" / "MAIN_SCRIPT_FOR_RESTART.py"
    if not main.exists():
        return None

    resolved = str(Path(path_result).resolve())
    key = re.sub(r"[^A-Za-z0-9_]", "_", Path(resolved).name)
    digest = hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:12]
    module_name = f"morphopt_run_{key}_{digest}"
    module = sys.modules.get(module_name)
    if module is None:
        spec = importlib.util.spec_from_file_location(module_name, main)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            with _cpu_torch_defaults():
                spec.loader.exec_module(module)
        except Exception as exc:  # pragma: no cover - best-effort result browsing
            sys.modules.pop(module_name, None)
            print(f"controller import failed for {path_result}: {exc}")
            return None
    return getattr(module, "ThisController", None)


def last_completed_iteration(path_result: str) -> int:
    """Return the latest persisted iteration, or zero for an empty result."""
    try:
        from ...optcore.history import History

        history = History()
        history.load(foldpath=str(Path(path_result) / "log"))
        return int(history.iteration or 0)
    except Exception:
        return 0


class ResultSession:
    """Stateful reader for one result directory.

    Controller imports and parameter initialization happen once per folder;
    histories are loaded per selected iteration.  Views receive ready-to-render
    objects and do not need to know the on-disk layout.
    """

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.folder: str | None = None
        self.controller = None
        self.params = None
        self.history = None
        self.iteration = 0

    def bind(self, folder: str) -> bool:
        folder = str(Path(folder).resolve())
        if self.folder == folder and self.controller is not None:
            return True
        self.reset()
        self.folder = folder
        self.controller = controller_class_from_folder(folder)
        if self.controller is None:
            return False
        try:
            with _cpu_torch_defaults():
                self.params = self.controller.Params()
                self.params.initialize()
        except Exception as exc:
            print(f"params init failed: {exc}")
            self.params = None
        return True

    def load_iteration(self, folder: str, iteration: int):
        normalized = str(Path(folder).resolve())
        if normalized != self.folder:
            self.bind(folder)
        from ...optcore.history import History

        history = History()
        history.load(
            foldpath=str(Path(folder) / "log"), iteration=int(iteration)
        )
        self.folder = normalized
        self.iteration = int(iteration)
        self.history = history
        return history

    def deformation_cases(self) -> tuple[int, ...]:
        if not self.folder:
            return ()
        found: set[int] = set()
        deformation = Path(self.folder) / "log" / "deformation"
        for path in deformation.glob("task_*_iter_*.stl"):
            match = re.match(r"task_(\d+)_iter_\d+\.stl$", path.name)
            if match:
                found.add(int(match.group(1)))
        return tuple(sorted(found))
