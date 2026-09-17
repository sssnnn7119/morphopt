"""Updater composition and local sensitivity objective."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from morphopt._torch import torch

from ..protocols import Updatable
from .terms import ConstraintTerm

if TYPE_CHECKING:
    from ..design_registry import DesignKey, DesignRegistry
    from ..modelparams.params import Params


class LocalSensitivityObjective:
    """Linear local objective produced from one Registry sensitivity block."""

    def __init__(self, sensitivity: torch.Tensor | None = None) -> None:
        self._sensitivity = torch.as_tensor(
            sensitivity if sensitivity is not None else torch.zeros(0)
        ).detach()
        """Fixed local linear objective coefficients."""

    def evaluate(self, parameters: torch.Tensor) -> torch.Tensor:
        """Evaluate the fixed linear expansion at trial parameters."""
        values = torch.as_tensor(parameters)
        if values.numel() != self._sensitivity.numel():
            return torch.zeros((), dtype=values.dtype, device=values.device)
        return (values.reshape(-1) * self._sensitivity.reshape(-1)).sum()


class BaseUpdater:
    """Common lifecycle for one updateable owner and its local optimizer."""

    def __init__(
        self,
        name: str,
        owner: Updatable | None = None,
        *,
        device: str = "cpu",
        step_size: float = 1e-2,
    ) -> None:
        self._name = str(name)
        """Stable updater name shown in the model tree."""
        self._owner = owner
        """Domain object whose design variables this updater changes."""
        self._device = str(device)
        """Device used by this updater's local optimization tensors."""
        self._step_size = float(step_size)
        """Local first-order step size used by the default updater."""
        self._iteration: int | None = None
        """Current outer optimization iteration."""
        self._sensitivities: Mapping[DesignKey, torch.Tensor] = {}
        """Sensitivity blocks received from Analyzer."""
        self._changes: dict[DesignKey, torch.Tensor] = {}
        """Proposed committed changes by DesignKey."""
        self._local_objective: LocalSensitivityObjective | None = None
        """Local linearized objective."""
        self._registry: DesignRegistry | None = None
        """Design registry that owns the updater's stable block key."""
        self._owner_key: DesignKey | None = None
        """DesignKey selected for the bound owner."""
        self._initialized = False
        """Updater lifecycle initialization state."""

    @property
    def name(self) -> str:
        """Return the updater name."""
        return self._name

    @property
    def device(self) -> str:
        """Return the updater-local device."""
        return self._device

    def initialize(
        self, params: Params | None = None, registry: DesignRegistry | None = None
    ) -> None:
        """Bind static problem and Registry references."""
        self._registry = registry
        self._initialized = True

    def reinitialize(
        self, iteration: int, sensitivities: Mapping[DesignKey, torch.Tensor]
    ) -> None:
        """Select this owner's sensitivity block for one iteration."""
        self._iteration = int(iteration)
        self._sensitivities = dict(sensitivities)
        self._changes = {}
        self._local_objective = None
        self._owner_key = None
        owner_name = str(self._owner.name)
        for key, value in self._sensitivities.items():
            if str(key.target_name) == owner_name:
                self._owner_key = key
                self._local_objective = LocalSensitivityObjective(value)
                break

    def compute_terms(self) -> tuple[ConstraintTerm, ...]:
        """Compute local constraint/regularization terms."""
        # TODO: Evaluate this updater's local constraints and regularizers.
        return ()

    def closure(self, parameters: torch.Tensor) -> torch.Tensor:
        """Evaluate the updater's local optimization closure."""
        if self._local_objective is None:
            return torch.zeros((), dtype=parameters.dtype, device=parameters.device)
        return self._local_objective.evaluate(parameters)

    def update(self) -> None:
        """Solve the local update problem and cache proposed changes."""
        if (
            self._owner_key is None
            or self._local_objective is None
            or self._owner is None
        ):
            return
        # Local optimization acts on the owner definition held by Params.
        # ``get_design_delta()`` remains the sensitivity graph workspace and
        # is used only as a shape fallback for lightweight owners.
        current = torch.as_tensor(self._owner.get_parameters())
        sensitivity = self._local_objective._sensitivity.to(
            device=current.device, dtype=current.dtype
        )
        change = (-self._step_size * sensitivity.reshape(current.shape)).detach()
        self._changes[self._owner_key] = change
        return

    def get_change(self) -> torch.Tensor | None:
        """Read the first proposed local change, when present."""
        return next(iter(self._changes.values()), None)

    def get_local_objective(self) -> LocalSensitivityObjective | None:
        """Read the fixed local sensitivity objective."""
        return self._local_objective

    def get_changes(self) -> Mapping[DesignKey, torch.Tensor]:
        """Read all proposed changes keyed by DesignKey."""
        return dict(self._changes)

    def save(self, folder_path: str, iteration: int) -> None:
        """Persist optimizer and local constraint state."""
        # TODO: Persist optimizer state and local constraint status.
        return

    def load(self, folder_path: str, iteration: int) -> None:
        """Restore optimizer and local constraint state."""
        # TODO: Restore optimizer state and local constraint status.
        return


