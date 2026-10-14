"""Load visitors turn definition values into glyph data, without drawing actors."""
from __future__ import annotations

from collections.abc import Callable
import numpy as np
import pyvista as pv
from ..model.problem import InterfaceNode
from .geometry import PreviewGeometry
from .scene import LoadScene, MeshItem, MessageItem, ArrowLoad, MomentLoad, SpringLoad, MarkerLoad

LoadHandler = Callable[[PreviewGeometry, LoadScene, InterfaceNode, list[float]], None]


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
        self._boundary_handlers: dict[str, LoadHandler] = {
            "BoundaryCondition": self.boundary_condition,
            "BoundaryConditionRP": self.boundary_condition_rp,
        }

    def register(
        self,
        interface_type: str,
        handler: LoadHandler,
        *,
        boundary: bool = False,
    ) -> None:
        (self._boundary_handlers if boundary else self._handlers)[interface_type] = handler

    def build(self, geometry: PreviewGeometry, step_index: int | None) -> LoadScene:
        scene = LoadScene(geometry.scene.diagonal)
        problem = geometry.problem
        for interface in problem.interfaces():
            self.visit(geometry, scene, interface, [], boundary=True)
        steps = problem.steps
        if steps is None or not isinstance(step_index, int) or not 0 <= step_index < len(steps.step_values):
            return scene
        interfaces = {interface.name: interface for interface in problem.interfaces()}
        for reference, raw_values in (steps.step_values[step_index] or {}).items():
            interface = reference if isinstance(reference, InterfaceNode) else interfaces.get(str(reference))
            if interface is None:
                continue
            self.visit(geometry, scene, interface, raw_values or [])
        return scene

    def visit(
        self,
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: InterfaceNode,
        raw_values: list,
        *,
        boundary: bool = False,
    ) -> None:
        handlers = self._boundary_handlers if boundary else self._handlers
        handler = handlers.get(interface.interface_type)
        if handler is None:
            return
        try:
            values = [float(geometry.values.resolve(value)) for value in raw_values]
            handler(geometry, scene, interface, values)
        except (NameError, SyntaxError, TypeError, ValueError, KeyError, OSError) as exc:
            # Preview errors describe the incomplete definition; other loads
            # still render, and the definition is never silently changed.
            scene.items.append(MessageItem(
                f"{interface.name}: {exc}",
                dict(position="upper_left", color="#e74c3c", font_size=10),
            ))

    @staticmethod
    def rp_location(
        geometry: PreviewGeometry,
        reference: InterfaceNode | None,
    ) -> np.ndarray | None:
        if reference is None:
            return None
        return np.asarray(geometry.values.resolve(reference.rp_location or [0., 0., 0.]), dtype=float)

    @staticmethod
    def pressure(
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: InterfaceNode,
        values: list[float],
    ) -> None:
        pressure = values[0] if values else 0.
        if abs(pressure) <= 1e-12:
            return
        mesh = geometry.mesh_for_surface(interface, str(interface.surface_name or ""))
        if mesh is None:
            return
        scene.items.append(MeshItem(mesh, dict(color="#1abc9c", opacity=0.42, show_edges=False)))
        surface = mesh if isinstance(mesh, pv.PolyData) else mesh.extract_surface()
        try:
            normalized = surface.compute_normals(cell_normals=True, point_normals=False, inplace=False)
            centers = normalized.cell_centers().points
            normals = np.asarray(normalized.cell_data["Normals"], dtype=float)
        except (KeyError, ValueError, AttributeError):
            return
        if not len(centers) or not len(normals):
            return
        indices = np.unique(np.linspace(0, len(centers)-1, min(3, len(centers)), dtype=int))
        for sample, index in enumerate(indices):
            scene.items.append(ArrowLoad(
                centers[index],
                normals[index] * np.sign(pressure),
                "#1abc9c",
                f"P · {interface.name} · {pressure:g}" if sample == 0 else "",
            ))

    @classmethod
    def force(
        cls,
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: InterfaceNode,
        values: list[float],
    ) -> None:
        point = cls.rp_location(geometry, interface.reference_point)
        if point is not None:
            vector = vector3(values)
            scene.items.append(ArrowLoad(
                point,
                vector,
                "#e74c3c",
                f"F · {interface.name} · {np.linalg.norm(vector):g}",
            ))

    @classmethod
    def moment(
        cls,
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: InterfaceNode,
        values: list[float],
    ) -> None:
        point = cls.rp_location(geometry, interface.reference_point)
        if point is not None:
            vector = vector3(values)
            scene.items.append(MomentLoad(point, vector, f"M · {interface.name} · {np.linalg.norm(vector):g}"))

    @staticmethod
    def bodyforce(
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: InterfaceNode,
        values: list[float],
    ) -> None:
        center = geometry.instance_center(interface.instance_name or "")
        if center is not None:
            vector = vector3(values)
            scene.items.append(ArrowLoad(
                center,
                vector,
                "#ff8c42",
                f"B · {interface.name} · {np.linalg.norm(vector):g}",
            ))

    @classmethod
    def spring_to_ground(
        cls,
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: InterfaceNode,
        values: list[float],
    ) -> None:
        point = cls.rp_location(geometry, interface.reference_point)
        if point is not None and len(values) >= 5 and abs(values[0]) > 1e-12:
            scene.items.append(SpringLoad(point, np.asarray(values[2:5]), f"{interface.name} · k={values[0]:g}"))

    @classmethod
    def spring_between(
        cls,
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: InterfaceNode,
        values: list[float],
    ) -> None:
        first = cls.rp_location(geometry, interface.reference_point1)
        second = cls.rp_location(geometry, interface.reference_point2)
        if first is not None and second is not None and values and abs(values[0]) > 1e-12:
            scene.items.append(SpringLoad(first, second, f"{interface.name} · k={values[0]:g}"))

    @staticmethod
    def penalty(
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: InterfaceNode,
        values: list[float],
    ) -> None:
        center = geometry.object_center(str(interface.obj_name or ""))
        if center is not None:
            scene.items.append(MarkerLoad(center, f"DOF {interface.s} · {interface.name}", "#ec4899"))

    @staticmethod
    def boundary_condition(
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: InterfaceNode,
        values: list[float],
    ) -> None:
        name = str(interface.set_nodes_name or "")
        mesh = geometry.mesh_for_surface(interface, name)
        if mesh is not None:
            scene.items.append(MeshItem(mesh, dict(color="#4aa3df", opacity=0.42, show_edges=False)))
            return
        center = geometry.node_set_center(interface.instance_name or "", name)
        if center is not None:
            scene.items.append(MarkerLoad(center, f"BC · {interface.name}", "#4aa3df"))

    @classmethod
    def boundary_condition_rp(
        cls,
        geometry: PreviewGeometry,
        scene: LoadScene,
        interface: InterfaceNode,
        values: list[float],
    ) -> None:
        point = cls.rp_location(geometry, interface.reference_point)
        if point is not None:
            scene.items.append(MarkerLoad(point, f"BC · {interface.name}", "#4aa3df"))


def vector3(values: list[float]) -> np.ndarray:
    vector = np.zeros(3, dtype=float)
    vector[:min(3, len(values))] = values[:3]
    return vector
