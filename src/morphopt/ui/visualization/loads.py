"""Load visitors turn definition values into glyph data, without drawing actors."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, TypeVar

import numpy as np
import pyvista as pv

from ..i18n import tr
from ..model.node_types.loads import (
    BodyForceNode,
    BoundaryConditionNode,
    BoundaryConditionRPNode,
    ConcentratedForceNode,
    ConcentratedMomentNode,
    CoupleNode,
    PenaltyDoFNode,
    PressureNode,
    ReferencePointNode,
    SpringBetweenRPsNode,
    SpringToGroundNode,
)
from ..model.problem import FEAComponentNode
from ..theme import theme_manager
from .geometry import PreviewGeometry
from .scene import (
    ArrowLoad,
    CouplingLoad,
    LoadScene,
    MarkerLoad,
    MeshItem,
    MessageItem,
    MomentLoad,
    SpringLoad,
)

LoadT = TypeVar("LoadT", bound=FEAComponentNode)
LoadHandler = Callable[[PreviewGeometry, LoadScene, Any, list[float]], None]


class LoadPreviewVisitor:
    """Register handlers by component type; new loads do not change the viewport."""

    def __init__(self) -> None:
        self._handlers: dict[type[FEAComponentNode], LoadHandler] = {
            PressureNode: self.pressure,
            ConcentratedForceNode: self.force,
            ConcentratedMomentNode: self.moment,
            BodyForceNode: self.bodyforce,
            SpringToGroundNode: self.spring_to_ground,
            SpringBetweenRPsNode: self.spring_between,
            PenaltyDoFNode: self.penalty,
        }
        self._always_visible_handlers: dict[type[FEAComponentNode], LoadHandler] = {
            BoundaryConditionNode: self.boundary_condition,
            BoundaryConditionRPNode: self.boundary_condition_rp,
            ReferencePointNode: self.reference_point,
            CoupleNode: self.couple,
        }

    def register(
        self,
        node_type: type[LoadT],
        handler: Callable[[PreviewGeometry, LoadScene, LoadT, list[float]], None],
        *,
        boundary: bool = False,
    ) -> None:
        (self._always_visible_handlers if boundary else self._handlers)[node_type] = (
            handler
        )

    def build(self, geometry: PreviewGeometry, step_index: int | None) -> LoadScene:
        scene = LoadScene(
            geometry.scene.glyph_scale,
            annotation_scale=geometry.scene.diagonal,
        )
        problem = geometry.problem
        for component in problem.fea_components():
            self.visit(geometry, scene, component, [], boundary=True)
        steps = problem.steps
        if (
            steps is None
            or not isinstance(step_index, int)
            or not 0 <= step_index < len(steps.step_values)
        ):
            return scene
        components = {
            component.name: component for component in problem.fea_components()
        }
        for reference, raw_values in (steps.step_values[step_index] or {}).items():
            component = (
                reference
                if isinstance(reference, FEAComponentNode)
                else components.get(str(reference))
            )
            if component is None:
                continue
            self.visit(geometry, scene, component, raw_values or [])
        return scene

    def visit(
        self,
        geometry: PreviewGeometry,
        scene: LoadScene,
        component: FEAComponentNode,
        raw_values: list,
        *,
        boundary: bool = False,
    ) -> None:
        handlers = self._always_visible_handlers if boundary else self._handlers
        handler = next(
            (handlers[cls] for cls in type(component).__mro__ if cls in handlers), None
        )
        if handler is None:
            return
        try:
            values = [float(geometry.values.resolve(value)) for value in raw_values]
            handler(geometry, scene, component, values)
        except (
            NameError,
            SyntaxError,
            TypeError,
            ValueError,
            KeyError,
            OSError,
            AttributeError,
            IndexError,
            RuntimeError,
            NotImplementedError,
        ) as exc:
            # Preview errors describe the incomplete definition; other loads
            # still render, and the definition is never silently changed.
            scene.items.append(
                MessageItem(
                    tr("ui.visualization.load.error", name=component.name, error=exc),
                    dict(
                        position="upper_left",
                        color=theme_manager.palette.viewer.render.marker_color_annotation_error,
                        font_size=theme_manager.palette.viewer.render.label_font_size,
                    ),
                )
            )

    @staticmethod
    def rp_location(
        geometry: PreviewGeometry,
        reference: ReferencePointNode | None,
    ) -> np.ndarray | None:
        if reference is None:
            return None
        return np.asarray(
            geometry.values.resolve(reference.rp_location or [0.0, 0.0, 0.0]),
            dtype=float,
        )

    @staticmethod
    def pressure(
        geometry: PreviewGeometry,
        scene: LoadScene,
        component: PressureNode,
        values: list[float],
    ) -> None:
        pressure = values[0] if values else 0.0
        if abs(pressure) <= theme_manager.palette.viewer.loads.pressure_zero_tolerance:
            return
        mesh = geometry.mesh_for_surface(component, str(component.surface_name or ""))
        if mesh is None:
            return
        scene.items.append(
            MeshItem(
                mesh,
                dict(
                    color=theme_manager.palette.viewer.loads.pressure_surface_color,
                    opacity=theme_manager.palette.viewer.loads.pressure_opacity,
                    show_edges=False,
                    smooth_shading=True,
                    ambient=theme_manager.palette.viewer.loads.pressure_ambient,
                    diffuse=theme_manager.palette.viewer.loads.pressure_diffuse,
                    specular=theme_manager.palette.viewer.loads.pressure_specular,
                    preview_offset=(
                        geometry.scene.diagonal
                        * theme_manager.palette.viewer.loads.pressure_preview_offset_ratio
                    ),
                ),
            )
        )
        surface = (
            mesh
            if isinstance(mesh, pv.PolyData)
            else mesh.extract_surface(algorithm="dataset_surface")
        )
        try:
            normalized = surface.compute_normals(
                cell_normals=True, point_normals=False, inplace=False
            )
            centers = normalized.cell_centers().points
            normals = np.asarray(normalized.cell_data["Normals"], dtype=float)
        except (KeyError, ValueError, AttributeError):
            return
        if not len(centers) or not len(normals):
            return
        indices = np.unique(
            np.linspace(
                0,
                len(centers) - 1,
                min(
                    theme_manager.palette.viewer.loads.pressure_surface_samples,
                    len(centers),
                ),
                dtype=int,
            )
        )
        for sample, index in enumerate(indices):
            scene.items.append(
                ArrowLoad(
                    centers[index],
                    normals[index] * np.sign(pressure),
                    theme_manager.palette.viewer.loads.pressure_arrow_color,
                    tr(
                        "ui.visualization.load.pressure",
                        name=component.name,
                        value=pressure,
                        instance=component.instance_name,
                        surface=component.surface_name,
                    )
                    if sample == 0
                    else "",
                )
            )

    @classmethod
    def force(
        cls,
        geometry: PreviewGeometry,
        scene: LoadScene,
        component: ConcentratedForceNode,
        values: list[float],
    ) -> None:
        point = cls.rp_location(geometry, component.reference_point)
        if point is not None:
            vector = vector3(values)
            scene.items.append(
                ArrowLoad(
                    point,
                    vector,
                    theme_manager.palette.viewer.loads.force_color,
                    tr(
                        "ui.visualization.load.force",
                        name=component.name,
                        rp=component.rp_name,
                        vector=vector_text(vector),
                    ),
                )
            )

    @classmethod
    def moment(
        cls,
        geometry: PreviewGeometry,
        scene: LoadScene,
        component: ConcentratedMomentNode,
        values: list[float],
    ) -> None:
        point = cls.rp_location(geometry, component.reference_point)
        if point is not None:
            vector = vector3(values)
            scene.items.append(
                MomentLoad(
                    point,
                    vector,
                    tr(
                        "ui.visualization.load.moment",
                        name=component.name,
                        rp=component.rp_name,
                        vector=vector_text(vector),
                    ),
                )
            )

    @staticmethod
    def bodyforce(
        geometry: PreviewGeometry,
        scene: LoadScene,
        component: BodyForceNode,
        values: list[float],
    ) -> None:
        center = geometry.instance_center(component.instance_name or "")
        if center is not None:
            vector = vector3(values)
            scene.items.append(
                ArrowLoad(
                    center,
                    vector,
                    theme_manager.palette.viewer.loads.body_force_color,
                    tr(
                        "ui.visualization.load.bodyforce",
                        name=component.name,
                        instance=component.instance_name,
                        elements=component.element_name,
                        vector=vector_text(vector),
                    ),
                )
            )

    @classmethod
    def spring_to_ground(
        cls,
        geometry: PreviewGeometry,
        scene: LoadScene,
        component: SpringToGroundNode,
        values: list[float],
    ) -> None:
        point = cls.rp_location(geometry, component.reference_point)
        if (
            point is not None
            and len(values) >= 5
            and abs(values[0]) > theme_manager.palette.viewer.loads.glyph_zero_tolerance
        ):
            scene.items.append(
                SpringLoad(
                    point,
                    np.asarray(values[2:5]),
                    tr(
                        "ui.visualization.load.spring_to_ground",
                        name=component.name,
                        rp=component.rp_name,
                        ground=vector_text(values[2:5]),
                        stiffness=values[0],
                        rest_length=values[1],
                    ),
                )
            )

    @classmethod
    def spring_between(
        cls,
        geometry: PreviewGeometry,
        scene: LoadScene,
        component: SpringBetweenRPsNode,
        values: list[float],
    ) -> None:
        first = cls.rp_location(geometry, component.reference_point1)
        second = cls.rp_location(geometry, component.reference_point2)
        if (
            first is not None
            and second is not None
            and len(values) >= 2
            and abs(values[0]) > theme_manager.palette.viewer.loads.glyph_zero_tolerance
        ):
            scene.items.append(
                SpringLoad(
                    first,
                    second,
                    tr(
                        "ui.visualization.load.spring_between",
                        name=component.name,
                        rp1=component.rp_name1,
                        rp2=component.rp_name2,
                        stiffness=values[0],
                        rest_length=values[1],
                    ),
                )
            )

    @staticmethod
    def penalty(
        geometry: PreviewGeometry,
        scene: LoadScene,
        component: PenaltyDoFNode,
        values: list[float],
    ) -> None:
        center = geometry.object_center(str(component.obj_name or ""))
        if center is not None and len(values) >= 2:
            scene.items.append(
                MarkerLoad(
                    center,
                    tr(
                        "ui.visualization.load.penalty",
                        name=component.name,
                        object=component.obj_name,
                        object_type=component.obj_type,
                        dof=component.s,
                        stiffness=values[0],
                        target=values[1],
                    ),
                    theme_manager.palette.viewer.render.marker_color_penalty,
                )
            )

    @staticmethod
    def boundary_condition(
        geometry: PreviewGeometry,
        scene: LoadScene,
        component: BoundaryConditionNode,
        values: list[float],
    ) -> None:
        name = str(component.set_nodes_name or "")
        mesh = geometry.mesh_for_surface(component, name)
        if mesh is not None:
            scene.items.append(
                MeshItem(
                    mesh,
                    dict(
                        color=theme_manager.palette.viewer.loads.boundary_color,
                        opacity=theme_manager.palette.viewer.loads.boundary_opacity,
                        show_edges=False,
                        lighting=False,
                        preview_offset=(
                            geometry.scene.diagonal
                            * theme_manager.palette.viewer.loads.boundary_preview_offset_ratio
                        ),
                    ),
                )
            )
            outline = mesh.extract_feature_edges(
                boundary_edges=True,
                feature_edges=False,
                manifold_edges=False,
                non_manifold_edges=False,
            )
            if outline.n_points:
                scene.items.append(
                    MeshItem(
                        outline.tube(
                            radius=geometry.scene.glyph_scale
                            * theme_manager.palette.viewer.loads.boundary_outline_width_ratio
                        ),
                        dict(
                            color=theme_manager.palette.viewer.loads.boundary_outline_color,
                            lighting=False,
                        ),
                    )
                )
        center = geometry.node_set_center(component.instance_name or "", name)
        if center is not None:
            scene.items.append(
                MarkerLoad(
                    center,
                    tr(
                        "ui.visualization.load.boundary",
                        name=component.name,
                        instance=component.instance_name,
                        nodeset=name,
                        dofs=fixed_dofs_text(geometry, component),
                    ),
                    theme_manager.palette.viewer.loads.boundary_marker_color,
                )
            )

    @classmethod
    def boundary_condition_rp(
        cls,
        geometry: PreviewGeometry,
        scene: LoadScene,
        component: BoundaryConditionRPNode,
        values: list[float],
    ) -> None:
        point = cls.rp_location(geometry, component.reference_point)
        if point is not None:
            scene.items.append(
                MarkerLoad(
                    point,
                    tr(
                        "ui.visualization.load.boundary_rp",
                        name=component.name,
                        rp=component.rp_name,
                        dofs=fixed_dofs_text(geometry, component),
                    ),
                    theme_manager.palette.viewer.loads.boundary_marker_color,
                )
            )

    @classmethod
    def reference_point(
        cls,
        geometry: PreviewGeometry,
        scene: LoadScene,
        component: ReferencePointNode,
        values: list[float],
    ) -> None:
        point = cls.rp_location(geometry, component)
        if point is not None:
            scene.items.append(
                MarkerLoad(
                    point,
                    tr(
                        "ui.visualization.load.reference_point",
                        name=component.name,
                        x=point[0],
                        y=point[1],
                        z=point[2],
                    ),
                    theme_manager.palette.viewer.render.marker_color_reference_point,
                    is_reference_point=True,
                )
            )

    @classmethod
    def couple(
        cls,
        geometry: PreviewGeometry,
        scene: LoadScene,
        component: CoupleNode,
        values: list[float],
    ) -> None:
        reference_point = cls.rp_location(geometry, component.reference_point)
        node_set_center = geometry.node_set_center(
            component.instance_name or "", component.set_nodes_name or ""
        )
        if reference_point is None or node_set_center is None:
            return
        surface = geometry.mesh_for_surface(
            component, str(component.set_nodes_name or "")
        )
        label = tr(
            "ui.visualization.load.coupling",
            name=component.name,
            rp=component.rp_name,
            instance=component.instance_name,
            nodeset=component.set_nodes_name,
        )
        scene.items.append(
            CouplingLoad(
                reference_point,
                node_set_center,
                label,
                surface,
                label,
            )
        )


def vector3(values: list[float]) -> np.ndarray:
    vector = np.zeros(3, dtype=float)
    vector[: min(3, len(values))] = values[:3]
    return vector


def vector_text(values: Sequence[float] | np.ndarray) -> str:
    """Format coordinates or vector components without assuming physical units."""
    return "[" + ", ".join(f"{value:.6g}" for value in values) + "]"


def fixed_dofs_text(geometry: PreviewGeometry, component: FEAComponentNode) -> str:
    names = ("X", "Y", "Z", "Rx", "Ry", "Rz")
    return (
        "["
        + ", ".join(
            names[index] for index in geometry.values.resolve(component.index_dof or [])
        )
        + "]"
    )
