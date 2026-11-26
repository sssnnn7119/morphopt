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
from typing import TYPE_CHECKING, Any

from ._runtime import cpu_torch_defaults
from .snapshots import SavedComponent, Snapshot, design_components, snapshot_path

if TYPE_CHECKING:
    from torchfea import FEAController
    from torchfea.solver import StaticResult

_LOGGER = logging.getLogger(__name__)


class OptimizationArchive:
    """Compose access to controller, parameters, history, and saved meshes.

    One instance represents one run directory and caches the restored model
    state. Export operations share this object instead of reimplementing the
    archive layout or initializing duplicate parameter trees.
    """

    def __init__(self, folder: str | Path) -> None:
        """Initialize OptimizationArchive and its configuration state.

        Args:
            folder (str | Path): Directory containing the optimization run or archive.
        """
        self.folder = Path(folder).resolve()
        self._controller_loaded = False
        self._controller_class: type[Any] | None = None
        self._params: Any | None = None
        self._parameters_iteration: int | None = None
        self._component_iterations: dict[int, int] = {}
        self._snapshot_iteration = None
        self._snapshot = None

    @property
    def log_folder(self) -> Path:
        """Locate the log directory within the optimization archive.

        Returns:
            Path: Archive folder followed by log.
        """
        return self.folder / "log"

    @property
    def log_files(self) -> tuple[Path, ...]:
        """Saved text logs, available before the first completed iteration.

        Returns:
            tuple[Path, ...]: Saved text logs, available before the first completed iteration.
        """
        return tuple(
            sorted(path for path in self.log_folder.glob("*.log") if path.is_file())
        )

    @property
    def controller_class(self) -> type[Any] | None:
        """Lazily import and cache the controller declaration from the archived script.

        Returns:
            type | None: Archived ThisController class, or None if no declaration can be imported.
        """
        if not self._controller_loaded:
            self._controller_class = _import_controller(self.folder)
            self._controller_loaded = True
        return self._controller_class

    @property
    def params(self) -> Any | None:
        """Access the already initialized archived parameter collection.

        Returns:
            Params | None: Current cached parameters; None until initialization succeeds.
        """
        return self._params

    def initialize_params(self) -> Any | None:
        """Initialize the archived controller's geometry, FEA, and materials.

        Returns:
            Params | None: Initialized parameter collection from the archived task; None if no
                controller definition is available.
        """
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
        """Restore the complete model parameter state at one iteration.

        Args:
            iteration (int): Iteration index associated with the saved or current model state.

        Returns:
            Params | None: Model parameters restored at iteration, or None when the archived
                controller is unavailable.
        """
        params = self.initialize_params()
        if params is None:
            return None
        if self._parameters_iteration != iteration:
            self._parameters_iteration = None
            self._component_iterations.clear()
            with cpu_torch_defaults():
                params.load(foldpath=str(self.log_folder), iteration=iteration)
            self._parameters_iteration = iteration
        return params

    def load_geometry_part(self, name: str, iteration: int) -> Any:
        """Restore one geometry part without loading unrelated model state.

        Args:
            name (str): Name identifying the item in its owning collection.
            iteration (int): Iteration index associated with the saved or current model state.

        Returns:
            BasePart: Registered geometry interface restored at the requested iteration.
        """
        params = self.initialize_params()
        if params is None:
            raise ValueError("The archived geometry definition is unavailable.")
        return self._load_component(params.geometry.interfaces[name], iteration)

    def _load_component(self, component: Any, iteration: int) -> Any:
        """Restore one interface without loading unrelated checkpoints."""
        key = id(component)
        if (
            self._parameters_iteration != iteration
            and self._component_iterations.get(key) != iteration
        ):
            self._parameters_iteration = None
            self._component_iterations.pop(key, None)
            with cpu_torch_defaults():
                component.load(foldpath=str(self.log_folder), iteration=iteration)
            self._component_iterations[key] = iteration
        return component

    def load_design_component(self, component: Any, iteration: int) -> Any:
        """Restore the native design for component export at a completed solve.

        Row k displays geometry checkpoint k - 1, starting with the initial surface.
        """
        if getattr(component, "surfaceinterfaces", None) is None:
            return self._load_component(component, iteration)

        step = iteration - 1
        directory = self.log_folder / component.pathlog_required()[0] / component.name
        for index, surface in enumerate(component.surfaceinterfaces):
            if surface.num_variables:
                stem = directory / f"Surface-{index}_iter-{step}"
                if not stem.is_file() and not stem.with_suffix(".npz").is_file():
                    raise FileNotFoundError(
                        f"Missing surface for iteration {iteration}: {stem}"
                    )
        return self.load_geometry_part(component.name, step)

    def load_history(self, iteration: int | None = None) -> Any:
        """Load optimization history, optionally at a specific iteration.

        Args:
            iteration (int | None): Iteration index associated with the saved or current model
                state.

        Returns:
            History: Recorded history containing entries through the requested iteration, or all
                saved entries when iteration is None.
        """
        from ..optcore.history import History

        history = History()
        if iteration is None:
            history.load(foldpath=str(self.log_folder))
        else:
            history.load(foldpath=str(self.log_folder), iteration=int(iteration))
        return history

    @property
    def completed_iteration(self) -> int:
        """Return the latest persisted iteration, or zero for an empty run.

        Returns:
            int: The latest persisted iteration, or zero for an empty run.
        """
        try:
            history = self.load_history()
            return int(history.iteration or 0)
        except Exception:
            return 0

    @property
    def fea_folder(self) -> Path:
        """Locate saved finite-element models and solutions within the archive.

        Returns:
            Path: Log subdirectory named femodel&results.
        """
        return self.log_folder / "femodel&results"

    def fea_model_path(self, iteration: int) -> Path:
        """Resolve the native finite-element model filename for a completed iteration.

        Args:
            iteration (int): Iteration index associated with the saved or current model state.

        Returns:
            Path: Model archive path ending in femodel_ITERATION.npz; existence is not checked.
        """
        return self.fea_folder / f"femodel_{iteration}.npz"

    def fea_result_path(self, case: str, iteration: int) -> Path:
        """Resolve the native solution filename for a named case and iteration.

        Args:
            case (str): Registered load-case name selecting the saved or current finite-element
                result.
            iteration (int): Iteration index associated with the saved or current model state.

        Returns:
            Path: Solution archive path ending in result_CASE_iter_ITERATION.npz; existence is not
                checked.
        """
        return self.fea_folder / f"result_{case}_iter_{iteration}.npz"

    def fea_iterations(self) -> tuple[int, ...]:
        """List iterations with an archived finite-element model.

        Returns:
            tuple[int, ...]: List iterations with an archived finite-element model.
        """
        return tuple(
            sorted(
                int(match[1])
                for path in self.fea_folder.glob("femodel_*.npz")
                if (match := re.fullmatch(r"femodel_(\d+)\.npz", path.name))
            )
        )

    def deformation_cases(self, iteration: int | None = None) -> tuple[str, ...]:
        """Return archived load-case names in their recorded order.

        Returns:
            tuple[str, ...]: Archived load-case names in their recorded order.
        """
        scene = self.snapshot(self.completed_iteration if iteration is None else iteration)
        return scene.cases if scene else ()

    def deformation_mesh(self, case: str, iteration: int) -> Any | None:
        """Reconstruct the assembly surface for a completed load case.

        Args:
            case (str): Registered load-case name.
            iteration (int): One-based history row identifying the solved mesh.

        Returns:
            pv.PolyData | None: Deformed exterior of all instances, or None if unavailable.
        """
        scene = self.snapshot(iteration)
        return scene.deformation_mesh(case) if scene else None

    def snapshot(self, iteration: int) -> Snapshot | None:
        """Read the VTM index once per selected iteration."""
        if self._snapshot_iteration != iteration:
            path = snapshot_path(self.log_folder, iteration)
            if not path.is_file():
                return None
            self._snapshot = Snapshot(path)
            self._snapshot_iteration = iteration
        return self._snapshot

    def design_components(self) -> tuple[tuple[str, Any], ...]:
        """Restore native interfaces for component-specific exports."""
        params = self.initialize_params()
        return tuple(design_components(params)) if params is not None else ()

    def visualizable_components(self, iteration: int | None = None) -> tuple[tuple[str, SavedComponent], ...]:
        """List design views recorded in the selected snapshot."""
        scene = self.snapshot(self.completed_iteration if iteration is None else iteration)
        return tuple((item.category, item) for item in scene.components.values()) if scene else ()

    def design_view_component(self, category: str, name: str, iteration: int) -> SavedComponent:
        """Select a component's saved meshes for one completed iteration."""
        scene = self.snapshot(iteration)
        if scene is None:
            raise FileNotFoundError(snapshot_path(self.log_folder, iteration))
        return scene.components[category, name]


