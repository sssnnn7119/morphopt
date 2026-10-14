"""Viewport-independent scene descriptions produced by preview visitors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pyvista as pv


@dataclass
class MeshItem:
    mesh: pv.DataSet
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class LabelItem:
    points: np.ndarray
    labels: list[str]
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class MessageItem:
    text: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class PreviewScene:
    """One geometry snapshot. It contains no Qt widgets or VTK actors."""

    items: list[MeshItem | LabelItem | MessageItem] = field(default_factory=list)
    base_meshes: list[tuple[str, pv.DataSet, MeshItem]] = field(default_factory=list)

    def add_mesh(self, mesh: pv.DataSet, **options: Any) -> MeshItem:
        item = MeshItem(mesh, options)
        self.items.append(item)
        return item

    def add_base(self, instance_name: str, mesh: pv.DataSet, **options: Any) -> None:
        item = self.add_mesh(mesh, **options)
        self.base_meshes.append((instance_name, mesh, item))

    def add_point_labels(self, points, labels, **options: Any) -> LabelItem:
        item = LabelItem(np.asarray(points), list(labels), options)
        self.items.append(item)
        return item

    def add_text(self, text: str, **options: Any) -> MessageItem:
        item = MessageItem(text, options)
        self.items.append(item)
        return item

    @property
    def diagonal(self) -> float:
        bounds = [mesh.bounds for _, mesh, _ in self.base_meshes if mesh.n_points]
        if not bounds:
            return 10.0
        lo = np.min([[b[0], b[2], b[4]] for b in bounds], axis=0)
        hi = np.max([[b[1], b[3], b[5]] for b in bounds], axis=0)
        return float(np.linalg.norm(hi - lo)) or 10.0


@dataclass
class ArrowLoad:
    start: np.ndarray
    vector: np.ndarray
    color: str
    label: str


@dataclass
class MomentLoad:
    center: np.ndarray
    vector: np.ndarray
    label: str


@dataclass
class SpringLoad:
    start: np.ndarray
    end: np.ndarray
    label: str


@dataclass
class MarkerLoad:
    location: np.ndarray
    label: str
    color: str


@dataclass
class LoadScene:
    scale: float
    items: list[MeshItem | MessageItem | ArrowLoad | MomentLoad | SpringLoad | MarkerLoad] = field(default_factory=list)
