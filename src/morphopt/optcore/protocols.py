"""Small structural protocols shared by the V4 object graph."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import pyvista

from morphopt._torch import torch

JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
"""JSON-compatible scalar, sequence, or mapping value."""

JsonObject = dict[str, JsonValue]
"""JSON-compatible object mapping string keys to values."""


@runtime_checkable
class Initializable(Protocol):
    """Lifecycle protocol for one-time and per-iteration initialization."""

    def initialize(self, *args: Any, **kwargs: Any) -> None:
        """Create static runtime state."""
        ...

    def reinitialize(self, *args: Any, **kwargs: Any) -> None:
        """Refresh state for one iteration."""
        ...


@runtime_checkable
class Visualizable(Protocol):
    """Protocol for cached preview meshes.

    ``build_meshes`` is the state-changing operation; ``get_meshes`` only
    reads a cache that has already been built.
    """

    def build_meshes(self, *args: Any, **kwargs: Any) -> None:
        """Build and cache preview meshes."""
        ...

    def get_meshes(self, *args: Any, **kwargs: Any) -> tuple[pyvista.DataSet, ...]:
        """Read already-cached preview meshes."""
        ...


@runtime_checkable
class Persistable(Protocol):
    """Protocol for versioned checkpoint persistence."""

    def save(self, folder_path: str | Path, iteration: int) -> None:
        """Persist state into a checkpoint directory."""
        ...

    def load(self, folder_path: str | Path, iteration: int) -> None:
        """Restore state from a checkpoint directory."""
        ...


@runtime_checkable
class Updatable(Protocol):
    """Protocol for an owner participating in Registry transactions.

    Owners keep their committed parameters and backend references.  The
    registry supplies detached trial deltas and commits validated changes.
    """

    def get_parameters(self) -> torch.Tensor:
        """Read committed owner parameters."""
        ...

    def set_parameters(self, parameters: torch.Tensor) -> None:
        """Replace committed owner parameters."""
        ...

    def build_design_delta(self) -> None:
        """Build a local zero-based trial delta."""
        ...

    def get_design_delta(self) -> torch.Tensor:
        """Read the current local trial delta."""
        ...

    def update_assembly(self, design_delta: torch.Tensor) -> None:
        """Apply a trial delta to cached backend objects."""
        ...

    def apply_design_delta(self, changes: torch.Tensor) -> None:
        """Commit validated changes to the owner."""
        ...
