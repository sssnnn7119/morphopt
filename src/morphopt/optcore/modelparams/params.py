"""Unified Params pipeline: Geometry → Materials → FEA."""

from __future__ import annotations

import json
from multiprocessing.pool import Pool
from pathlib import Path
from typing import Callable, TypeVar

from morphopt.logging import get_logger
import pyvista
import torchfea
from .fea import FEAParams
from .geometry import GeometryParams
from .materials import MaterialsParams

logger = get_logger(__name__)
RequiredValue = TypeVar("RequiredValue")


class Params:
    """Create and process the complete problem Assembly.

    Params is the sole pipeline coordinator for Geometry, Materials and FEA;
    those processors remain independent and communicate through Assembly.
    """

    def __init__(
        self,
        geometry_factory: Callable[[], GeometryParams] = GeometryParams,
        materials_factory: Callable[[], MaterialsParams] = MaterialsParams,
        fea_factory: Callable[[], FEAParams] = FEAParams,
    ) -> None:
        self._geometry_factory = geometry_factory
        """Factory for independent geometry definitions."""
        self._materials_factory = materials_factory
        """Factory for independent material definitions."""
        self._fea_factory = fea_factory
        """Factory for load and boundary definitions."""
        self._geometry: GeometryParams | None = None
        """Geometry processor for the current problem."""
        self._materials: MaterialsParams | None = None
        """Material processor for the current problem."""
        self._fea: FEAParams | None = None
        """FEA component and load-step processor."""
        self._iteration: int | None = None
        """Current outer optimization iteration."""
        self._torchfea_Assembly: torchfea.Assembly | None = None
        """Shared backend Assembly produced by the pipeline."""
        self._initialized = False
        """Params lifecycle initialization state."""

    @property
    def geometry_factory(self) -> Callable[[], GeometryParams]:
        """Return the GeometryParams factory."""
        return self._geometry_factory

    @property
    def materials_factory(self) -> Callable[[], MaterialsParams]:
        """Return the MaterialsParams factory."""
        return self._materials_factory

    @property
    def fea_factory(self) -> Callable[[], FEAParams]:
        """Return the FEAParams factory."""
        return self._fea_factory

    def build_assembly(
        self,
        path_result: str | Path | None = None,
        pools: Pool | None = None,
    ) -> None:
        """Run the Geometry → Materials → FEA assembly pipeline."""
        self._require_initialized()
        assert self._geometry is not None and self._materials is not None and self._fea is not None
        self._geometry.build_assembly(path_result, pools)
        self._torchfea_Assembly = self._geometry.get_assembly()
        self._materials.reinitialize(self._iteration or 0, self._torchfea_Assembly)
        self._materials.build_materials()
        self._materials.assign_materials()
        self._fea.reinitialize(self._iteration or 0, self._torchfea_Assembly)
        self._fea.build_components()
        self._fea.assign_components()

    def get_geometry(self) -> GeometryParams:
        """Return initialized GeometryParams."""
        return self._require(self._geometry, "GeometryParams")

    def get_materials(self) -> MaterialsParams:
        """Return initialized MaterialsParams."""
        return self._require(self._materials, "MaterialsParams")

    def get_fea(self) -> FEAParams:
        """Return initialized FEAParams."""
        return self._require(self._fea, "FEAParams")

    def get_assembly(self) -> torchfea.Assembly | None:
        """Read the latest complete Assembly reference."""
        return self._torchfea_Assembly

    def export_problem_data(self, target_path: str | Path) -> Path:
        """Export a user-readable problem manifest to ``target_path``."""
        path = Path(target_path)
        path.mkdir(parents=True, exist_ok=True)
        (path / "params.json").write_text(json.dumps({"iteration": self._iteration}, indent=2), encoding="utf-8")
        # TODO: Export Assembly and all processor metadata in the agreed V4 schema.
        return path

    def initialize(self) -> None:
        """Create processors and run their static definition hooks."""
        self._geometry = self._geometry_factory()
        self._materials = self._materials_factory()
        self._fea = self._fea_factory()
        self._geometry.initialize()
        self._materials.initialize()
        self._fea.initialize()
        self._initialized = True

    def reinitialize(self, iteration: int) -> None:
        """Set the iteration and clear the previous Assembly reference."""
        self._iteration = int(iteration)
        self._torchfea_Assembly = None
        assert self._geometry is not None and self._materials is not None and self._fea is not None
        self._geometry.reinitialize(iteration)
        self._materials.reinitialize(iteration, None)
        self._fea.reinitialize(iteration, None)

    def build_meshes(self) -> None:
        """Build preview caches across all three processors."""
        assert self._geometry is not None and self._materials is not None and self._fea is not None
        self._geometry.build_meshes()
        self._materials.build_meshes()
        self._fea.build_meshes()

    def get_meshes(self) -> tuple[pyvista.DataSet, ...]:
        """Read the combined preview cache."""
        assert self._geometry is not None and self._materials is not None and self._fea is not None
        meshes: list[pyvista.DataSet] = []
        for processor in (self._geometry, self._materials, self._fea):
            meshes.extend(processor.get_meshes())
        return tuple(meshes)

    def save(self, folder_path: str | Path, iteration: int) -> None:
        """Delegate checkpoint persistence to all processors."""
        folder = Path(folder_path)
        folder.mkdir(parents=True, exist_ok=True)
        assert self._geometry is not None and self._materials is not None and self._fea is not None
        self._geometry.save(folder, iteration)
        self._materials.save(folder, iteration)
        self._fea.save(folder, iteration)

    def load(self, folder_path: str | Path, iteration: int) -> None:
        """Delegate checkpoint loading to all processors."""
        assert self._geometry is not None and self._materials is not None and self._fea is not None
        self._geometry.load(folder_path, iteration)
        self._materials.load(folder_path, iteration)
        self._fea.load(folder_path, iteration)

    def _validate_assembly(self, assembly: torchfea.Assembly) -> None:
        # TODO: Validate names, material coverage and component references once
        # concrete TorchFEA objects are connected.
        return None

    def _require_initialized(self) -> None:
        if not self._initialized:
            self.initialize()

    @staticmethod
    def _require(value: RequiredValue | None, name: str) -> RequiredValue:
        if value is None:
            raise RuntimeError(f"{name} has not been initialized")
        return value
