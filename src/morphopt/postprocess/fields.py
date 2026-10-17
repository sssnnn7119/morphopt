"""Physical field providers; every integration point remains a separate record."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cached_property
from enum import Enum

import numpy as np
import torch


@contextmanager
def evaluation_defaults(result):
    """TorchFEA allocates working arrays using defaults; match and then restore them."""
    dtype, device = torch.get_default_dtype(), torch.get_default_device()
    torch.set_default_dtype(result.GC.dtype)
    torch.set_default_device(result.GC.device)
    try:
        yield
    finally:
        torch.set_default_dtype(dtype)
        torch.set_default_device(device)


def array(value) -> np.ndarray:
    return value.detach().cpu().numpy() if isinstance(value, torch.Tensor) else np.asarray(value)


@dataclass(frozen=True)
class ResultTable:
    name: str
    columns: tuple[str, ...]
    rows: Iterable[tuple]


class FieldContext:
    """Per-export cache shared by field providers; never changes the solver state."""

    def __init__(self, controller, result):
        self.controller, self.result = controller, result

    @cached_property
    def coordinates(self):
        return self.controller.GC2RGC(self.result.GC)

    def instances(self):
        for name, instance in self.controller.assembly._instances.items():
            if instance.enabled is False:
                continue
            displacement = self.coordinates[instance._RGC_index].reshape(-1, 3)
            yield name, instance, displacement

    def reference_points(self):
        for index, (name, point) in enumerate(self.controller.assembly._reference_points.items(), start=1):
            if point.enabled is False:
                continue
            values = array(self.coordinates[point._RGC_index]).reshape(-1)
            yield index, name, point, values

    def element_blocks(self):
        for name, instance, displacement in self.instances():
            rotation = instance.rotation_matrix
            local = displacement if rotation is None else displacement @ rotation.to(displacement)
            for block_name, element in instance.part.elems.items():
                if len(element._elems):
                    yield name, instance, block_name, element, local

    @cached_property
    def gauss_positions(self):
        positions = {}
        for name, instance, block, element, _ in self.element_blocks():
            getter = getattr(element, 'get_gaussian_points', None)
            if not callable(getter):
                continue
            try:
                points = getter(instance.nodes)
            except NotImplementedError:
                continue
            if points is not None and array(points).size:
                positions[name, block] = array(points)
        return positions

    def gauss_blocks(self, kind: str):
        required = {
            'gauss_coordinates': (),
            'energy': ('get_potential_energy_density', 'gaussian_weight'),
            'stress': ('get_deformation_gradient', 'components_Solid'),
            'strain': ('get_deformation_gradient',),
        }[kind]
        for item in self.element_blocks():
            name, _, block, element, _ = item
            if (name, block) in self.gauss_positions and all(hasattr(element, attr) for attr in required):
                yield item


class ResultLocation(str, Enum):
    NODES = 'nodes'
    REFERENCE_POINTS = 'reference_points'
    ELEMENTS = 'elements'


NODE_KEYS = ('instance', 'node_id')
REFERENCE_POINT_KEYS = ('reference_point_id', 'reference_point')
ELEMENT_KEYS = ('instance', 'element_block', 'element_id', 'integration_point')


def record_keys(location: ResultLocation) -> tuple[str, ...]:
    return {ResultLocation.NODES: NODE_KEYS,
            ResultLocation.REFERENCE_POINTS: REFERENCE_POINT_KEYS,
            ResultLocation.ELEMENTS: ELEMENT_KEYS}[location]


def record_rows(context: FieldContext, location: ResultLocation):
    if location is ResultLocation.NODES:
        for name, instance, _ in context.instances():
            for index in range(len(instance.nodes)):
                yield name, index + 1
    elif location is ResultLocation.REFERENCE_POINTS:
        for index, name, _point, _values in context.reference_points():
            yield index, name
    else:
        for name, _, block, element, _ in context.element_blocks():
            points = context.gauss_positions.get((name, block))
            for element_id in array(element._elems_index).reshape(-1):
                if points is None:
                    yield name, block, int(element_id) + 1, None
                else:
                    for point in range(points.shape[0]):
                        yield name, block, int(element_id) + 1, point + 1


def nodal_table(context: FieldContext, kind: str) -> ResultTable:
    columns = {
        'coordinates': ('X', 'Y', 'Z'),
        'displacement': ('U1', 'U2', 'U3', 'U'),
        'deformed_coordinates': ('x', 'y', 'z'),
    }[kind]

    def rows():
        for name, instance, displacement in context.instances():
            position, value = array(instance.nodes), array(displacement)
            if kind == 'coordinates':
                data = position
            elif kind == 'deformed_coordinates':
                data = position + value
            else:
                data = np.column_stack((value, np.linalg.norm(value, axis=1)))
            for index, row in enumerate(data, start=1):
                yield name, index, *row
    return ResultTable(kind, (*NODE_KEYS, *columns), rows())


def element_coordinate_table(context: FieldContext) -> ResultTable:
    def rows():
        for name, instance, block, element, _ in context.element_blocks():
            centers = array(instance.nodes[element._elems].mean(dim=1))
            points = context.gauss_positions.get((name, block))
            for index, element_id in enumerate(array(element._elems_index).reshape(-1)):
                for point in range(points.shape[0]) if points is not None else (None,):
                    yield name, block, int(element_id) + 1, point + 1 if point is not None else None, *centers[index]
    return ResultTable('element_coordinates', (*ELEMENT_KEYS, 'CX', 'CY', 'CZ'), rows())


def reference_point_table(context: FieldContext, kind: str) -> ResultTable:
    columns = {
        'coordinates': ('X', 'Y', 'Z'),
        'displacement': ('U1', 'U2', 'U3', 'U'),
        'rotation': ('UR1', 'UR2', 'UR3', 'UR'),
        'deformed_coordinates': ('x', 'y', 'z'),
    }[kind]

    def rows():
        for index, name, point, values in context.reference_points():
            position = array(point.node).reshape(-1)
            if kind == 'coordinates':
                data = position
            elif kind == 'deformed_coordinates':
                data = position + values[:3]
            else:
                components = values[:3] if kind == 'displacement' else values[3:6]
                data = (*components, np.linalg.norm(components))
            yield index, name, *data
    return ResultTable('rp_' + kind, (*REFERENCE_POINT_KEYS, *columns), rows())


def gauss_table(context: FieldContext, kind: str) -> ResultTable:
    components = ((0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2))
    names = {'gauss_coordinates': ('X', 'Y', 'Z'),
             'energy': ('strain_energy_density', 'reference_volume', 'strain_energy'),
             'stress': ('S11', 'S22', 'S33', 'S12', 'S13', 'S23', 'S_Mises'),
             'strain': ('E11', 'E22', 'E33', 'E12', 'E13', 'E23')}

    def rows():
        for name, instance, block, element, local in context.gauss_blocks(kind):
            positions = context.gauss_positions[name, block]
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
                    tensor = piola_transpose.transpose(-1, -2) @ gradient.transpose(-1, -2) / jacobian[..., None, None]
                    tensor = (tensor + tensor.transpose(-1, -2)) * 0.5
                if instance.rotation_matrix is not None:
                    rotation = instance.rotation_matrix.to(tensor)
                    tensor = rotation @ tensor @ rotation.T
                values = torch.stack(tuple(tensor[..., a, b] for a, b in components), dim=-1)
                if kind == 'stress':
                    identity = torch.eye(3, dtype=tensor.dtype, device=tensor.device)
                    deviator = tensor - tensor.diagonal(dim1=-2, dim2=-1).sum(-1)[..., None, None] * identity / 3
                    mises = (1.5 * deviator.square().sum((-1, -2))).clamp_min(0).sqrt()
                    values = torch.cat((values, mises[..., None]), dim=-1)
            values = array(values)
            element_ids = array(element._elems_index).reshape(-1)
            for element_index, element_id in enumerate(element_ids):
                for point in range(values.shape[0]):
                    yield (name, block, int(element_id) + 1, point + 1,
                           *values[point, element_index])

    return ResultTable('gauss_' + kind,
        (*ELEMENT_KEYS, *names[kind]), rows())


@dataclass(frozen=True)
class ResultField:
    key: str
    label_key: str
    description: str
    location: ResultLocation
    extract: Callable[[FieldContext], ResultTable]
    gauss_kind: str | None = None

    def available(self, context: FieldContext) -> bool:
        if self.location is ResultLocation.REFERENCE_POINTS:
            return next(context.reference_points(), None) is not None
        return self.gauss_kind is None or next(context.gauss_blocks(self.gauss_kind), None) is not None


# Adding a physical quantity requires only a provider for one record location.
RESULT_FIELDS: dict[str, ResultField] = {
    'coordinates': ResultField('coordinates', 'ui.fea.field_coordinates', 'Global reference node coordinates.',
        ResultLocation.NODES, lambda context: nodal_table(context, 'coordinates')),
    'displacement': ResultField('displacement', 'ui.fea.field_displacement', 'Global nodal displacement components and magnitude.',
        ResultLocation.NODES, lambda context: nodal_table(context, 'displacement')),
    'deformed_coordinates': ResultField('deformed_coordinates', 'ui.fea.field_deformed_coordinates', 'Global deformed node coordinates.',
        ResultLocation.NODES, lambda context: nodal_table(context, 'deformed_coordinates')),
    'rp_coordinates': ResultField('rp_coordinates', 'ui.fea.field_rp_coordinates', 'Global reference-point coordinates.',
        ResultLocation.REFERENCE_POINTS, lambda context: reference_point_table(context, 'coordinates')),
    'rp_displacement': ResultField('rp_displacement', 'ui.fea.field_rp_displacement', 'Global reference-point translation components and magnitude.',
        ResultLocation.REFERENCE_POINTS, lambda context: reference_point_table(context, 'displacement')),
    'rp_rotation': ResultField('rp_rotation', 'ui.fea.field_rp_rotation', 'Global reference-point rotation vector components and magnitude in radians (axis-angle, not Euler angles).',
        ResultLocation.REFERENCE_POINTS, lambda context: reference_point_table(context, 'rotation')),
    'rp_deformed_coordinates': ResultField('rp_deformed_coordinates', 'ui.fea.field_rp_deformed_coordinates', 'Global translated reference-point coordinates.',
        ResultLocation.REFERENCE_POINTS, lambda context: reference_point_table(context, 'deformed_coordinates')),
    'element_coordinates': ResultField('element_coordinates', 'ui.fea.field_element_coordinates', "Mean global reference coordinates of an element's nodes.",
        ResultLocation.ELEMENTS, element_coordinate_table),
    'gauss_coordinates': ResultField('gauss_coordinates', 'ui.fea.field_gauss_coordinates', 'Global reference integration-point coordinates.',
        ResultLocation.ELEMENTS, lambda context: gauss_table(context, 'gauss_coordinates'), 'gauss_coordinates'),
    'energy': ResultField('energy', 'ui.fea.field_energy', 'Strain energy per reference volume, reference integration volume and their product.',
        ResultLocation.ELEMENTS, lambda context: gauss_table(context, 'energy'), 'energy'),
    'stress': ResultField('stress', 'ui.fea.field_stress', 'Cauchy stress in global axes, evaluated separately at each integration point.',
        ResultLocation.ELEMENTS, lambda context: gauss_table(context, 'stress'), 'stress'),
    'strain': ResultField('strain', 'ui.fea.field_strain', 'Green-Lagrange tensor strain in global reference axes; shear components are tensor shear.',
        ResultLocation.ELEMENTS, lambda context: gauss_table(context, 'strain'), 'strain'),
}


def available_fields(controller, result, location: ResultLocation | str) -> tuple[str, ...]:
    location = ResultLocation(location)
    with evaluation_defaults(result):
        context = FieldContext(controller, result)
        return tuple(key for key, field in RESULT_FIELDS.items()
                     if field.location is location and field.available(context))


def combined_table(context: FieldContext, location: ResultLocation, providers: tuple[ResultField, ...]) -> ResultTable:
    """Join provider columns onto stable record IDs without materializing the full table."""
    keys = record_keys(location)
    # Omit the integration-point identifier completely when no block has Gauss points.
    include_gauss = location is ResultLocation.ELEMENTS and bool(context.gauss_positions)
    output_keys = keys[:-1] if location is ResultLocation.ELEMENTS and not include_gauss else keys
    tables = tuple(provider.extract(context) for provider in providers)
    for table in tables:
        if table.columns[:len(keys)] != keys:
            raise ValueError(f'Field {table.name} does not use the {location.value} record identifiers.')
    columns = (*output_keys, *(column for table in tables for column in table.columns[len(keys):]))
    if len(set(columns)) != len(columns):
        raise ValueError('Selected result fields contain duplicate column names.')

    def rows():
        iterators = [iter(table.rows) for table in tables]
        pending = [next(iterator, None) for iterator in iterators]
        for record in record_rows(context, location):
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
            raise ValueError('A result field contains unknown or out-of-order record identifiers.')
    return ResultTable(location.value, columns, rows())
