"""Viewport-independent scene descriptions produced by preview visitors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pyvista as pv

from ..theme import theme_manager


@dataclass
class MeshFaces:
    """Domain names for display-cell groups, independent of viewport actors."""

    part_name: str
    instance_name: str | None
    cell_groups: np.ndarray
    group_names: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class FaceSelection:
    """Identify a picked Part or Instance face and the named selection it represents."""
    part_name: str
    instance_name: str | None
    surface_names: tuple[str, ...]


@dataclass
class MeshItem:
    """Describe a renderable mesh, its stable scene identity, and visualization options."""
    mesh: pv.DataSet
    options: dict[str, Any] = field(default_factory=dict)
    faces: MeshFaces | None = None


@dataclass
class LabelItem:
    """Describe a spatial text annotation and its rendering options."""
    points: np.ndarray
    labels: list[str]
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class MessageItem:
    """Describe a viewport text message independently of the rendering backend."""
    text: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class PreviewScene:
    """One geometry snapshot. It contains no Qt widgets or VTK actors."""

    items: list[MeshItem | LabelItem | MessageItem] = field(default_factory=list)
    base_meshes: list[tuple[str, pv.DataSet, MeshItem]] = field(default_factory=list)
    instance_legend: list[tuple[str, str]] = field(default_factory=list)
    show_bounding_box: bool = False

    def add_mesh(self, mesh: pv.DataSet, **options: Any) -> MeshItem:
        """Add mesh.

        Args:
            mesh (pv.DataSet): Mesh used for geometric evaluation or visualization.
            **options: Additional keyword arguments accepted by the shared interface.

        Returns:
            MeshItem: Add mesh.
        """
        item = MeshItem(mesh, options)
        self.items.append(item)
        return item

    def add_base(
        self,
        instance_name: str,
        mesh: pv.DataSet,
        *,
        faces: MeshFaces | None = None,
        **options: Any,
    ) -> None:
        """Add base.

        Args:
            instance_name (str): Registered Instance name in the assembly.
            mesh (pv.DataSet): Mesh used for geometric evaluation or visualization.
            faces (MeshFaces | None): Face selection or mesh connectivity required by the selected
                surface operation.
            **options: Additional keyword arguments accepted by the shared interface.
        """
        item = self.add_mesh(mesh, **options)
        item.faces = faces
        self.base_meshes.append((instance_name, mesh, item))

    def add_point_labels(self, points, labels, **options: Any) -> LabelItem:
        """Add point labels.

        Args:
            points: Point coordinates in the representation expected by this operation.
            labels: Display labels aligned with the component values.
            **options: Additional keyword arguments accepted by the shared interface.

        Returns:
            LabelItem: Add point labels.
        """
        item = LabelItem(np.asarray(points), list(labels), options)
        self.items.append(item)
        return item

    def add_text(self, text: str, **options: Any) -> MessageItem:
        """Add text.

        Args:
            text (str): Text displayed, parsed, or inserted by this operation.
            **options: Additional keyword arguments accepted by the shared interface.

        Returns:
            MessageItem: Add text.
        """
        item = MessageItem(text, options)
        self.items.append(item)
        return item

    @property
    def bounds(self) -> tuple[float, float, float, float, float, float] | None:
        """Bounds of the complete geometry, excluding annotations and overlays.

        Returns:
            tuple[float, float, float, float, float, float] | None: Bounds of the complete geometry,
                excluding annotations and overlays.
        """
        bounds = [mesh.bounds for _, mesh, _ in self.base_meshes if mesh.n_points]
        if not bounds:
            return None
        lo = np.min([[b[0], b[2], b[4]] for b in bounds], axis=0)
        hi = np.max([[b[1], b[3], b[5]] for b in bounds], axis=0)
        return (
            float(lo[0]),
            float(hi[0]),
            float(lo[1]),
            float(hi[1]),
            float(lo[2]),
            float(hi[2]),
        )

    @property
    def diagonal(self) -> float:
        """Return diagonal.

        Returns:
            float: Diagonal.
        """
        bounds = self.bounds
        if bounds is None:
            return theme_manager.palette.viewer.scene_fallback_diagonal
        return (
            float(np.linalg.norm(np.asarray(bounds)[1::2] - np.asarray(bounds)[::2]))
            or theme_manager.palette.viewer.scene_fallback_diagonal
        )

    @property
    def glyph_scale(self) -> float:
        """Size symbols by typical Part width, capped by the scene diagonal.

        Returns:
            float: Size symbols by typical Part width, capped by the scene diagonal.
        """
        widths = []
        for _, mesh, _ in self.base_meshes:
            if not mesh.n_points:
                continue
            extents = np.diff(np.asarray(mesh.bounds).reshape(3, 2), axis=1).ravel()
            extents = extents[extents > 0]
            if extents.size:
                widths.append(float(np.median(extents)))
        return (
            min(
                self.diagonal,
                theme_manager.palette.viewer.glyph_width_ratio
                * float(np.median(widths)),
            )
            if widths
            else self.diagonal
        )


@dataclass
class ArrowLoad:
    """Describe an applied load rendered as a directed arrow."""
    start: np.ndarray
    vector: np.ndarray
    color: str
    label: str


@dataclass
class MomentLoad:
    """Describe an applied moment rendered as an oriented arc and arrow."""
    center: np.ndarray
    vector: np.ndarray
    label: str


@dataclass
class SpringLoad:
    """Describe the endpoints and label of a spring visualization glyph."""
    start: np.ndarray
    end: np.ndarray
    label: str


@dataclass
class MarkerLoad:
    """Describe a reference-point or boundary-condition marker in the preview scene."""
    location: np.ndarray
    label: str
    color: str
    is_reference_point: bool = False


@dataclass
class CouplingLoad:
    """Describe the reference point, target region, and annotation of a coupling glyph."""
    reference_point: np.ndarray
    node_set_center: np.ndarray
    label: str
    surface: pv.DataSet | None = None
    surface_label: str = ""


@dataclass
class LoadScene:
    """Collect load, boundary-condition, reference-point, and coupling glyph descriptions."""
    scale: float
    annotation_scale: float = 0.0
    items: list[
        MeshItem
        | MessageItem
        | ArrowLoad
        | MomentLoad
        | SpringLoad
        | MarkerLoad
        | CouplingLoad
    ] = field(default_factory=list)
