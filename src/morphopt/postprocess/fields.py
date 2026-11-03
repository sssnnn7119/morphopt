"""Finite-element fields, record tables, and nodal contour projections.

FiniteElementResults owns the numerical context for one model/solution pair.
Field providers and contour descriptors declare quantities; this module does
not load archives, write files, or choose UI labels.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from enum import Enum
from functools import cached_property
from typing import Any

import numpy as np
import torch

from ._runtime import evaluation_defaults


def _as_array(value: torch.Tensor | np.ndarray) -> np.ndarray:
    return value.detach().cpu().numpy() if isinstance(value, torch.Tensor) else np.asarray(value)


class ResultLocation(str, Enum):
    NODES = 'nodes'
    REFERENCE_POINTS = 'reference_points'
    ELEMENTS = 'elements'


@dataclass(frozen=True)
class ResultTable:
    """A field selection with stable columns and lazily evaluated rows."""

    name: str
    columns: tuple[str, ...]
    rows: Iterable[tuple]
    fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContourField:
    """A displayed scalar component of a physical result field."""

    key: str
    source: str
    component: int


_NODE_KEYS = ('instance', 'node_id')
_REFERENCE_POINT_KEYS = ('reference_point_id', 'reference_point')
_ELEMENT_KEYS = ('instance', 'element_block', 'element_id', 'integration_point')


_GAUSS_COMPONENTS = ((0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2))
_GAUSS_COLUMNS = {
    'gauss_coordinates': ('X', 'Y', 'Z'),
    'energy': ('strain_energy_density', 'reference_volume', 'strain_energy'),
    'stress': ('S11', 'S22', 'S33', 'S12', 'S13', 'S23', 'S_Mises'),
    'strain': ('E11', 'E22', 'E33', 'E12', 'E13', 'E23'),
}


CONTOUR_FIELDS = (
    ContourField("U", "displacement", 3),
    *(ContourField(f"U{axis}", "displacement", axis - 1) for axis in (1, 2, 3)),
    ContourField("S_Mises", "stress", 6),
    *(ContourField(key, "stress", index)
      for index, key in enumerate(_GAUSS_COLUMNS["stress"][:-1])),
    *(ContourField(key, "strain", index)
      for index, key in enumerate(_GAUSS_COLUMNS["strain"])),
    ContourField("strain_energy_density", "energy", 0),
)


def _record_keys(location: ResultLocation) -> tuple[str, ...]:
    return {
        ResultLocation.NODES: _NODE_KEYS,
        ResultLocation.REFERENCE_POINTS: _REFERENCE_POINT_KEYS,
        ResultLocation.ELEMENTS: _ELEMENT_KEYS,
    }[location]


@dataclass(frozen=True)
class ResultField:
    """Physical field provider independent of display labels and file formats."""

    key: str
    description: str
    location: ResultLocation
    extract: Callable[[FiniteElementResults], ResultTable]
    gauss_kind: str | None = None

    def available(self, context: FiniteElementResults) -> bool:
        if self.location is ResultLocation.REFERENCE_POINTS:
            return next(context.reference_points(), None) is not None
        return (
            self.gauss_kind is None
            or next(context.gauss_blocks(self.gauss_kind), None) is not None
        )


class FiniteElementResults:
    """Evaluate fields and cache contour projections for one model and solution."""

    def __init__(self, controller: Any, result: Any) -> None:
        self.controller, self.result = controller, result
        self._contour_groups: dict[str, dict[str, np.ndarray]] = {}

    def available_fields(self, location: ResultLocation | str) -> tuple[str, ...]:
        """List supported table fields at one record location."""
        location = ResultLocation(location)
        with evaluation_defaults(self.result):
            return tuple(
                key for key, field in RESULT_FIELDS.items()
                if field.location is location and field.available(self)
            )

    def table(
        self,
        location: ResultLocation | str = ResultLocation.NODES,
        fields: Sequence[str] | None = None,
    ) -> ResultTable:
        """Join selected physical quantities onto stable record identifiers.

        Rows are evaluated lazily under the solution's Torch defaults. Fields
        unavailable for the model are omitted; an empty selection is rejected.
        """
        location = ResultLocation(location)
        keys = (
            tuple(dict.fromkeys(fields))
            if fields is not None else self.available_fields(location)
        )
        if not keys:
            raise ValueError("Choose at least one result field.")
        providers = tuple(RESULT_FIELDS[key] for key in keys)
        if any(provider.location is not location for provider in providers):
            raise ValueError("Choose fields from one result location only.")
        with evaluation_defaults(self.result):
            providers = tuple(field for field in providers if field.available(self))
            if not providers:
                raise ValueError("The selected model has no data for these physical quantities.")
            return self._combined_table(location, providers)

    @cached_property
    def contour_fields(self) -> tuple[ContourField, ...]:
        with evaluation_defaults(self.result), torch.no_grad():
            supported = {"displacement"}
            for kind in ("stress", "strain", "energy"):
                if next(self.gauss_blocks(kind), None) is not None:
                    supported.add(kind)
        return tuple(field for field in CONTOUR_FIELDS if field.source in supported)

    def contour_values(self, field: ContourField) -> dict[str, np.ndarray]:
        """Return a scalar node array for each supported instance."""
        if field.source not in self._contour_groups:
            with evaluation_defaults(self.result), torch.no_grad():
                self._contour_groups[field.source] = self._evaluate_contours(field.source)
        return {
            name: values[:, field.component]
            for name, values in self._contour_groups[field.source].items()
        }

    @cached_property
    def coordinates(self) -> torch.Tensor:
        with evaluation_defaults(self.result):
            return self.controller.GC2RGC(self.result.GC)

    def instances(self) -> Iterator[tuple[str, Any, torch.Tensor]]:
        for name, instance in self.controller.assembly._instances.items():
            if instance.enabled is False:
                continue
            displacement = self.coordinates[instance._RGC_index].reshape(-1, 3)
            yield name, instance, displacement

    def reference_points(self) -> Iterator[tuple[int, str, Any, np.ndarray]]:
        for index, (name, point) in enumerate(self.controller.assembly._reference_points.items(), start=1):
            if point.enabled is False:
                continue
            values = _as_array(self.coordinates[point._RGC_index]).reshape(-1)
            yield index, name, point, values

    def element_blocks(self) -> Iterator[tuple[str, Any, str, Any, torch.Tensor]]:
        for name, instance, displacement in self.instances():
            rotation = instance.rotation_matrix
            local = (
                displacement if rotation is None
                else displacement @ rotation.to(displacement)
            )
            for block_name, element in instance.part.elems.items():
                if len(element._elems):
                    yield name, instance, block_name, element, local

    @cached_property
    def gauss_positions(self) -> dict[tuple[str, str], np.ndarray]:
        positions = {}
        for name, instance, block, element, _ in self.element_blocks():
            getter = getattr(element, 'get_gaussian_points', None)
            if not callable(getter):
                continue
            try:
                with evaluation_defaults(self.result):
                    points = getter(instance.nodes)
            except NotImplementedError:
                continue
            if points is not None and _as_array(points).size:
                positions[name, block] = _as_array(points)
        return positions

    def gauss_blocks(
        self, kind: str
    ) -> Iterator[tuple[str, Any, str, Any, torch.Tensor]]:
        required = {
            'gauss_coordinates': (),
            'energy': ('get_potential_energy_density', 'gaussian_weight'),
            'stress': ('get_deformation_gradient', 'components_Solid'),
            'strain': ('get_deformation_gradient',),
        }[kind]
        for item in self.element_blocks():
            name, _, block, element, _ = item
            if (name, block) in self.gauss_positions and all(
                hasattr(element, attr) for attr in required
            ):
                yield item

    def gauss_values(self, kind: str) -> Iterator[tuple[str, str, Any, np.ndarray]]:
        """Yield block arrays (Gauss point, element, component) for export and display."""
        for name, instance, block, element, local in self.gauss_blocks(kind):
            with evaluation_defaults(self.result):
                positions = self.gauss_positions[name, block]
                if kind == 'gauss_coordinates':
                    values = positions
                elif kind == 'energy':
                    energy = element.get_potential_energy_density(local)
                    volume = element.gaussian_weight
                    if volume.ndim == 1:
                        volume = volume[:, None].expand_as(energy)
                    values = torch.stack((energy, volume, energy * volume), dim=-1)
                else:
                    gradient = element.get_deformation_gradient(local)
                    if kind == 'strain':
                        identity = torch.eye(3, dtype=gradient.dtype, device=gradient.device)
                        tensor = (gradient.transpose(-1, -2) @ gradient - identity) * 0.5
                    else:
                        jacobian = gradient.det()
                        if torch.any(jacobian <= 0):
                            raise ValueError('Cannot export Cauchy stress for an inverted element.')
                        # torchfea returns the transpose of first Piola stress.
                        piola_transpose, _ = element.components_Solid(local)
                        tensor = (
                            piola_transpose.transpose(-1, -2)
                            @ gradient.transpose(-1, -2)
                        ) / jacobian[..., None, None]
                        tensor = (tensor + tensor.transpose(-1, -2)) * 0.5
                    if instance.rotation_matrix is not None:
                        rotation = instance.rotation_matrix.to(tensor)
                        tensor = rotation @ tensor @ rotation.T
                    values = torch.stack(tuple(tensor[..., a, b] for a, b in _GAUSS_COMPONENTS), dim=-1)
                    if kind == 'stress':
                        identity = torch.eye(3, dtype=tensor.dtype, device=tensor.device)
                        trace = tensor.diagonal(dim1=-2, dim2=-1).sum(-1)
                        deviator = tensor - trace[..., None, None] * identity / 3
                        mises = (1.5 * deviator.square().sum((-1, -2))).clamp_min(0).sqrt()
                        values = torch.cat((values, mises[..., None]), dim=-1)
                values = _as_array(values)
            yield name, block, element, values

    def _evaluate_contours(self, source: str) -> dict[str, np.ndarray]:
        if source == "displacement":
            values = {}
            for name, _instance, displacement in self.instances():
                components = _as_array(displacement)
                values[name] = np.column_stack(
                    (components, np.linalg.norm(components, axis=1))
                )
            return values

        columns = len(_GAUSS_COLUMNS[source])
        sums: dict[str, np.ndarray] = {}
        counts: dict[str, np.ndarray] = {}
        for name, _block, element, values in self.gauss_values(source):
            if name not in sums:
                nodes = len(self.controller.assembly._instances[name].nodes)
                sums[name] = np.zeros((nodes, columns))
                counts[name] = np.zeros((nodes, 1))
            weights = _as_array(element.gaussian_weight)
            if weights.ndim == 1:
                weights = weights[:, None]
            weights = np.broadcast_to(weights, values.shape[:2])
            volumes = weights.sum(axis=0)
            means = np.full(values.shape[1:], np.nan)
            np.divide(
                (values * weights[..., None]).sum(axis=0),
                volumes[:, None],
                out=means,
                where=volumes[:, None] > 0,
            )
            nodes = _as_array(element._elems).astype(np.intp)
            valid = np.isfinite(means).all(axis=1)
            np.add.at(
                sums[name], nodes[valid].ravel(),
                np.repeat(means[valid], nodes.shape[1], axis=0),
            )
            np.add.at(counts[name], nodes[valid].ravel(), 1)
        return {
            name: np.divide(
                values, counts[name], out=np.full_like(values, np.nan),
                where=counts[name] > 0,
            )
            for name, values in sums.items()
        }

    def _record_rows(self, location: ResultLocation) -> Iterator[tuple]:
        if location is ResultLocation.NODES:
            for name, instance, _ in self.instances():
                for index in range(len(instance.nodes)):
                    yield name, index + 1
        elif location is ResultLocation.REFERENCE_POINTS:
            for index, name, _point, _values in self.reference_points():
                yield index, name
        else:
            for name, _, block, element, _ in self.element_blocks():
                points = self.gauss_positions.get((name, block))
                for element_id in _as_array(element._elems_index).reshape(-1):
                    if points is None:
                        yield name, block, int(element_id) + 1, None
                    else:
                        for point in range(points.shape[0]):
                            yield name, block, int(element_id) + 1, point + 1

    def _nodal_table(self, kind: str) -> ResultTable:
        columns = {
            'coordinates': ('X', 'Y', 'Z'),
            'displacement': ('U1', 'U2', 'U3', 'U'),
            'deformed_coordinates': ('x', 'y', 'z'),
        }[kind]

        def rows() -> Iterator[tuple]:
            for name, instance, displacement in self.instances():
                position, value = _as_array(instance.nodes), _as_array(displacement)
                if kind == 'coordinates':
                    data = position
                elif kind == 'deformed_coordinates':
                    data = position + value
                else:
                    data = np.column_stack((value, np.linalg.norm(value, axis=1)))
                for index, row in enumerate(data, start=1):
                    yield name, index, *row
        return ResultTable(kind, (*_NODE_KEYS, *columns), rows())

    def _element_coordinate_table(self) -> ResultTable:
        def rows() -> Iterator[tuple]:
            for name, instance, block, element, _ in self.element_blocks():
                centers = _as_array(instance.nodes[element._elems].mean(dim=1))
                points = self.gauss_positions.get((name, block))
                for index, element_id in enumerate(_as_array(element._elems_index).reshape(-1)):
                    for point in range(points.shape[0]) if points is not None else (None,):
                        yield (
                            name, block, int(element_id) + 1,
                            point + 1 if point is not None else None,
                            *centers[index],
                        )
        return ResultTable('element_coordinates', (*_ELEMENT_KEYS, 'CX', 'CY', 'CZ'), rows())

    def _reference_point_table(self, kind: str) -> ResultTable:
        columns = {
            'coordinates': ('X', 'Y', 'Z'),
            'displacement': ('U1', 'U2', 'U3', 'U'),
            'rotation': ('UR1', 'UR2', 'UR3', 'UR'),
            'deformed_coordinates': ('x', 'y', 'z'),
        }[kind]

        def rows() -> Iterator[tuple]:
            for index, name, point, values in self.reference_points():
                position = _as_array(point.node).reshape(-1)
                if kind == 'coordinates':
                    data = position
                elif kind == 'deformed_coordinates':
                    data = position + values[:3]
                else:
                    components = values[:3] if kind == 'displacement' else values[3:6]
                    data = (*components, np.linalg.norm(components))
                yield index, name, *data
        return ResultTable('rp_' + kind, (*_REFERENCE_POINT_KEYS, *columns), rows())

    def _gauss_table(self, kind: str) -> ResultTable:
        def rows() -> Iterator[tuple]:
            for name, block, element, values in self.gauss_values(kind):
                element_ids = _as_array(element._elems_index).reshape(-1)
                for element_index, element_id in enumerate(element_ids):
                    for point in range(values.shape[0]):
                        yield (name, block, int(element_id) + 1, point + 1,
                               *values[point, element_index])

        return ResultTable('gauss_' + kind, (*_ELEMENT_KEYS, *_GAUSS_COLUMNS[kind]), rows())

    def _combined_table(
        self,
        location: ResultLocation,
        providers: tuple[ResultField, ...],
    ) -> ResultTable:
        """Join provider columns onto stable record IDs without materializing the full table."""
        keys = _record_keys(location)
        # Omit the integration-point identifier completely when no block has Gauss points.
        include_gauss = location is ResultLocation.ELEMENTS and bool(self.gauss_positions)
        output_keys = (
            keys[:-1] if location is ResultLocation.ELEMENTS and not include_gauss else keys
        )
        tables = tuple(provider.extract(self) for provider in providers)
        for table in tables:
            if table.columns[:len(keys)] != keys:
                raise ValueError(
                    f"Field {table.name} does not use the {location.value} record identifiers."
                )
        columns = (
            *output_keys,
            *(column for table in tables for column in table.columns[len(keys):]),
        )
        if len(set(columns)) != len(columns):
            raise ValueError('Selected result fields contain duplicate column names.')

        def rows() -> Iterator[tuple]:
            records = iter(self._record_rows(location))
            with evaluation_defaults(self.result):
                iterators = [iter(table.rows) for table in tables]
                pending = [next(iterator, None) for iterator in iterators]
            while True:
                with evaluation_defaults(self.result):
                    record = next(records, None)
                    if record is None:
                        break
                    values = list(record[:len(output_keys)])
                    for index, table in enumerate(tables):
                        row = pending[index]
                        if row is not None and tuple(row[:len(keys)]) == record:
                            values.extend(row[len(keys):])
                            pending[index] = next(iterators[index], None)
                        else:
                            values.extend([None] * (len(table.columns) - len(keys)))
                yield tuple(values)
            if any(row is not None for row in pending):
                raise ValueError(
                    "A result field contains unknown or out-of-order record identifiers."
                )
        return ResultTable(
            location.value, columns, rows(), tuple(field.key for field in providers)
        )


# Adding a physical quantity requires only a provider for one record location.
RESULT_FIELDS: dict[str, ResultField] = {
    "coordinates": ResultField(
        "coordinates", "Global reference node coordinates.", ResultLocation.NODES,
        lambda context: context._nodal_table("coordinates"),
    ),
    "displacement": ResultField(
        "displacement", "Global nodal displacement components and magnitude.",
        ResultLocation.NODES, lambda context: context._nodal_table("displacement"),
    ),
    "deformed_coordinates": ResultField(
        "deformed_coordinates", "Global deformed node coordinates.",
        ResultLocation.NODES, lambda context: context._nodal_table("deformed_coordinates"),
    ),
    "rp_coordinates": ResultField(
        "rp_coordinates", "Global reference-point coordinates.",
        ResultLocation.REFERENCE_POINTS,
        lambda context: context._reference_point_table("coordinates"),
    ),
    "rp_displacement": ResultField(
        "rp_displacement", "Global reference-point translation components and magnitude.",
        ResultLocation.REFERENCE_POINTS,
        lambda context: context._reference_point_table("displacement"),
    ),
    "rp_rotation": ResultField(
        "rp_rotation",
        "Global reference-point rotation vector components and magnitude in radians "
        "(axis-angle, not Euler angles).",
        ResultLocation.REFERENCE_POINTS,
        lambda context: context._reference_point_table("rotation"),
    ),
    "rp_deformed_coordinates": ResultField(
        "rp_deformed_coordinates", "Global translated reference-point coordinates.",
        ResultLocation.REFERENCE_POINTS,
        lambda context: context._reference_point_table("deformed_coordinates"),
    ),
    "element_coordinates": ResultField(
        "element_coordinates", "Mean global reference coordinates of an element's nodes.",
        ResultLocation.ELEMENTS, lambda context: context._element_coordinate_table(),
    ),
    "gauss_coordinates": ResultField(
        "gauss_coordinates", "Global reference integration-point coordinates.",
        ResultLocation.ELEMENTS, lambda context: context._gauss_table("gauss_coordinates"),
        "gauss_coordinates",
    ),
    "energy": ResultField(
        "energy", "Strain energy per reference volume, reference integration volume and their product.",
        ResultLocation.ELEMENTS, lambda context: context._gauss_table("energy"), "energy",
    ),
    "stress": ResultField(
        "stress", "Cauchy stress in global axes, evaluated separately at each integration point.",
        ResultLocation.ELEMENTS, lambda context: context._gauss_table("stress"), "stress",
    ),
    "strain": ResultField(
        "strain", "Green-Lagrange tensor strain in global reference axes; shear components are tensor shear.",
        ResultLocation.ELEMENTS, lambda context: context._gauss_table("strain"), "strain",
    ),
}
