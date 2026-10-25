"""Fixed geometry owns one cached TorchFEA mesh and its named sets."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import torchfea

from .base_part import BasePart

if TYPE_CHECKING:
    from multiprocessing.pool import Pool

__all__ = ["FixedPart"]


class FixedPart(BasePart):
    """Base for fixed mesh builders and importers.

    Subclasses implement ``build_part()``. The cached TorchFEA Part owns all
    set data; the properties below expose its containers without copying them.
    """

    def __init__(
        self, part_name: str | None = None, exterior_surface: str | None = None,
    ) -> None:
        super().__init__(part_name=part_name, exterior_surface=exterior_surface)
        self._part: torchfea.Part | None = None
        self._part_cache_key: object = None

    @BasePart.part_name.setter
    def part_name(self, value: str | None) -> None:
        self._part_name = str(value).strip() if value else ""
        self.clear_mesh_cache()

    def clear_mesh_cache(self) -> None:
        """Discard the mesh before rebuilding changed inputs."""
        self._part = None
        self._part_cache_key = None

    def initialize(self, *args: object, **kwargs: object) -> None:
        """Start initialization with a fresh mesh, including custom build inputs."""
        self.clear_mesh_cache()
        super().initialize(*args, **kwargs)

    def _mesh_cache_key(self) -> object:
        """Identify inputs whose changes require a new mesh."""
        return None

    def get_part(
        self, path_result: str | None = None, pools: Pool | None = None,
    ) -> torchfea.Part:
        """Reuse this geometry's mesh until its inputs change or it is cleared."""
        key = self._mesh_cache_key()
        if self._part is None or key != self._part_cache_key:
            self.clear_mesh_cache()
            self._part = self.build_part(path_result=path_result, pools=pools)
            self._part_cache_key = key
        return self._part

    @property
    def node_sets(self) -> dict[str, np.ndarray]:
        """Node sets owned by the cached mesh, built on first access."""
        return self.get_part().set_nodes

    @property
    def surface_sets(self):
        """The cached mesh's surface container."""
        return self.get_part().surfaces

    @property
    def element_sets(self) -> dict[str, np.ndarray]:
        """Named element sets owned by the cached mesh."""
        return self.get_part().set_elements

    @property
    def surface_set_names(self) -> tuple[str, ...]:
        return tuple(self.surface_sets.keys())

    @property
    def node_set_names(self) -> tuple[str, ...]:
        return tuple(self.node_sets)
