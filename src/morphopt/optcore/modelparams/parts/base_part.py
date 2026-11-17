"""Base component for a TorchFEA Part and its Instance declarations."""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import TYPE_CHECKING

import torchfea

from ..base_model_component import BaseModelComponent

if TYPE_CHECKING:
    from multiprocessing.pool import Pool

__all__ = ["BasePart"]


def _as_pose(value: Sequence[float]) -> list[float]:
    """Validate a TorchFEA pose ``[tx, ty, tz, rx, ry, rz]``.

    Args:
        value (Sequence[float]): Value assigned to or evaluated for the selected field.

    Returns:
        list[float]: Validate a TorchFEA pose ``[tx, ty, tz, rx, ry, rz]``.
    """
    pose = [float(item) for item in value]
    if len(pose) != 6:
        raise ValueError(
            "translations_rotations must have exactly 6 components: "
            "[tx, ty, tz, rx, ry, rz]."
        )
    return pose


class BasePart(BaseModelComponent):
    """One TorchFEA Part with its Instance declarations.

    Subclasses implement :meth:`build_part` and may override
    :meth:`define_instance`.  Instance placement is always declared inside
    the Part class with :meth:`add_instance`.
    """

    is_variable: bool = False
    """Whether optimization may change this Part's geometry or mesh.

    Fixed-mesh material optimization does not make a Part variable.
    """

    def pathlog_required(self) -> list[str]:
        """Return the log directory used by this geometry component.

        Returns:
            list[str]: Relative log subdirectory names required before persistence.
        """
        return ["geometry"]

    def __init__(
        self,
        part_name: str | None = None,
        exterior_surface: str | None = None,
    ) -> None:
        """Initialize BasePart and its configuration state.

        Args:
            part_name (str | None): Registered Part name referenced by instances, loads, or material
                assignments.
            exterior_surface (str | None): Name assigned to the Part's exterior surface selection.
        """
        super().__init__()
        self._name: str = ""
        """Registration name inside the owning GeometryParams collection."""

        self._part_name: str = str(part_name).strip() if part_name else ""
        """Explicit Part name; empty falls back to the registration name."""

        self.exterior_surface: str | None = (
            str(exterior_surface).strip() if exterior_surface else None
        )
        """Surface set drawn by default for Part mesh and deformation visualization."""

        self._instance_definitions: list[tuple[str, str, list[float]]] = []
        """Declared ``(part_name, instance_name, pose)`` triples."""

    @property
    def name(self) -> str:
        """Registration name inside the GeometryParams collection.

        Returns:
            str: Registration name inside the GeometryParams collection.
        """
        return self._name

    @property
    def part_name(self) -> str:
        """Name of the Part inside the TorchFEA Assembly.

        Returns:
            str: Name of the Part inside the TorchFEA Assembly.
        """
        name = self._part_name or self._name
        if not name:
            raise ValueError(
                f"{type(self).__name__} has no part name; pass part_name or "
                "register it with GeometryParams.add_interface(name=...)."
            )
        return name

    @part_name.setter
    def part_name(self, value: str | None) -> None:
        """Set the Part name referenced by the assembly instances.

        Args:
            value (str | None): New Part name referenced by the assembly instances.
        """
        self._part_name = str(value).strip() if value else ""

    @property
    def instance_names(self) -> list[str]:
        """Names declared by :meth:`define_instance`.

        Returns:
            list[str]: Names declared by :meth:`define_instance`.
        """
        self._ensure_instance_definitions()
        return [name for _part_name, name, _pose in self._instance_definitions]

    def _ensure_instance_definitions(self) -> None:
        """Invoke the instance declaration hook when no instance definitions have been registered."""
        if not self._instance_definitions:
            self.define_instance()

    def define_instance(self) -> None:
        """Declare the default identity Instance for this Part."""
        self.add_instance(self.part_name, self.part_name, [0.0] * 6)

    def add_instance(
        self,
        part_name: str,
        instance_name: str,
        translations_rotations: list[float],
    ) -> None:
        """Declare one Instance using ``[tx, ty, tz, rx, ry, rz]``.

        Args:
            part_name (str): Registered Part name referenced by instances, loads, or material
                assignments.
            instance_name (str): Registered Instance name in the assembly.
            translations_rotations (list[float]): Instance pose [tx, ty, tz, rx, ry, rz], with
                rotations represented by an exponential-coordinate vector in radians.
        """
        part_name = str(part_name).strip()
        instance_name = str(instance_name).strip()
        if not part_name:
            raise ValueError("part_name cannot be empty.")
        if not instance_name:
            raise ValueError("instance_name cannot be empty.")
        if any(
            name == instance_name
            for _declared_part, name, _pose in self._instance_definitions
        ):
            raise ValueError(f"Instance {instance_name!r} already exists.")
        self._instance_definitions.append(
            (part_name, instance_name, _as_pose(translations_rotations))
        )

    def __repr__(self) -> str:
        """Describe the registered Part and its instance declarations.

        Returns:
            str: Interface class, definition name, assembly Part name, and instance names.
        """
        try:
            part_name = self.part_name
        except ValueError:
            part_name = "<unregistered>"
        return (
            f"{type(self).__name__}(name={self._name!r}, "
            f"part={part_name!r}, instances={self.instance_names})"
        )

    def initialize(self, *args: object, **kwargs: object) -> None:
        """Declare Instances when absent, preserving existing declarations.

        Args:
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.
        """
        super().initialize(*args, **kwargs)
        self._ensure_instance_definitions()

    def build_part(
        self, path_result: str | None = None, pools: Pool | None = None
    ) -> torchfea.Part:
        """Create (or import) the Part owned by this interface.

        Args:
            path_result (str | None): Optimization result directory containing scripts and log
                subdirectories.
            pools (Pool | None): Optional multiprocessing pool for geometry preparation or export.

        Returns:
            torchfea.Part: TorchFEA Part with geometry-derived selections and the requested element
                order.
        """
        raise NotImplementedError

    def get_part(
        self, path_result: str | None = None, pools: Pool | None = None
    ) -> torchfea.Part:
        """Build the current geometry; FixedPart supplies mesh reuse separately.

        Args:
            path_result (str | None): Optimization result directory containing scripts and log
                subdirectories.
            pools (Pool | None): Optional multiprocessing pool for geometry preparation or export.

        Returns:
            torchfea.Part: Cached or newly generated TorchFEA Part for the current geometry
                configuration.
        """
        return self.build_part(path_result=path_result, pools=pools)

    def add_to_assembly(
        self,
        assembly: torchfea.Assembly,
        path_result: str | None = None,
        pools: Pool | None = None,
    ) -> torchfea.Part:
        """Add this Part and its declared Instances to ``assembly``.

        Args:
            assembly (torchfea.Assembly): TorchFEA assembly containing the registered Parts,
                Instances, loads, and reference points.
            path_result (str | None): Optimization result directory containing scripts and log
                subdirectories.
            pools (Pool | None): Optional multiprocessing pool for geometry preparation or export.

        Returns:
            torchfea.Part: Add this Part and its declared Instances to ``assembly``.
        """
        part = self.get_part(path_result=path_result, pools=pools)
        part_name = self.part_name

        if self.exterior_surface:
            part.exterior_surface = self.exterior_surface
        part.is_variable = self.is_variable
        assembly.add_part(part=part, name=part_name)

        for declared_part_name, instance_name, pose in self._instance_definitions:
            if declared_part_name != part_name:
                raise ValueError(
                    f"Instance {instance_name!r} refers to Part "
                    f"{declared_part_name!r}, but this interface builds "
                    f"{part_name!r}."
                )
            assembly.add_instance(
                instance=torchfea.Instance(
                    part_name=declared_part_name,
                    translation=pose[:3],
                    rotation=pose[3:],
                ),
                name=instance_name,
            )
        return part

    def generate(
        self, path_result: str | None = None, pools: Pool | None = None
    ) -> torchfea.Assembly:
        """Build a standalone Assembly containing only this interface.

        Args:
            path_result (str | None): Optimization result directory containing scripts and log
                subdirectories.
            pools (Pool | None): Optional multiprocessing pool for geometry preparation or export.

        Returns:
            torchfea.Assembly: Standalone assembly containing this Part interface and its registered
                Instances.
        """
        assembly = torchfea.Assembly()
        self.add_to_assembly(assembly, path_result=path_result, pools=pools)
        return assembly

    def workdir(self, path_result: str | None) -> str:
        """Per-interface working directory inside a result/cache folder.

        Args:
            path_result (str | None): Optimization result directory containing scripts and log
                subdirectories.

        Returns:
            str: Per-interface working directory inside a result/cache folder.
        """
        if path_result is None:
            import tempfile

            return tempfile.mkdtemp(prefix=f"morphopt_{self.name or 'geometry'}_")
        directory = os.path.join(str(path_result), self.name or "geometry")
        os.makedirs(directory, exist_ok=True)
        return directory
