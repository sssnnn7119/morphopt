"""Shared lifecycle and backend state for all geometry Part definitions."""

from __future__ import annotations

from multiprocessing.pool import Pool
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

import pyvista
import torchfea

if TYPE_CHECKING:
    from .instance import InstanceDefinition


class BasePartDefinition:
    """Define one reusable TorchFEA Part and its Assembly instances.

    A Part definition owns immutable construction information and the backend
    ``torchfea.Part`` generated for the current optimization iteration.  Its
    instances are registered separately so one Part can be placed in an
    Assembly more than once without duplicating mesh data.
    """

    def __init__(
        self,
        part_name: str,
        *,
        element_names: tuple[str, ...] | None = None,
        exterior_surface: str = "extern",
    ) -> None:
        self._part_name = str(part_name)
        """Stable name used when registering the generated TorchFEA Part."""
        self._element_names = element_names
        """Optional names assigned to imported or generated element families."""
        self._exterior_surface = str(exterior_surface)
        """Surface-set name used as the exterior contact surface."""
        self._instances: dict[str, InstanceDefinition] = {}
        """Assembly instance definitions registered for this Part."""
        self._torchfea_Part: torchfea.Part | None = None
        """TorchFEA Part generated or imported for the current iteration."""
        self._meshes: tuple[pyvista.DataSet, ...] = ()
        """Cached visualization meshes built from this Part definition."""
        self._initialized = False
        """Whether static definition data and instance registrations are ready."""

    @property
    def part_name(self) -> str:
        """Return the stable name used in the backend Assembly."""
        return self._part_name

    @property
    def name(self) -> str:
        """Return the compatibility alias for :attr:`part_name`."""
        return self._part_name

    @property
    def element_names(self) -> tuple[str, ...] | None:
        """Return explicitly configured element-family names."""
        return self._element_names

    @property
    def exterior_surface(self) -> str:
        """Return the exterior surface-set name."""
        return self._exterior_surface

    @property
    def instances(self) -> MappingProxyType[str, InstanceDefinition]:
        """Return the read-only instance registry in registration order."""
        return MappingProxyType(self._instances)

    def define_instances(self) -> None:
        """Register Assembly instances for this Part.

        Subclasses override this hook and call :meth:`add_instance`.  A Part
        with no explicit registration receives one identity instance during
        :meth:`initialize`.
        """
        return None

    def add_instance(self, instance: InstanceDefinition) -> InstanceDefinition:
        """Register one uniquely named instance of this Part."""
        if instance.name in self._instances:
            raise ValueError(f"Duplicate instance name: {instance.name}")
        if instance.part_name != self._part_name:
            raise ValueError(
                f"Instance {instance.name!r} belongs to {instance.part_name!r}, "
                f"not Part {self._part_name!r}."
            )
        self._instances[instance.name] = instance
        return instance

    def build_part(self, path_result: Path | None = None, pools: Pool | None = None) -> None:
        """Create and cache the current backend Part.

        Concrete Part definitions implement their mesh-generation or import
        operation here.  ``path_result`` is the per-iteration geometry export
        directory and ``pools`` is reserved for geometry backends that support
        parallel meshing.
        """
        raise NotImplementedError

    def get_part(self) -> torchfea.Part:
        """Return the Part produced by the most recent :meth:`build_part`."""
        if self._torchfea_Part is None:
            raise RuntimeError(f"Part {self._part_name!r} has not been built.")
        return self._torchfea_Part

    def build_meshes(self) -> None:
        """Build preview meshes for this Part definition."""
        self._meshes = ()

    def get_meshes(self) -> tuple[pyvista.DataSet, ...]:
        """Return preview meshes created by :meth:`build_meshes`."""
        return self._meshes

    def export_model(self, path: str | Path, format: str) -> Path:
        """Export this Part's surface model to ``path``.

        Generated Parts override this interface with their native surface
        export.  Imported mesh Parts retain their source artifact instead.
        """
        raise NotImplementedError

    def initialize(self) -> None:
        """Prepare static registrations and create a default identity instance."""
        from .instance import InstanceDefinition

        self._instances.clear()
        self.define_instances()
        if not self._instances:
            self.add_instance(InstanceDefinition(self._part_name, self._part_name))
        self._initialized = True

    def reinitialize(self, iteration: int) -> None:
        """Clear data generated for one optimization iteration."""
        self._torchfea_Part = None
        self._meshes = ()

    def save(self, folder_path: str | Path, iteration: int) -> None:
        """Persist Part-owned state in the run log directory."""
        return None

    def load(self, folder_path: str | Path, iteration: int) -> None:
        """Restore Part-owned state from the run log directory."""
        return None
