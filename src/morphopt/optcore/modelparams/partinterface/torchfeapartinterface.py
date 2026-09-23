"""Part interface importing a fixed Part from a TorchFEA model archive."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import torch
import torchfea

from .basepartinterface import BasePartInterface

if TYPE_CHECKING:
    from multiprocessing.pool import Pool

__all__ = ["TorchFEAPartInterface", "resolve_model_path", "load_model_assembly"]


def _tensor_to_list(value: object) -> list[float] | None:
    if value is None:
        return None
    detach = getattr(value, "detach", None)
    if callable(detach):
        value = detach()
    cpu = getattr(value, "cpu", None)
    if callable(cpu):
        value = cpu()
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        value = tolist()
    return [float(item) for item in value]


def resolve_model_path(model_directory: str, model_filename: str = "") -> Path:
    """Resolve one exported TorchFEA ``.npz`` inside ``model_directory``."""
    directory = Path(model_directory).expanduser().resolve()
    if not directory.is_dir():
        raise FileNotFoundError(
            f"TorchFEA model directory does not exist: {directory}"
        )

    if model_filename:
        candidate = Path(model_filename)
        path = candidate if candidate.is_absolute() else directory / candidate
        path = path.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"TorchFEA model file does not exist: {path}")
        return path

    candidates = sorted(
        directory.glob("*.npz"),
        key=lambda item: item.stat().st_mtime_ns,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            f"No TorchFEA .npz model was found in: {directory}"
        )
    return candidates[0].resolve()


def load_model_assembly(
    model_directory: str, model_filename: str = ""
) -> torchfea.Assembly:
    """Load an exported model and return its Assembly."""
    path = resolve_model_path(model_directory, model_filename)
    model = torchfea.load_model(str(path))
    # Serialized TorchFEA models are usually stored on CPU.  Normalize the
    # imported model before combining it with Parts built under MorphOpt's
    # current default device.
    model.change_device(torch.device(torch.get_default_device()))
    assembly = model.assembly
    if assembly is None or not assembly._parts:
        raise ValueError(f"The TorchFEA model contains no Parts: {path}")
    return assembly


class TorchFEAPartInterface(BasePartInterface):
    """One fixed Part loaded from a ``torchfea-ui`` model archive."""

    cache_part = True

    def __init__(
        self,
        model_directory: str,
        model_filename: str = "",
        part_name: str | None = None,
        model_part_name: str | None = None,
        exterior_surface: str | None = None,
        _assembly: torchfea.Assembly | None = None,
    ) -> None:
        self.model_directory: str = str(model_directory)
        """Folder containing the exported TorchFEA model."""

        self.model_filename: str = str(model_filename)
        """Exported ``.npz`` file name; empty selects the newest file."""

        self.model_path: str = str(
            resolve_model_path(self.model_directory, self.model_filename)
        )
        """Resolved path of the imported TorchFEA model."""

        source = _assembly or load_model_assembly(
            self.model_directory, self.model_filename
        )
        archive_names = list(source._parts)

        selector = str(model_part_name).strip() if model_part_name else ""
        if not selector and part_name and str(part_name) in archive_names:
            selector = str(part_name)
        if not selector:
            if len(archive_names) != 1:
                raise ValueError(
                    f"{self.model_path!r} contains several Parts "
                    f"({archive_names}); pass model_part_name to select one."
                )
            selector = archive_names[0]
        if selector not in archive_names:
            raise KeyError(
                f"Part {selector!r} does not exist in {self.model_path!r} "
                f"({archive_names})."
            )

        self.model_part_name: str = selector
        """Part name inside the exported archive."""

        self._source_instances: list[tuple[str, object]] = [
            # Keep only the selected Part's placements; loads and other model
            # objects are deliberately rebuilt by MorphOpt.
            (name, instance)
            for name, instance in source._instances.items()
            if instance.part_name == selector
        ]
        super().__init__(part_name=part_name, exterior_surface=exterior_surface)

    def define_instance(self) -> None:
        """Copy the selected Part's archive Instances into the new Assembly."""
        if not self._source_instances:
            super().define_instance()
            return

        for name, source_instance in self._source_instances:
            translation = _tensor_to_list(
                getattr(source_instance, "_translation", None)
            ) or [0.0, 0.0, 0.0]
            rotation = _tensor_to_list(
                getattr(source_instance, "_rotation", None)
            ) or [0.0, 0.0, 0.0]
            self.add_instance(
                self.part_name,
                name,
                [*translation, *rotation],
            )

    @classmethod
    def for_all_parts(
        cls, model_directory: str, model_filename: str = ""
    ) -> list["TorchFEAPartInterface"]:
        """Create one interface per Part stored in the archive."""
        assembly = load_model_assembly(model_directory, model_filename)
        return [
            cls(
                model_directory,
                model_filename,
                part_name=part_name,
                model_part_name=part_name,
                _assembly=assembly,
            )
            for part_name in assembly._parts
        ]

    def build_part(
        self, path_result: str | None = None, pools: Pool | None = None
    ) -> torchfea.Part:
        """Return the selected Part of a freshly loaded model."""
        assembly = load_model_assembly(self.model_directory, self.model_filename)
        return assembly.get_part(self.model_part_name)
