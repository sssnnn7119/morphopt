"""Geometry registration and fresh TorchFEA Assembly construction."""

from __future__ import annotations

from multiprocessing.pool import Pool
from pathlib import Path
from types import MappingProxyType

import pyvista
import torchfea

from ..protocols import Updatable
from .parts.base import BasePartDefinition
from .reference import ReferencePoint


class GeometryParams:
    """Own Part/reference-point definitions and build a fresh geometry Assembly."""

    def __init__(self) -> None:
        self._parts: dict[str, BasePartDefinition] = {}
        """Part definitions keyed by their stable output Part name."""
        self._reference_points: dict[str, ReferencePoint] = {}
        """Assembly-level reference-point definitions keyed by stable name."""
        self._element_names: dict[str, tuple[str, ...]] = {}
        """Validated element-family names derived from each registered Part."""
        self._iteration: int | None = None
        """Outer optimization iteration represented by current geometry caches."""
        self._torchfea_Assembly: torchfea.Assembly | None = None
        """Assembly generated from current Part and instance definitions."""
        self._meshes: tuple[pyvista.DataSet, ...] = ()
        """Cached visualization meshes built from all registered Parts."""
        self._initialized = False
        """Whether definition hooks and static Part state have been initialized."""

    @property
    def parts(self) -> MappingProxyType[str, BasePartDefinition]:
        """Return the read-only Part registry."""
        return MappingProxyType(self._parts)

    @property
    def reference_points(self) -> MappingProxyType[str, ReferencePoint]:
        """Return the read-only reference-point registry."""
        return MappingProxyType(self._reference_points)

    def define_parts(self) -> None:
        """Register all geometry Parts through :meth:`add_part`."""
        return None

    def add_part(self, part: BasePartDefinition) -> BasePartDefinition:
        """Register one uniquely named Part definition."""
        if part.part_name in self._parts:
            raise ValueError(f"Duplicate part name: {part.part_name}")
        self._parts[part.part_name] = part
        return part

    def define_reference_points(self) -> None:
        """Register all Assembly reference points through :meth:`add_reference_point`."""
        return None

    def add_reference_point(self, reference_point: ReferencePoint) -> ReferencePoint:
        """Register one uniquely named Assembly-level reference point."""
        if reference_point.name in self._reference_points:
            raise ValueError(f"Duplicate reference-point name: {reference_point.name}")
        self._reference_points[reference_point.name] = reference_point
        return reference_point

    def build_assembly(
        self,
        path_result: str | Path | None = None,
        pools: Pool | None = None,
    ) -> None:
        """Build Parts, instances and reference points into one new Assembly."""
        directory = Path(path_result) if path_result is not None else None
        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True)
        assembly = torchfea.Assembly()
        for part in self._parts.values():
            part_path = directory / part.part_name if directory is not None else None
            part.build_part(part_path, pools)
            assembly.add_part(part.get_part(), name=part.part_name)
            for instance in part.instances.values():
                instance.build_instance()
                assembly.add_instance(instance.get_instance(), name=instance.name)
        for reference_point in self._reference_points.values():
            reference_point.build_reference_point()
            assembly.add_reference_point(
                reference_point.get_reference_point(), name=reference_point.name
            )
        self._torchfea_Assembly = assembly

    def get_assembly(self) -> torchfea.Assembly:
        """Return the Assembly built by the most recent :meth:`build_assembly`."""
        if self._torchfea_Assembly is None:
            raise RuntimeError("Geometry Assembly has not been built")
        return self._torchfea_Assembly

    def get_design_owners(self) -> tuple[Updatable, ...]:
        """Return registered Parts that own editable geometry variables."""
        return tuple(part for part in self._parts.values() if isinstance(part, Updatable))

    def build_meshes(self) -> None:
        """Build and cache visual preview meshes for every registered Part."""
        meshes: list[pyvista.DataSet] = []
        for part in self._parts.values():
            part.build_meshes()
            meshes.extend(part.get_meshes())
        self._meshes = tuple(meshes)

    def get_meshes(self) -> tuple[pyvista.DataSet, ...]:
        """Return preview meshes created by :meth:`build_meshes`."""
        return self._meshes

    def initialize(self) -> None:
        """Run definition hooks and initialize all registered geometry objects."""
        self._parts.clear()
        self._reference_points.clear()
        self._element_names.clear()
        self.define_parts()
        self.define_reference_points()
        for part in self._parts.values():
            part.initialize()
            if part.element_names is not None:
                self._element_names[part.part_name] = part.element_names
        self._initialized = True

    def reinitialize(self, iteration: int) -> None:
        """Clear per-iteration Assembly and refresh each Part's runtime state."""
        self._iteration = int(iteration)
        self._torchfea_Assembly = None
        self._meshes = ()
        for part in self._parts.values():
            part.reinitialize(iteration)

    def save(self, folder_path: str | Path, iteration: int) -> None:
        """Persist each Part and reference-point state in the geometry log folder."""
        folder = Path(folder_path) / "geometry"
        folder.mkdir(parents=True, exist_ok=True)
        for part in self._parts.values():
            part.save(folder / part.part_name, iteration)
        for reference_point in self._reference_points.values():
            reference_point.save(folder / reference_point.name, iteration)

    def load(self, folder_path: str | Path, iteration: int) -> None:
        """Restore each Part and reference-point state from the geometry log folder."""
        folder = Path(folder_path) / "geometry"
        for part in self._parts.values():
            part.load(folder / part.part_name, iteration)
        for reference_point in self._reference_points.values():
            reference_point.load(folder / reference_point.name, iteration)
