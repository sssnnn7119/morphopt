"""Shared access to one optimization run's saved state and result files."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .context import cpu_torch_defaults

_LOGGER = logging.getLogger(__name__)


class OptimizationArchive:
    """Compose access to controller, parameters, history, and saved meshes.

    One instance represents one run directory and caches the restored model
    state. Export operations share this object instead of reimplementing the
    archive layout or initializing duplicate parameter trees.
    """

    def __init__(self, folder: str | Path) -> None:
        self.folder = Path(folder).resolve()
        self._controller_loaded = False
        self._controller_class: type[Any] | None = None
        self._params: Any | None = None
        self._parameters_iteration: int | None = None
        self._geometry_iterations: dict[str, int] = {}

    @property
    def log_folder(self) -> Path:
        return self.folder / "log"

    @property
    def controller_class(self) -> type[Any] | None:
        if not self._controller_loaded:
            self._controller_class = _import_controller(self.folder)
            self._controller_loaded = True
        return self._controller_class

    @property
    def params(self) -> Any | None:
        return self._params

    def initialize_params(self) -> Any | None:
        """Initialize the archived controller's geometry, FEA, and materials."""
        if self._params is None:
            controller = self.controller_class
            if controller is None:
                return None
            with cpu_torch_defaults():
                params = controller.Params()
                params.geometry.initialize()
                params.feamodel.initialize_interfaces()
                params.materials.initialize()
            self._params = params
        return self._params

    def load_parameters(self, iteration: int) -> Any | None:
        """Restore the complete model parameter state at one iteration."""
        params = self.initialize_params()
        if params is None:
            return None
        if self._parameters_iteration != iteration:
            self._parameters_iteration = None
            self._geometry_iterations.clear()
            with cpu_torch_defaults():
                params.load(foldpath=str(self.log_folder), iteration=iteration)
            self._parameters_iteration = iteration
        return params

    def load_geometry_part(self, name: str, iteration: int) -> Any:
        """Restore one geometry part without loading unrelated model state."""
        params = self.initialize_params()
        if params is None:
            raise ValueError("The archived geometry definition is unavailable.")
        part = params.geometry.interfaces[name]
        if self._parameters_iteration == iteration:
            return part
        if self._geometry_iterations.get(name) != iteration:
            self._parameters_iteration = None
            self._geometry_iterations.pop(name, None)
            with cpu_torch_defaults():
                part.load(foldpath=str(self.log_folder), iteration=iteration)
            self._geometry_iterations[name] = iteration
        return part

    def load_history(self, iteration: int | None = None) -> Any:
        """Load optimization history, optionally at a specific iteration."""
        from ..optcore.history import History

        history = History()
        if iteration is None:
            history.load(foldpath=str(self.log_folder))
        else:
            history.load(foldpath=str(self.log_folder), iteration=int(iteration))
        return history

    @property
    def completed_iteration(self) -> int:
        """Return the latest persisted iteration, or zero for an empty run."""
        try:
            history = self.load_history()
            return int(history.iteration or 0)
        except Exception:
            return 0

    @property
    def fea_folder(self) -> Path:
        return self.log_folder / "femodel&results"

    def fea_model_path(self, iteration: int) -> Path:
        return self.fea_folder / f"femodel_{iteration}.npz"

    def fea_result_path(self, case: str, iteration: int) -> Path:
        return self.fea_folder / f"result_{case}_iter_{iteration}.npz"

    def fea_iterations(self) -> tuple[int, ...]:
        """List iterations with an archived finite-element model."""
        return tuple(sorted(
            int(match[1])
            for path in self.fea_folder.glob("femodel_*.npz")
            if (match := re.fullmatch(r"femodel_(\d+)\.npz", path.name))
        ))

    def deformation_cases(self) -> tuple[str, ...]:
        """Return archived load-case names in their recorded order."""
        path = self.fea_folder / "load_cases.json"
        if not path.is_file():
            return ()
        return tuple(json.loads(path.read_text(encoding="utf-8")))

    def deformation_mesh(self, case: str, iteration: int) -> Any | None:
        """Read one saved load-case mesh, returning ``None`` if it is absent."""
        import pyvista as pv

        path = self.log_folder / "deformation" / f"task_{case}_iter_{iteration}.stl"
        return pv.read(path) if path.is_file() else None

    def visualizable_components(self) -> tuple[tuple[str, Any], ...]:
        """Return updateable model interfaces that implement visualization."""
        from ..optcore.protocal import ProtocalUpdatable, ProtocalVisualizable

        params = self._params
        if params is None:
            return ()
        collections = (
            ("Part", params.geometry),
            ("FEA", params.feamodel),
            ("Material", params.materials),
        )
        return tuple(
            (category, component)
            for category, collection in collections
            for component in collection.interfaces.values()
            if isinstance(component, ProtocalUpdatable)
            and isinstance(component, ProtocalVisualizable)
        )


@dataclass(frozen=True)
class IterationModel:
    """Reference to one saved finite-element model and optional load case."""

    folder: str
    iteration: int
    case: str | None = None

    @property
    def model_path(self) -> Path:
        return OptimizationArchive(self.folder).fea_model_path(self.iteration)

    @property
    def result_path(self) -> Path | None:
        if self.case is None:
            return None
        return OptimizationArchive(self.folder).fea_result_path(self.case, self.iteration)

    @staticmethod
    def iterations(folder: str) -> tuple[int, ...]:
        return OptimizationArchive(folder).fea_iterations()

    def cases(self) -> tuple[str, ...]:
        archive = OptimizationArchive(self.folder)
        return tuple(
            case for case in archive.deformation_cases()
            if archive.fea_result_path(case, self.iteration).is_file()
        )


def last_completed_iteration(folder: str | Path) -> int:
    """Return a run's latest saved iteration without retaining an archive."""
    return OptimizationArchive(folder).completed_iteration


def _import_controller(folder: Path) -> type[Any] | None:
    main = folder / "scripts" / "MAIN_SCRIPT_FOR_RESTART.py"
    if not main.is_file():
        return None

    resolved = str(folder)
    key = re.sub(r"[^A-Za-z0-9_]", "_", folder.name)
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
            with cpu_torch_defaults():
                spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            _LOGGER.exception("Could not import optimization controller from %s", main)
            return None
    return getattr(module, "ThisController", None)
