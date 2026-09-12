"""Geometry parameter classes and the TorchFEA Assembly import helpers."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import torchfea

from .baseparam import BaseParams


# ---------------------------------------------------------------------------
# TorchFEA model import helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PartSummary:
    name: str
    node_sets: tuple[str, ...]
    element_sets: tuple[str, ...]
    surface_sets: tuple[str, ...]
    element_types: tuple[str, ...]


@dataclass(frozen=True)
class InstanceSummary:
    name: str
    part_name: str


@dataclass(frozen=True)
class TorchFEAModelSummary:
    path: str
    parts: tuple[PartSummary, ...]
    instances: tuple[InstanceSummary, ...]

    def part_for_instance(self, instance_name: str) -> PartSummary | None:
        instance = next(
            (item for item in self.instances if item.name == instance_name), None)
        if instance is None:
            return None
        return next(
            (item for item in self.parts if item.name == instance.part_name), None)


def resolve_model_path(model_directory: str, model_filename: str = "") -> Path:
    """Resolve one exported TorchFEA ``.npz`` inside ``model_directory``."""
    directory = Path(model_directory).expanduser().resolve()
    if not directory.is_dir():
        raise FileNotFoundError(
            f"TorchFEA model directory does not exist: {directory}")

    if model_filename:
        candidate = Path(model_filename)
        path = candidate if candidate.is_absolute() else directory / candidate
        path = path.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"TorchFEA model file does not exist: {path}")
        return path

    candidates = sorted(
        directory.glob("*.npz"), key=lambda item: item.stat().st_mtime_ns,
        reverse=True)
    if not candidates:
        raise FileNotFoundError(
            f"No TorchFEA .npz model was found in: {directory}")
    return candidates[0].resolve()


def inspect_model(model_directory: str,
                  model_filename: str = "") -> TorchFEAModelSummary:
    """Return selectable Part/Instance/set names from an exported model."""
    path = resolve_model_path(model_directory, model_filename)
    return _inspect_model_cached(str(path), path.stat().st_mtime_ns)


@lru_cache(maxsize=16)
def _inspect_model_cached(path: str, _mtime_ns: int) -> TorchFEAModelSummary:
    controller = _read_controller(path)
    source = controller.assembly
    if source is None:
        raise ValueError("The TorchFEA model does not contain an Assembly.")

    parts = tuple(
        PartSummary(
            name=name,
            node_sets=tuple(part.set_nodes.keys()),
            element_sets=tuple(part.set_elements.keys()),
            surface_sets=tuple(part.surfaces.keys()),
            element_types=tuple(part.elems.keys()),
        )
        for name, part in source._parts.items()
    )
    instances = tuple(
        InstanceSummary(name=name, part_name=instance.part_name)
        for name, instance in source._instances.items()
    )
    if not parts:
        raise ValueError("The TorchFEA Assembly contains no Parts.")
    if not instances:
        raise ValueError("The TorchFEA Assembly contains no Instances.")
    return TorchFEAModelSummary(str(Path(path).resolve()), parts, instances)


def load_geometry_assembly(model_directory: str,
                           model_filename: str = "") -> torchfea.Assembly:
    """Load a clean Assembly containing only cloned Parts and Instances."""
    path = resolve_model_path(model_directory, model_filename)
    controller = _read_controller(str(path))
    source = controller.assembly
    if source is None:
        raise ValueError("The TorchFEA model does not contain an Assembly.")

    assembly = torchfea.Assembly()
    for name, part in source._parts.items():
        cloned_part = torchfea.Serializable._deserialize(part._serialize())
        if (cloned_part.exterior_surface == "extern"
                and "extern" not in cloned_part.surfaces):
            boundary = []
            for element in cloned_part.elems.values():
                boundary.extend(element.extract_boundary_surface_set())
            if boundary:
                cloned_part.surfaces["extern"] = boundary
        assembly.add_part(cloned_part, name=name)
    for name, instance in source._instances.items():
        cloned_instance = torchfea.Serializable._deserialize(instance._serialize())
        assembly.add_instance(cloned_instance, name=name)

    if not assembly._parts:
        raise ValueError("The TorchFEA Assembly contains no Parts.")
    if not assembly._instances:
        raise ValueError("The TorchFEA Assembly contains no Instances.")
    return assembly


def _read_controller(path: str) -> torchfea.FEAController:
    """Deserialize a controller without initializing its analysis objects."""
    with np.load(path, allow_pickle=True) as loaded:
        if "data" not in loaded:
            raise ValueError("The .npz file is not a TorchFEA model archive.")
        return torchfea.FEAController._deserialize(loaded["data"])

class BaseGeometry(BaseParams):
    """
    Base class for geometry parameter classes.

    Subclasses must provide the mesh/geometry generation and assembly modification
    behavior used by the optimization pipeline.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)

    def generate(self, path_result: str, pools=None) -> torchfea.Assembly:
        """Generate the FEA part for the current geometry."""
        raise NotImplementedError
    


