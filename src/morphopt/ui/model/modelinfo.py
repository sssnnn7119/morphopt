"""Read-only projections of an exported TorchFEA model, for the UI.

The archive itself is always loaded with :func:`torchfea.load_model`; this
module only turns the resulting Assembly into small, immutable name lists that
the editors, the code generator and the preview can query cheaply:

* which Parts exist, and which Instances place them,
* the surface / node / element sets and element families of every Part.

Those names are what the UI offers as choices for the load, material and
contact interfaces, and what the code generator validates before emitting
runnable source.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import torchfea

from ...optcore.modelparams.partinterface import resolve_model_path

__all__ = [
    "InstanceSummary",
    "PartSummary",
    "TorchFEAModelSummary",
    "inspect_model",
    "resolve_model_path",
]


@dataclass(frozen=True)
class PartSummary:
    """Names exposed by one Part of an imported Assembly."""

    name: str
    node_sets: tuple[str, ...]
    element_sets: tuple[str, ...]
    surface_sets: tuple[str, ...]
    element_types: tuple[str, ...]


@dataclass(frozen=True)
class InstanceSummary:
    """One Instance of an imported Assembly and the Part it places."""

    name: str
    part_name: str
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class TorchFEAModelSummary:
    """Parts and Instances of one exported model archive."""

    path: str
    parts: tuple[PartSummary, ...]
    instances: tuple[InstanceSummary, ...]

    def part(self, part_name: str) -> PartSummary | None:
        return next((item for item in self.parts if item.name == part_name), None)

    def part_for_instance(self, instance_name: str) -> PartSummary | None:
        instance = next(
            (item for item in self.instances if item.name == instance_name), None
        )
        if instance is None:
            return None
        return self.part(instance.part_name)


def inspect_model(
    model_directory: str, model_filename: str = ""
) -> TorchFEAModelSummary:
    """Return the Part/Instance/set names of an exported model."""
    path = resolve_model_path(model_directory, model_filename)
    return _inspect_model_cached(str(path), path.stat().st_mtime_ns)


def _vector3(instance: object, attribute: str) -> tuple[float, float, float]:
    """Read one TorchFEA placement vector without exposing backend tensors."""
    value = getattr(instance, attribute, None)
    if value is None:
        return (0.0, 0.0, 0.0)
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        value = tolist()
    values = tuple(float(item) for item in value)
    return values if len(values) == 3 else (0.0, 0.0, 0.0)


@lru_cache(maxsize=16)
def _inspect_model_cached(path: str, _mtime_ns: int) -> TorchFEAModelSummary:
    assembly = torchfea.load_model(path).assembly
    parts = tuple(
        PartSummary(
            name=name,
            node_sets=tuple(part.set_nodes.keys()),
            element_sets=tuple(part.set_elements.keys()),
            surface_sets=tuple(part.surfaces.keys()),
            element_types=tuple(part.elems.keys()),
        )
        for name, part in assembly._parts.items()
    )
    instances = tuple(
        InstanceSummary(
            name=name,
            part_name=instance.part_name,
            translation=_vector3(instance, "_translation"),
            rotation=_vector3(instance, "_rotation"),
        )
        for name, instance in assembly._instances.items()
    )
    if not parts:
        raise ValueError(f"The TorchFEA model contains no Parts: {path}")
    return TorchFEAModelSummary(path, parts, instances)
