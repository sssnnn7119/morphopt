"""Immutable Part definition loaded from an Abaqus INP model."""

from __future__ import annotations

from collections.abc import Sequence
from multiprocessing.pool import Pool
from pathlib import Path

import torchfea

from .base import BasePartDefinition
from .instance import InstanceDefinition
from .mesh import MeshBuilder


class InpPart(BasePartDefinition):
    """Reuse one selected immutable Part from a TorchFEA-readable INP file."""

    def __init__(
        self,
        part_name: str,
        inp_path: str | Path,
        source_part_name: str,
        *,
        element_names: Sequence[str] | None = None,
        source_instance_names: Sequence[str] | None = None,
        exterior_surface: str = "extern",
    ) -> None:
        super().__init__(
            part_name,
            element_names=tuple(element_names) if element_names is not None else None,
            exterior_surface=exterior_surface,
        )
        self._inp_path = Path(inp_path)
        """INP source containing the immutable source Assembly."""
        self._source_part_name = str(source_part_name)
        """Part name selected from the source Assembly."""
        self._source_instance_names = (
            tuple(str(name) for name in source_instance_names)
            if source_instance_names is not None
            else None
        )
        """Optional selected source instances; None selects every matching instance."""
        self._torchfea_Assembly: torchfea.Assembly | None = None
        """Cached immutable source Assembly parsed from the INP file."""
        self._source_element_types: tuple[str, ...] = ()
        """Source element types in stable V4 naming order."""

    @property
    def inp_path(self) -> Path:
        """Return the immutable INP source path."""
        return self._inp_path

    @property
    def source_part_name(self) -> str:
        """Return the selected source Part name."""
        return self._source_part_name

    @property
    def source_instance_names(self) -> tuple[str, ...] | None:
        """Return the optional selected source-instance names."""
        return self._source_instance_names

    def get_source_assembly(self) -> torchfea.Assembly:
        """Return the source Assembly loaded during :meth:`initialize`."""
        if self._torchfea_Assembly is None:
            raise RuntimeError(f"INP source {self._inp_path} has not been initialized")
        return self._torchfea_Assembly

    def build_part(self, path_result: Path | None = None, pools: Pool | None = None) -> None:
        """Expose the selected immutable source Part for the current Assembly."""
        del path_result, pools
        self._torchfea_Part = self.get_source_assembly().get_part(self._source_part_name)
        self._torchfea_Part.exterior_surface = self._exterior_surface
        self._rename_element_families()

    def initialize(self) -> None:
        """Load source data, resolve element names and register selected instances."""
        super().initialize()
        self._load_source_assembly()
        self._resolve_element_names()
        self._build_source_instances()

    def build_meshes(self) -> None:
        """Build the fixed Part preview mesh from its selected source Part."""
        self._meshes = (self.get_source_assembly().get_part(self._source_part_name).get_mesh(),)

    def _load_source_assembly(self) -> None:
        """Parse the INP source and cache its full source Assembly."""
        source = MeshBuilder.read_inp_part(self._inp_path, self._source_part_name)
        assembly = torchfea.Assembly()
        assembly.add_part(source, name=self._source_part_name)
        self._torchfea_Assembly = assembly

    def _resolve_element_names(self) -> None:
        """Map selected source element families to configured output names."""
        source = self.get_source_assembly().get_part(self._source_part_name)
        names_by_type = sorted(
            source.elems,
            key=lambda name: self._element_order(source.elems[name].__class__.__name__),
        )
        self._source_element_types = tuple(names_by_type)
        if self._element_names is None:
            self._element_names = tuple(source.elems[name].__class__.__name__ for name in names_by_type)
        if len(self._element_names) != len(names_by_type):
            raise ValueError(
                f"INP Part {self._source_part_name!r} has {len(names_by_type)} element families, "
                f"but {len(self._element_names)} output names were supplied"
            )

    def _build_source_instances(self) -> None:
        """Replace the default instance with selected source-instance placements."""
        self._instances.clear()
        source_instances = self.get_source_assembly()._instances
        selected_names = self._source_instance_names
        for name, source_instance in source_instances.items():
            if source_instance.part_name != self._source_part_name:
                continue
            if selected_names is not None and name not in selected_names:
                continue
            self.add_instance(
                InstanceDefinition(
                    name,
                    self._part_name,
                    translation=source_instance._translation.detach().cpu().tolist(),
                    rotation=source_instance._rotation.detach().cpu().tolist(),
                )
            )
        if not self._instances:
            self.add_instance(InstanceDefinition(self._part_name, self._part_name))

    def _rename_element_families(self) -> None:
        """Rename selected backend families to the resolved output names."""
        part = self.get_part()
        renamed: dict[str, torchfea.elements.Element_3D] = {}
        for source_name, output_name in zip(
            self._source_element_types, self._element_names, strict=True
        ):
            renamed[output_name] = (
                part.elems[source_name]
                if source_name in part.elems
                else part.elems[output_name]
            )
        part.elems = renamed

    @staticmethod
    def _element_order(element_type: str) -> tuple[int, str]:
        """Order supported element types before remaining source-order names."""
        order = ("C3D4", "C3D6", "C3D8", "C3D10", "C3D15", "C3D20")
        return (order.index(element_type), element_type) if element_type in order else (len(order), element_type)