class FixedGeometry(BaseGeometry):
    """
    Base class for geometry whose FE assembly stays fixed during optimization.

    Subclasses may read an INP mesh or a saved TorchFEA model.  In both cases
    the assembly is built once and reused across optimization iterations.
    """
    def __init__(self):
        super().__init__()
        self._assembly: torchfea.Assembly = None
        """
        The FEA assembly containing the geometry for the optimization problem. This assembly is generated from a fixed mesh and does not change during optimization iterations.
        """

    @property
    def assembly(self) -> torchfea.Assembly:
        """
        Get the FEA assembly containing the geometry for the optimization problem.

        Returns:
            torchfea.Assembly: The FEA assembly containing the geometry.
        """
        if self._assembly is None:
            self._assembly = self.define_assembly()
        return self._assembly

    def define_assembly(self)-> torchfea.Assembly:
        """
        Define the assembly for the geometry using node and element data.

        This method should be implemented in subclasses to create the assembly based on specific node and element data.

        Returns:
            torchfea.Assembly: The defined assembly for the geometry.
        """
        raise NotImplementedError

    def generate(self, *args, **kwargs):
        """Return the lazily built fixed torchfea assembly."""
        return self.assembly

class FixedGeometryINP(FixedGeometry):
    """
    Geometry parameters class for fixed mesh geometry using an Abaqus .inp file.
    """
    def __init__(self, mesh_file: str, part_name: str = 'final_model'):
        super().__init__()
        self._mesh_file = mesh_file
        """
        The file path of the mesh to be loaded for the geometry.
        """

        self._part_name = part_name
        """The name of the part in the Abaqus INP file to be used for the geometry."""

    def define_assembly(self):
        inp = torchfea.FEA_INP()
        inp.read_inp(self._mesh_file)

        fe_ext = torchfea.from_inp(inp)
        
        assembly = torchfea.Assembly()

        assembly.add_part(part=fe_ext.assembly.get_part(self._part_name), name='final_model')
        instance = torchfea.Instance(part_name='final_model')
        assembly.add_instance(instance=instance, name='final_model')
        instance.exterior_surface = 'surface_0_All'
        return assembly


class FixedGeometryTorchFEA(FixedGeometry):
    """Fixed geometry imported from a model exported by ``torchfea-ui``.

    Only the saved Parts and Instances are used.  MorphOpt creates its own
    loads, constraints, boundary conditions, reference points, and solver.
    """

    def __init__(self, model_directory: str, model_filename: str):
        super().__init__()
        self.model_directory = str(model_directory)
        self.model_filename = str(model_filename)
        # Fail early with a path-specific message while keeping assembly
        # construction lazy.
        self.model_path = str(resolve_model_path(
            self.model_directory, self.model_filename))

    def define_assembly(self) -> torchfea.Assembly:
        return load_geometry_assembly(
            self.model_directory, self.model_filename)
