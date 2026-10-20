"""Scalar contour fields using the same physical quantities as result exports."""

from dataclasses import dataclass
from functools import cached_property

import numpy as np
import torch

from ...postprocess.fields import (
    GAUSS_COLUMNS, FieldContext, array, evaluation_defaults, gauss_values,
)


@dataclass(frozen=True)
class DisplayField:
    key: str
    label_key: str
    source: str
    component: int


DISPLAY_FIELDS = (
    DisplayField('U', 'ui.fea.contour_displacement', 'displacement', 3),
    *(DisplayField(f'U{axis}', f'ui.fea.contour_U{axis}', 'displacement', axis - 1)
      for axis in (1, 2, 3)),
    DisplayField('S_Mises', 'ui.fea.contour_mises', 'stress', 6),
    *(DisplayField(key, 'ui.fea.contour_stress', 'stress', index)
      for index, key in enumerate(GAUSS_COLUMNS['stress'][:-1])),
    *(DisplayField(key, 'ui.fea.contour_strain', 'strain', index)
      for index, key in enumerate(GAUSS_COLUMNS['strain'])),
    DisplayField('strain_energy_density', 'ui.fea.contour_energy', 'energy', 0),
)


class ResultContours:
    """Cache one immutable solution's fields, independently of camera and deformation.

    Stress/strain/energy density are reference-volume-weighted Gauss averages
    per element, then arithmetic averages of incident elements at each node.
    This is a contour projection, not stress extrapolation. Unsupported nodes
    stay NaN; exports retain all original integration-point values.
    """

    def __init__(self, controller, result):
        self.controller, self.result = controller, result
        self.context = FieldContext(controller, result)
        self._groups = {}

    @cached_property
    def fields(self) -> tuple[DisplayField, ...]:
        with evaluation_defaults(self.result), torch.no_grad():
            supported = {'displacement'}
            for kind in ('stress', 'strain', 'energy'):
                if next(self.context.gauss_blocks(kind), None) is not None:
                    supported.add(kind)
            return tuple(field for field in DISPLAY_FIELDS if field.source in supported)

    def values(self, field: DisplayField) -> dict[str, np.ndarray]:
        if field.source not in self._groups:
            with evaluation_defaults(self.result), torch.no_grad():
                self._groups[field.source] = self._evaluate(field.source)
        return {name: values[:, field.component]
                for name, values in self._groups[field.source].items()}

    def _evaluate(self, source: str) -> dict[str, np.ndarray]:
        if source == 'displacement':
            return {name: np.column_stack((array(displacement),
                        np.linalg.norm(array(displacement), axis=1)))
                    for name, _instance, displacement in self.context.instances()}

        columns = len(GAUSS_COLUMNS[source])
        sums = {}
        counts = {}
        for name, _block, element, values in gauss_values(self.context, source):
            if name not in sums:
                nodes = len(self.controller.assembly._instances[name].nodes)
                sums[name] = np.zeros((nodes, columns))
                counts[name] = np.zeros((nodes, 1))
            weights = array(element.gaussian_weight)
            if weights.ndim == 1:
                weights = weights[:, None]
            weights = np.broadcast_to(weights, values.shape[:2])
            volumes = weights.sum(axis=0)
            means = np.full(values.shape[1:], np.nan)
            np.divide((values * weights[..., None]).sum(axis=0), volumes[:, None],
                      out=means, where=volumes[:, None] > 0)
            nodes = array(element._elems).astype(np.intp)
            valid = np.isfinite(means).all(axis=1)
            np.add.at(sums[name], nodes[valid].ravel(),
                      np.repeat(means[valid], nodes.shape[1], axis=0))
            np.add.at(counts[name], nodes[valid].ravel(), 1)
        return {name: np.divide(values, counts[name], out=np.full_like(values, np.nan),
                                where=counts[name] > 0)
                for name, values in sums.items()}
