"""Stable design-variable registration and transactional updates."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from morphopt._torch import torch
from morphopt.logging import get_logger

from .modelparams.params import Params
from .protocols import JsonObject, Updatable

logger = get_logger(__name__)
DesignCategory = Literal["geometry", "material", "load"]


@dataclass(frozen=True, order=True, slots=True)
class DesignKey:
    """Immutable identity of one design-variable owner.

    ``case_index`` is used only for load variables; geometry and material
    owners use ``None`` so their layout is shared by every load case.
    """

    category: DesignCategory
    target_name: str
    case_index: int | None = None


class DesignBlock:
    """A frozen slice of the global design vector.

    The block records the owner, stable key, flattened range and original
    shape.  It never recomputes the layout after :meth:`finalize`.
    """

    def __init__(self, key: DesignKey, owner: Updatable) -> None:
        self._key = key
        """Stable identifier for the registered design block."""
        self._owner = owner
        """Domain object that owns and applies this block."""
        self._start: int | None = None
        """Global vector start offset."""
        self._stop: int | None = None
        """Exclusive global vector stop offset."""
        self._size: int | None = None
        """Flattened number of local variables."""
        self._shape: tuple[int, ...] = ()
        """Original tensor shape for local values."""

    @property
    def key(self) -> DesignKey:
        """Return this block's stable key."""
        return self._key

    @property
    def owner(self) -> Updatable:
        """Return the owner bound to this block."""
        return self._owner

    def finalize(self, start: int, design_delta: torch.Tensor) -> None:
        """Freeze this block's offset and local tensor shape."""
        values = torch.as_tensor(design_delta)
        self._start = int(start)
        self._size = int(values.numel())
        self._stop = self._start + self._size
        self._shape = tuple(values.shape)

    def get_range(self) -> tuple[int, int]:
        """Return the half-open global vector range ``(start, stop)``."""
        if self._start is None or self._stop is None:
            raise RuntimeError("Design block has not been finalized")
        return self._start, self._stop

    def get_size(self) -> int:
        """Return the flattened number of variables in this block."""
        if self._size is None:
            raise RuntimeError("Design block has not been finalized")
        return self._size

    def compute_local_values(self, full_values: torch.Tensor) -> torch.Tensor:
        """Slice and reshape a global vector for this owner."""
        start, stop = self.get_range()
        return full_values[start:stop].reshape(self._shape)

    def signature(self) -> JsonObject:
        """Return the serializable layout signature used by checkpoints."""
        start, stop = self.get_range()
        return {
            "category": self._key.category,
            "target_name": self._key.target_name,
            "case_index": self._key.case_index,
            "start": start,
            "stop": stop,
            "shape": list(self._shape),
        }


