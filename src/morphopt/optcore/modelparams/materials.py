"""Material definition processor in the Geometry → Materials → FEA pipeline."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

from ..protocols import Updatable
import pyvista
import torchfea
from .material.base import BaseMaterialInterface
from .material.models import MaterialModels


class MaterialsParams:
    """Register material definitions and attach them to a generated Assembly."""

    def __init__(self) -> None:
        self._materials: dict[str, BaseMaterialInterface] = {}
        """Material definitions keyed by their stable registered names."""
        self._torchfea_Assembly: torchfea.Assembly | None = None
        """Assembly currently receiving native material assignments."""
        self._iteration: int | None = None
        """Outer optimization iteration represented by runtime references."""
        self._meshes: tuple[pyvista.DataSet, ...] = ()
        """Cached combined material-field visualization meshes."""
        self._initialized = False
        """Whether ``define_materials()`` has populated the registry."""

    @property
    def materials(self) -> MappingProxyType[str, BaseMaterialInterface]:
        """Return the read-only material registry."""
        return MappingProxyType(self._materials)

    @property
    def materialmodels(self) -> type[MaterialModels]:
        """Return the typed material-model constructor namespace."""
        return MaterialModels

    def define_materials(self) -> None:
        """Register task-specific material definitions with ``add_material()``."""
        return None

    def add_material(
        self,
        material: BaseMaterialInterface,
        name: str | None = None,
    ) -> BaseMaterialInterface:
        """Register one material definition under a stable unique name."""
        material_name = str(name or material.name)
        if material_name in self._materials:
            raise ValueError(f"Material {material_name!r} is already registered")
        self._materials[material_name] = material
        return material

    def names_for_part(self, part_name: str) -> tuple[str, ...]:
        """Read names of material definitions targeting ``part_name``."""
        return tuple(
            name
            for name, material in self._materials.items()
            if material.part_name == part_name
        )

    def get_design_owners(self) -> tuple[BaseMaterialInterface, ...]:
        """Read material fields participating in the optimization registry."""
        return tuple(
            material
            for material in self._materials.values()
            if isinstance(material, Updatable)
        )

    def initialize(self) -> None:
        """Build definition state and let the task register its materials."""
        self._materials.clear()
        self.define_materials()
        for material in self._materials.values():
            material.initialize()
        self._initialized = True

    def reinitialize(self, iteration: int, assembly: torchfea.Assembly) -> None:
        """Bind a freshly generated Assembly to every registered material."""
        self._iteration = int(iteration)
        self._torchfea_Assembly = assembly
        for material in self._materials.values():
            material.reinitialize(iteration, assembly)

    def build_materials(self) -> None:
        """Build every native constitutive object for the current Assembly."""
        for material in self._materials.values():
            material.build_material()

    def assign_materials(self) -> None:
        """Write all built native materials and densities to their elements."""
        for material in self._materials.values():
            material.assign_material()

    def build_meshes(self) -> None:
        """Build and collect the material preview caches."""
        meshes: list[pyvista.DataSet] = []
        for material in self._materials.values():
            material.build_meshes()
            meshes.extend(material.get_meshes())
        self._meshes = tuple(meshes)

    def get_meshes(self) -> tuple[pyvista.DataSet, ...]:
        """Read the already-built combined material preview cache."""
        return self._meshes

    def plot(
        self,
        plotter: pyvista.Plotter,
        meshes: tuple[pyvista.DataSet, ...] | None = None,
    ) -> pyvista.Plotter:
        """Draw the supplied or cached material preview meshes."""
        for mesh in self._meshes if meshes is None else meshes:
            plotter.add_mesh(mesh)
        return plotter

    def save(self, folder_path: str | Path, iteration: int) -> None:
        """Save every registered material's iteration data."""
        for material in self._materials.values():
            material.save(folder_path, iteration)

    def load(self, folder_path: str | Path, iteration: int) -> None:
        """Load every registered material's iteration data."""
        for material in self._materials.values():
            material.load(folder_path, iteration)
