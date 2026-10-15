"""Load visitors turn definition values into glyph data, without drawing actors."""
from __future__ import annotations

from collections.abc import Callable, Sequence
import numpy as np
import pyvista as pv
from ...constants import CONSTANT
from ..model.problem import FEAComponentNode
from ..i18n import tr
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

LoadHandler = Callable[[PreviewGeometry, LoadScene, FEAComponentNode, list[float]], None]


class LoadPreviewVisitor:
    """Register handlers by interface type; new loads do not change the viewport."""

    def __init__(self) -> None:
        self._handlers: dict[str, LoadHandler] = {
            "Pressure": self.pressure,
            "ConcentratedForce": self.force,
            "ConcentratedMoment": self.moment,
            "Bodyforce": self.bodyforce,
            "SpringToGround": self.spring_to_ground,
            "SpringBetweenRPs": self.spring_between,
            "PenaltyDoF": self.penalty,
        }
        self._always_visible_handlers: dict[str, LoadHandler] = {
            "BoundaryCondition": self.boundary_condition,
            "BoundaryConditionRP": self.boundary_condition_rp,
            "ReferencePoint": self.reference_point,
            "Couple": self.couple,
        }

    def register(
        self,
        interface_type: str,
        handler: LoadHandler,
        *,
        boundary: bool = False,
    ) -> None:
        (self._always_visible_handlers if boundary else self._handlers)[interface_type] = handler

    def build(self, geometry: PreviewGeometry, step_index: int | None) -> LoadScene:
        scene = LoadScene(
            geometry.scene.glyph_scale,
            annotation_scale=geometry.scene.diagonal,
        )
        problem = geometry.problem
        for interface in problem.interfaces():
            self.visit(geometry, scene, interface, [], boundary=True)
        steps = problem.steps
        if steps is None or not isinstance(step_index, int) or not 0 <= step_index < len(steps.step_values):
            return scene
        interfaces = {interface.name: interface for interface in problem.interfaces()}
        for reference, raw_values in (steps.step_values[step_index] or {}).items():
            interface = reference if isinstance(reference, FEAComponentNode) else interfaces.get(str(reference))
            if interface is None:
                continue
            self.visit(geometry, scene, interface, raw_values or [])
        return scene

    def visit(
        self,
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: FEAComponentNode,
        raw_values: list,
        *,
        boundary: bool = False,
    ) -> None:
        handlers = self._always_visible_handlers if boundary else self._handlers
        handler = handlers.get(interface.interface_type)
        if handler is None:
            return
        try:
            values = [float(geometry.values.resolve(value)) for value in raw_values]
            handler(geometry, scene, interface, values)
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
            scene.items.append(MessageItem(
                tr("ui.visualization.load.error", name=interface.name, error=exc),
                dict(
                    position="upper_left",
                    color=CONSTANT.UI.VIEWER.RENDER.MARKER_COLOR_ANNOTATION_ERROR,
                    font_size=CONSTANT.UI.VIEWER.RENDER.LABEL_FONT_SIZE,
                ),
            ))

    @staticmethod
    def rp_location(
        geometry: PreviewGeometry,
        reference: FEAComponentNode | None,
    ) -> np.ndarray | None:
        if reference is None:
            return None
        return np.asarray(geometry.values.resolve(reference.rp_location or [0., 0., 0.]), dtype=float)

    @staticmethod
    def pressure(
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: FEAComponentNode,
        values: list[float],
    ) -> None:
        pressure = values[0] if values else 0.
        if abs(pressure) <= CONSTANT.UI.VIEWER.LOADS.PRESSURE_ZERO_TOLERANCE:
            return
        mesh = geometry.mesh_for_surface(interface, str(interface.surface_name or ""))
        if mesh is None:
            return
        scene.items.append(
            MeshItem(
                mesh,
                dict(
                    color=CONSTANT.UI.VIEWER.LOADS.PRESSURE_SURFACE_COLOR,
                    opacity=CONSTANT.UI.VIEWER.LOADS.PRESSURE_OPACITY,
                    show_edges=False,
                    smooth_shading=True,
                    ambient=CONSTANT.UI.VIEWER.LOADS.PRESSURE_AMBIENT,
                    diffuse=CONSTANT.UI.VIEWER.LOADS.PRESSURE_DIFFUSE,
                    specular=CONSTANT.UI.VIEWER.LOADS.PRESSURE_SPECULAR,
                    preview_offset=(
                        geometry.scene.diagonal
                        * CONSTANT.UI.VIEWER.LOADS.PRESSURE_PREVIEW_OFFSET_RATIO
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
            normalized = surface.compute_normals(cell_normals=True, point_normals=False, inplace=False)
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
                min(CONSTANT.UI.VIEWER.LOADS.PRESSURE_SURFACE_SAMPLES, len(centers)),
                dtype=int,
            )
        )
        for sample, index in enumerate(indices):
            scene.items.append(ArrowLoad(
                centers[index],
                normals[index] * np.sign(pressure),
                CONSTANT.UI.VIEWER.LOADS.PRESSURE_ARROW_COLOR,
                tr(
                    "ui.visualization.load.pressure", name=interface.name, value=pressure,
                    instance=interface.instance_name, surface=interface.surface_name,
                ) if sample == 0 else "",
            ))

    @classmethod
    def force(
        cls,
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: FEAComponentNode,
        values: list[float],
    ) -> None:
        point = cls.rp_location(geometry, interface.reference_point)
        if point is not None:
            vector = vector3(values)
            scene.items.append(ArrowLoad(
                point,
                vector,
                CONSTANT.UI.VIEWER.LOADS.FORCE_COLOR,
                tr("ui.visualization.load.force", name=interface.name,
                   rp=interface.rp_name, vector=vector_text(vector)),
            ))

    @classmethod
    def moment(
        cls,
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: FEAComponentNode,
        values: list[float],
    ) -> None:
        point = cls.rp_location(geometry, interface.reference_point)
        if point is not None:
            vector = vector3(values)
            scene.items.append(MomentLoad(
                point, vector, tr("ui.visualization.load.moment", name=interface.name,
                                  rp=interface.rp_name, vector=vector_text(vector)),
            ))

    @staticmethod
    def bodyforce(
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: FEAComponentNode,
        values: list[float],
    ) -> None:
        center = geometry.instance_center(interface.instance_name or "")
        if center is not None:
            vector = vector3(values)
            scene.items.append(ArrowLoad(
                center,
                vector,
                CONSTANT.UI.VIEWER.LOADS.BODY_FORCE_COLOR,
                tr("ui.visualization.load.bodyforce", name=interface.name,
                   instance=interface.instance_name, elements=interface.element_name,
                   vector=vector_text(vector)),
            ))

    @classmethod
    def spring_to_ground(
        cls,
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: FEAComponentNode,
        values: list[float],
    ) -> None:
        point = cls.rp_location(geometry, interface.reference_point)
        if (
            point is not None
            and len(values) >= 5
            and abs(values[0]) > CONSTANT.UI.VIEWER.LOADS.GLYPH_ZERO_TOLERANCE
        ):
            scene.items.append(SpringLoad(
                point, np.asarray(values[2:5]),
                tr("ui.visualization.load.spring_to_ground", name=interface.name,
                   rp=interface.rp_name, ground=vector_text(values[2:5]),
                   stiffness=values[0], rest_length=values[1]),
            ))

    @classmethod
    def spring_between(
        cls,
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: FEAComponentNode,
        values: list[float],
    ) -> None:
        first = cls.rp_location(geometry, interface.reference_point1)
        second = cls.rp_location(geometry, interface.reference_point2)
        if (
            first is not None
            and second is not None
            and len(values) >= 2
            and abs(values[0]) > CONSTANT.UI.VIEWER.LOADS.GLYPH_ZERO_TOLERANCE
        ):
            scene.items.append(SpringLoad(
                first, second, tr("ui.visualization.load.spring_between", name=interface.name,
                                  rp1=interface.rp_name1, rp2=interface.rp_name2,
                                  stiffness=values[0], rest_length=values[1]),
            ))

    @staticmethod
    def penalty(
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: FEAComponentNode,
        values: list[float],
    ) -> None:
        center = geometry.object_center(str(interface.obj_name or ""))
        if center is not None and len(values) >= 2:
            scene.items.append(MarkerLoad(
                center, tr("ui.visualization.load.penalty", name=interface.name,
                           object=interface.obj_name, object_type=interface.obj_type,
                           dof=interface.s, stiffness=values[0], target=values[1]),
                CONSTANT.UI.VIEWER.RENDER.MARKER_COLOR_PENALTY,
            ))

    @staticmethod
    def boundary_condition(
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: FEAComponentNode,
        values: list[float],
    ) -> None:
        name = str(interface.set_nodes_name or "")
        mesh = geometry.mesh_for_surface(interface, name)
        if mesh is not None:
            scene.items.append(
                MeshItem(
                    mesh,
                    dict(
                        color=CONSTANT.UI.VIEWER.LOADS.BOUNDARY_COLOR,
                        opacity=CONSTANT.UI.VIEWER.LOADS.BOUNDARY_OPACITY,
                        show_edges=False,
                        lighting=False,
                        preview_offset=(
                            geometry.scene.diagonal
                            * CONSTANT.UI.VIEWER.LOADS.BOUNDARY_PREVIEW_OFFSET_RATIO
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
                            * CONSTANT.UI.VIEWER.LOADS.BOUNDARY_OUTLINE_WIDTH_RATIO
                        ),
                        dict(
                            color=CONSTANT.UI.VIEWER.LOADS.BOUNDARY_OUTLINE_COLOR,
                            lighting=False,
                        ),
                    )
                )
        center = geometry.node_set_center(interface.instance_name or "", name)
        if center is not None:
            scene.items.append(MarkerLoad(
                center, tr("ui.visualization.load.boundary", name=interface.name,
                           instance=interface.instance_name, nodeset=name,
                           dofs=fixed_dofs_text(geometry, interface)),
                CONSTANT.UI.VIEWER.LOADS.BOUNDARY_MARKER_COLOR,
            ))

    @classmethod
    def boundary_condition_rp(
        cls,
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: FEAComponentNode,
        values: list[float],
    ) -> None:
        point = cls.rp_location(geometry, interface.reference_point)
        if point is not None:
            scene.items.append(MarkerLoad(
                point, tr("ui.visualization.load.boundary_rp", name=interface.name,
                          rp=interface.rp_name, dofs=fixed_dofs_text(geometry, interface)),
                CONSTANT.UI.VIEWER.LOADS.BOUNDARY_MARKER_COLOR,
            ))

    @classmethod
    def reference_point(
        cls,
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: FEAComponentNode,
        values: list[float],
    ) -> None:
        point = cls.rp_location(geometry, interface)
        if point is not None:
            scene.items.append(
                MarkerLoad(
                    point,
                    tr(
                        "ui.visualization.load.reference_point",
                        name=interface.name,
                        x=point[0],
                        y=point[1],
                        z=point[2],
                    ),
                    "#f5a623",
                    is_reference_point=True,
                )
            )

    @classmethod
    def couple(
        cls,
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: FEAComponentNode,
        values: list[float],
    ) -> None:
        reference_point = cls.rp_location(geometry, interface.reference_point)
        node_set_center = geometry.node_set_center(
            interface.instance_name or "", interface.set_nodes_name or ""
        )
        if reference_point is None or node_set_center is None:
            return
        surface = geometry.mesh_for_surface(
            interface, str(interface.set_nodes_name or "")
        )
        label = tr(
            "ui.visualization.load.coupling", name=interface.name,
            rp=interface.rp_name, instance=interface.instance_name,
            nodeset=interface.set_nodes_name,
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
    vector[:min(3, len(values))] = values[:3]
    return vector


def vector_text(values: Sequence[float] | np.ndarray) -> str:
    """Format coordinates or vector components without assuming physical units."""
    return "[" + ", ".join(f"{value:.6g}" for value in values) + "]"


def fixed_dofs_text(geometry: PreviewGeometry, interface: FEAComponentNode) -> str:
    names = ("X", "Y", "Z", "Rx", "Ry", "Rz")
    return "[" + ", ".join(names[index] for index in geometry.values.resolve(interface.index_dof or [])) + "]"