class DesignRegistry:
    """Own the global variable layout and its update transaction.

    Registration collects owners before an immutable layout is frozen.
    Subsequent iterations only rebuild values and route trial/committed
    tensors through the existing blocks.
    """

    def __init__(self) -> None:
        self._pending_blocks: dict[DesignKey, DesignBlock] = {}
        """Owners awaiting layout finalization."""
        self._blocks: tuple[DesignBlock, ...] = ()
        """Frozen blocks in deterministic order."""
        self._block_by_key: dict[DesignKey, DesignBlock] = {}
        """Direct lookup for finalized blocks."""
        self._design_delta: torch.Tensor | None = None
        """Current flattened design delta."""
        self._iteration: int | None = None
        """Iteration associated with the current layout values."""
        self._finalized = False
        """Whether registration has been frozen."""

    def add_block(self, key: DesignKey, owner: Updatable) -> None:
        """Register a non-empty owner before layout finalization."""
        if self._finalized:
            raise RuntimeError("Design layout is already finalized")
        if key in self._pending_blocks:
            raise ValueError(f"Duplicate design key: {key}")
        values = self._owner_delta(owner)
        if values.numel() == 0:
            return
        self._pending_blocks[key] = DesignBlock(key, owner)

    def finalize(self) -> None:
        """Sort owners deterministically and freeze all global offsets."""
        offset = 0
        ordered = sorted(
            self._pending_blocks.values(), key=lambda block: self._sort_key(block.key)
        )
        for block in ordered:
            block.finalize(offset, self._owner_delta(block.owner))
            offset += block.get_size()
        self._blocks = tuple(ordered)
        self._block_by_key = {block.key: block for block in ordered}
        self._finalized = True

    def build_design_delta(self) -> None:
        """Build the current leaf vector and expose local views to owners."""
        self._require_finalized()
        for block in self._blocks:
            block.owner.build_design_delta()
        local_values = [
            self._owner_delta(block.owner).reshape(-1) for block in self._blocks
        ]
        if not local_values:
            self._design_delta = torch.zeros(0, dtype=torch.float32, requires_grad=True)
            return
        for block, values in zip(self._blocks, local_values):
            if values.numel() != block.get_size():
                raise ValueError(f"Design layout changed for {block.key}")
        joined = (
            torch.cat([values.detach() for values in local_values])
            .clone()
            .requires_grad_(True)
        )
        self._design_delta = joined
        for block in self._blocks:
            local = block.compute_local_values(joined)
            block.owner.set_design_delta(local)

    def get_design_delta(self) -> torch.Tensor:
        """Return the latest global design vector."""
        if self._design_delta is None:
            raise RuntimeError("Design delta has not been built")
        return self._design_delta

    def get_blocks(self) -> tuple[DesignBlock, ...]:
        """Return all frozen blocks in stable update order."""
        return self._blocks

    def get_block_range(self, key: DesignKey) -> tuple[int, int]:
        """Return one owner's global range."""
        return self._block_by_key[key].get_range()

    def get_owner(self, key: DesignKey) -> Updatable:
        """Return the owner bound to ``key``."""
        return self._block_by_key[key].owner

    def has_geometry_variables(self) -> bool:
        """Report whether the registry contains editable geometry."""
        return any(block.key.category == "geometry" for block in self._blocks)

    def compute_block_values(
        self, full_values: torch.Tensor
    ) -> dict[DesignKey, torch.Tensor]:
        """Purely split a global vector into owner-shaped tensors."""
        self._validate_full_values(full_values)
        return {
            block.key: block.compute_local_values(full_values) for block in self._blocks
        }

    def update_assembly(
        self,
        full_design_delta: torch.Tensor,
        categories: set[DesignCategory] | None = None,
    ) -> None:
        """Apply a trial vector to selected owners without committing it."""
        self._validate_full_values(full_design_delta)
        for block in self._blocks:
            if categories is not None and block.key.category not in categories:
                continue
            block.owner.update_assembly(block.compute_local_values(full_design_delta))

    def apply_design_delta(self, changes: Mapping[DesignKey, torch.Tensor]) -> None:
        """Commit all supplied changes as one rollback-safe transaction."""
        self._require_finalized()
        snapshots = self._snapshot_parameters()
        try:
            for block in self._blocks:
                if block.key not in changes:
                    continue
                block.owner.apply_design_delta(changes[block.key])
        except Exception:
            self._restore_parameters(snapshots)
            raise

    def initialize(self, params: Params) -> None:
        """Collect owners from Params, freeze layout and build initial values."""
        self._pending_blocks.clear()
        self._blocks = ()
        self._block_by_key.clear()
        self._finalized = False
        self._collect_geometry_owners(params)
        self._collect_material_owners(params)
        self._collect_load_owners(params)
        self.finalize()
        self.build_design_delta()

    def reinitialize(self, iteration: int) -> None:
        """Associate the next vector with an outer iteration."""
        self._iteration = int(iteration)
        self._design_delta = None

    def save(self, folder_path: str | Path, iteration: int) -> None:
        """Persist the stable layout signature for checkpoint validation."""
        folder = Path(folder_path)
        folder.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "iteration": int(iteration),
            "blocks": [block.signature() for block in self._blocks],
        }
        (folder / "design_registry.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    def load(self, folder_path: str | Path, iteration: int) -> None:
        """Validate a checkpoint layout against the current task definition."""
        path = Path(folder_path) / "design_registry.json"
        if not path.exists():
            raise FileNotFoundError(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        saved = payload.get("blocks", [])
        current = [block.signature() for block in self._blocks]
        if saved and saved != current:
            raise ValueError("Design registry layout does not match checkpoint")
        self._iteration = int(iteration)

    def _collect_geometry_owners(self, params: Params) -> None:
        geometry = params.get_geometry()
        owners = geometry.get_design_owners()
        for owner in owners:
            self.add_block(DesignKey("geometry", str(owner.name)), owner)

    def _collect_material_owners(self, params: Params) -> None:
        materials = params.get_materials()
        owners = materials.get_design_owners()
        for owner in owners:
            self.add_block(DesignKey("material", str(owner.name)), owner)

    def _collect_load_owners(self, params: Params) -> None:
        fea = params.get_fea()
        owners = fea.get_design_owners()
        for name, case_index, owner in owners:
            self.add_block(DesignKey("load", str(name), case_index), owner)

    def _owner_delta(self, owner: Updatable) -> torch.Tensor:
        values = owner.get_design_delta()
        values = torch.as_tensor(values)
        # Newly constructed owners expose an empty trial cache until their
        # first ``build_design_delta()`` call.  Their committed parameter
        # shape is still a valid layout declaration and must be registered
        # before the first build can occur.
        if values.numel() == 0:
            parameters = torch.as_tensor(owner.get_parameters())
            if parameters.numel() > 0:
                return torch.zeros_like(parameters)
        return values

    def _sort_key(self, key: DesignKey) -> tuple[int, str, int]:
        category_order = {"geometry": 0, "material": 1, "load": 2}
        return (
            category_order[key.category],
            key.target_name,
            -1 if key.case_index is None else key.case_index,
        )

    def _validate_full_values(self, values: torch.Tensor) -> None:
        self._require_finalized()
        expected = sum(block.get_size() for block in self._blocks)
        vector = torch.as_tensor(values)
        if vector.ndim != 1 or vector.numel() != expected:
            raise ValueError(
                f"Expected a flat design vector of length {expected}, got {tuple(vector.shape)}"
            )
        if not torch.isfinite(vector).all():
            raise ValueError("Design vector contains non-finite values")

    def _require_finalized(self) -> None:
        if not self._finalized:
            raise RuntimeError("Design registry has not been finalized")

    def _snapshot_parameters(self) -> dict[DesignKey, torch.Tensor]:
        snapshots: dict[DesignKey, torch.Tensor] = {}
        for block in self._blocks:
            snapshots[block.key] = (
                torch.as_tensor(block.owner.get_parameters()).detach().clone()
            )
        return snapshots

    def _restore_parameters(self, snapshots: Mapping[DesignKey, torch.Tensor]) -> None:
        for block in self._blocks:
            if block.key in snapshots:
                block.owner.set_parameters(snapshots[block.key])
