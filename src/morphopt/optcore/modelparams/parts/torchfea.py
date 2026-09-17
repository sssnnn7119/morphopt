"""Immutable Part definition linked to a saved TorchFEA model."""

from __future__ import annotations

from collections.abc import Sequence
from multiprocessing.pool import Pool
from pathlib import Path

import torchfea

from .base import BasePartDefinition
from .inp import InpPart
from .instance import InstanceDefinition


class TorchFEAPart(BasePartDefinition):
    """Reuse one selected Part and its placements from a TorchFEA model file."""

    def __init__(
        self,
        part_name: str,
        model_directory: str | Path,
        model_filename: str,
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
        self._model_directory = Path(model_directory)
        """Directory containing the TorchFEA model file."""
        self._model_filename = str(model_filename)
        """TorchFEA model file name within :attr:`model_directory`."""
        self._source_part_name = str(source_part_name)
        """Part name selected from the source model Assembly."""
        self._source_instance_names = (
            tuple(str(name) for name in source_instance_names)
            if source_instance_names is not None
            else None
        )
        """Optional source instances selected for the generated Assembly."""
        self._torchfea_Assembly: torchfea.Assembly | None = None
        """Cached immutable Assembly loaded from the model file."""
        self._source_element_types: tuple[str, ...] = ()
        """Selected source element-family names in stable type order."""

    @property
    def model_directory(self) -> Path:
        """Return the directory containing the source model."""
        return self._model_directory

    @property
    def model_filename(self) -> str:
        """Return the source model filename."""
        return self._model_filename

    @property
    def source_part_name(self) -> str:
        """Return the selected source Part name."""
        return self._source_part_name

    @property
    def source_instance_names(self) -> tuple[str, ...] | None:
        """Return selected source instance names, when explicitly configured."""
        return self._source_instance_names

    def get_source_assembly(self) -> torchfea.Assembly:
        """Return the source Assembly loaded during :meth:`initialize`."""
        if self._torchfea_Assembly is None:
            raise RuntimeError(f"TorchFEA model {self._compute_model_path()} has not been initialized")
        return self._torchfea_Assembly

    def build_part(self, path_result: Path | None = None, pools: Pool | None = None) -> None:
        """Expose the selected immutable model Part for the current Assembly."""
        del path_result, pools
        self._torchfea_Part = self.get_source_assembly().get_part(self._source_part_name)
        self._torchfea_Part.exterior_surface = self._exterior_surface
        self._rename_element_families()

    def initialize(self) -> None:
        """Load the model, resolve family names and inherit instance placements."""
        super().initialize()
        self._load_source_assembly()
        self._resolve_element_names()
        self._build_source_instances()

    def build_meshes(self) -> None:
        """Build a preview mesh directly from the selected source Part."""
        self._meshes = (self.get_source_assembly().get_part(self._source_part_name).get_mesh(),)

    def _compute_model_path(self) -> Path:
        """Return the normalized saved-model path."""
        return self._model_directory / self._model_filename

    def _load_source_assembly(self) -> None:
        """Load and cache the source Assembly using TorchFEA's model reader."""
        self._torchfea_Assembly = torchfea.load_model(str(self._compute_model_path())).assembly

    def _resolve_element_names(self) -> None:
        """Map selected source element families to configured output names."""
        source = self.get_source_assembly().get_part(self._source_part_name)
        names_by_type = sorted(
            source.elems,
            key=lambda name: InpPart._element_order(source.elems[name].__class__.__name__),
        )
        self._source_element_types = tuple(names_by_type)
        if self._element_names is None:
            self._element_names = tuple(source.elems[name].__class__.__name__ for name in names_by_type)
        if len(self._element_names) != len(names_by_type):
            raise ValueError(
                f"Model Part {self._source_part_name!r} has {len(names_by_type)} element families, "
                f"but {len(self._element_names)} output names were supplied"
            )

    def _build_source_instances(self) -> None:
        """Replace the default instance with selected source-instance placements."""
        self._instances.clear()
        for name, source_instance in self.get_source_assembly()._instances.items():
            if source_instance.part_name != self._source_part_name:
                continue
            if self._source_instance_names is not None and name not in self._source_instance_names:
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
        """Rename selected backend families to resolved output names."""
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