class UpdaterEntry:
    """Named binding between one updater and one updateable owner."""

    def __init__(self, name: str, updater: BaseUpdater) -> None:
        self._name = str(name)
        """Stable entry name used for lookup and persistence."""
        self._updater = updater
        """Concrete updater bound by this entry."""

    @property
    def name(self) -> str:
        """Return the entry name."""
        return self._name

    @property
    def updater(self) -> BaseUpdater:
        """Return the updater bound by this entry."""
        return self._updater

    def validate(self, owner: Updatable | None = None) -> None:
        """Validate that an optional owner matches the binding."""
        if (
            owner is not None
            and self._updater._owner is not None
            and owner is not self._updater._owner
        ):
            raise ValueError(f"Updater {self._name} is bound to a different owner")


class Updaters:
    """Register and dispatch any number of independent updater objects."""

    def __init__(
        self, entries: Iterable[UpdaterEntry] = (), *, device: str = "cpu"
    ) -> None:
        self._entries = list(entries)
        """Ordered updater entries in the optimization problem."""
        self._device = str(device)
        """Default device passed to updater-local computations."""
        self._changes: dict[DesignKey, torch.Tensor] = {}
        """Merged changes produced by all updaters."""
        self._initialized = False
        """Collection lifecycle initialization state."""

    @property
    def entries(self) -> tuple[UpdaterEntry, ...]:
        """Return registered updater entries."""
        return tuple(self._entries)

    @property
    def device(self) -> str:
        """Return the default updater device."""
        return self._device

    def define_updaters(self) -> None:
        """Task hook for registering updater entries."""
        # TODO: User task definitions call add_updater() here.
        return

    def add_updater(
        self, updater: BaseUpdater, name: str | None = None
    ) -> UpdaterEntry:
        """Register one updater and return its entry."""
        entry = UpdaterEntry(name or updater.name, updater)
        self._entries.append(entry)
        return entry

    def initialize(
        self, params: Params | None = None, registry: DesignRegistry | None = None
    ) -> None:
        """Initialize all registered updater objects."""
        if not self._entries:
            self.define_updaters()
        for entry in self._entries:
            # The collection owns the updater device policy.  Individual
            # updater classes still expose ``device`` for diagnostics and
            # may use it to place their local tensors/optimizers.
            entry.updater._device = self._device
            entry.updater.initialize(params, registry)
        self._initialized = True

    def reinitialize(
        self, iteration: int, sensitivities: Mapping[DesignKey, torch.Tensor]
    ) -> None:
        """Distribute current block sensitivities to every updater."""
        self._changes = {}
        for entry in self._entries:
            entry.updater.reinitialize(iteration, sensitivities)

    def update(self) -> None:
        """Run all local updates and merge their proposed changes."""
        for entry in self._entries:
            entry.updater.update()
            self._changes.update(entry.updater.get_changes())

    def get_changes(self) -> Mapping[DesignKey, torch.Tensor]:
        """Read the merged change mapping."""
        return dict(self._changes)

    def save(self, folder_path: str, iteration: int) -> None:
        """Persist every updater's state."""
        for entry in self._entries:
            entry.updater.save(folder_path, iteration)

    def load(self, folder_path: str, iteration: int) -> None:
        """Restore every updater's state."""
        for entry in self._entries:
            entry.updater.load(folder_path, iteration)
