"""Project finite-element result fields onto nodes for visualization."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import Any

import numpy as np
import torch

from .context import evaluation_defaults
from .fields import GAUSS_COLUMNS, FieldContext, array, gauss_values


@dataclass(frozen=True)
class ContourField:
    """A displayed scalar component of a physical result field."""

    key: str
    source: str
    component: int


CONTOUR_FIELDS = (
    ContourField("U", "displacement", 3),
    *(ContourField(f"U{axis}", "displacement", axis - 1) for axis in (1, 2, 3)),
    ContourField("S_Mises", "stress", 6),
    *(ContourField(key, "stress", index)
      for index, key in enumerate(GAUSS_COLUMNS["stress"][:-1])),
    *(ContourField(key, "strain", index)
      for index, key in enumerate(GAUSS_COLUMNS["strain"])),
    ContourField("strain_energy_density", "energy", 0),
)


class ResultContours:
    """Cache nodal projections for one finite-element model and solution.

    Gauss values are averaged by reference volume within each element and
    then averaged across adjacent elements. Nodes without values remain NaN.
    """

    def __init__(self, controller: Any, result: Any) -> None:
        self.controller = controller
        self.result = result
        self.context = FieldContext(controller, result)
        self._groups: dict[str, dict[str, np.ndarray]] = {}

    @cached_property
    def fields(self) -> tuple[ContourField, ...]:
        with evaluation_defaults(self.result), torch.no_grad():
            supported = {"displacement"}
            for kind in ("stress", "strain", "energy"):
                if next(self.context.gauss_blocks(kind), None) is not None:
                    supported.add(kind)
        return tuple(field for field in CONTOUR_FIELDS if field.source in supported)

    def values(self, field: ContourField) -> dict[str, np.ndarray]:
        """Return a scalar node array for each supported instance."""
        if field.source not in self._groups:
            with evaluation_defaults(self.result), torch.no_grad():
                self._groups[field.source] = self._evaluate(field.source)
        return {
            name: values[:, field.component]
            for name, values in self._groups[field.source].items()
        }

    def _evaluate(self, source: str) -> dict[str, np.ndarray]:
        if source == "displacement":
            values = {}
            for name, _instance, displacement in self.context.instances():
                components = array(displacement)
                values[name] = np.column_stack(
                    (components, np.linalg.norm(components, axis=1))
                )
            return values

        columns = len(GAUSS_COLUMNS[source])
        sums: dict[str, np.ndarray] = {}
        counts: dict[str, np.ndarray] = {}
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
            np.divide(
                (values * weights[..., None]).sum(axis=0),
                volumes[:, None],
                out=means,
                where=volumes[:, None] > 0,
            )
            nodes = array(element._elems).astype(np.intp)
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