@dataclass(frozen=True)
class IterationModel:
    """Reference to one saved finite-element model and optional load case."""

    folder: str
    iteration: int
    case: str | None = None

    @property
    def model_path(self) -> Path:
        """Resolve this snapshot's saved finite-element model path.

        Returns:
            Path: Native model archive associated with the snapshot iteration.
        """
        return OptimizationArchive(self.folder).fea_model_path(self.iteration)

    @property
    def result_path(self) -> Path | None:
        """Resolve this snapshot's optional named load-case solution path.

        Returns:
            Path | None: Native solution archive path, or None when no case is selected.
        """
        if self.case is None:
            return None
        return OptimizationArchive(self.folder).fea_result_path(
            self.case, self.iteration
        )

    @staticmethod
    def iterations(folder: str) -> tuple[int, ...]:
        """List completed iterations with an available saved finite-element model.

        Args:
            folder (str): Directory containing the optimization run or archive.

        Returns:
            tuple[int, ...]: Available model iteration indices in increasing order.
        """
        return OptimizationArchive(folder).fea_iterations()

    def cases(self) -> tuple[str, ...]:
        """List load cases with an existing solution at this snapshot iteration.

        Returns:
            tuple[str, ...]: Available solution case names in archive registration order.
        """
        archive = OptimizationArchive(self.folder)
        index = archive.fea_folder / "load_cases.json"
        if not index.is_file():
            return ()
        return tuple(
            case
            for case in json.loads(index.read_text(encoding="utf-8"))
            if archive.fea_result_path(case, self.iteration).is_file()
        )


def load_solved_model(
    model_path: str | Path,
    result_path: str | Path,
) -> tuple[FEAController, StaticResult]:
    """Load a TorchFEA model and restore the load case used to compute its solution."""
    import torchfea

    controller = torchfea.load_model(str(model_path))
    result = torchfea.solver.StaticResult.load(str(result_path))
    controller.assembly.set_work_conditions(result.work_conditions)
    return controller, result


def last_completed_iteration(folder: str | Path) -> int:
    """Return a run's latest saved iteration without retaining an archive.

    Args:
        folder (str | Path): Directory containing the optimization run or archive.

    Returns:
        int: A run's latest saved iteration without retaining an archive.
    """
    return OptimizationArchive(folder).completed_iteration


def _import_controller(folder: Path) -> type[Any] | None:
    """Import the archived restart script under a path-specific module name.

    Args:
        folder (Path): Directory containing the optimization run or archive.

    Returns:
        type | None: ThisController declaration, or None when the script is missing or cannot be
            imported.
    """
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
