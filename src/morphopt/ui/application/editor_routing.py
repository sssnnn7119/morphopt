"""Pure routing from model-tree nodes to definition editor pages."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from ..model.problem import Node, ProblemDefinition


class EditorKind(Enum):
    """Stable identifiers for pages in the definition editor stack."""

    PROPERTIES = auto()
    SOLVER = auto()
    GEOMETRY = auto()
    LOADS = auto()
    MATERIALS = auto()
    STEPS = auto()
    OPTIMIZER_OVERVIEW = auto()
    UPDATER = auto()
    OBJECTIVE = auto()
    CUSTOM_CLASS = auto()
    HELPER_CODE = auto()


@dataclass(frozen=True)
class EditorRoute:
    kind: EditorKind
    node: Node | None = None
    focus: Node | None = None


def route_editor(node: Node | None) -> EditorRoute:
    """Select an editor without touching Qt or mutating the definition."""
    if node is None:
        return EditorRoute(EditorKind.PROPERTIES)
    if node.kind in {"custom_class", "method_override"}:
        return EditorRoute(EditorKind.CUSTOM_CLASS, node)
    if node.kind in {
        "helper_code", "helper_code_block", "helper_variables_group", "helper_functions_group",
        "helper_variable", "helper_function",
    }:
        return EditorRoute(EditorKind.HELPER_CODE, node)
    if node.kind == "solver":
        return EditorRoute(EditorKind.SOLVER, node)
    if node.kind == "geometry":
        return EditorRoute(EditorKind.GEOMETRY, node)
    if node.kind in {"part_interface", "instance", "surface", "cad_operation"}:
        return EditorRoute(EditorKind.GEOMETRY, focus=node)
    if node.kind in {"loads_group", "loads"}:
        return EditorRoute(EditorKind.LOADS, focus=None)
    if node.kind == "interface":
        return EditorRoute(EditorKind.LOADS, focus=node)
    if node.kind == "materials":
        return EditorRoute(EditorKind.MATERIALS)
    if node.kind == "material":
        return EditorRoute(EditorKind.MATERIALS, focus=node)
    if node.kind == "steps":
        return EditorRoute(EditorKind.STEPS, node)
    if node.kind == "updater":
        return EditorRoute(EditorKind.OPTIMIZER_OVERVIEW, node)
    if node.kind.startswith("updater_"):
        return EditorRoute(EditorKind.UPDATER, node.updater_parent, node)
    if node.kind == "objective":
        return EditorRoute(EditorKind.OBJECTIVE, node)
    return EditorRoute(EditorKind.PROPERTIES, node)


def managed_nodes(problem: ProblemDefinition | None, mode: str, focus: Node | None) -> list[Node]:
    """Scope a definition page to one selected interface and its owned children."""
    from ..model.problem import CADOperationNode, InstanceNode, InterfaceNode, MaterialNode, PartInterfaceNode, SurfaceNode

    if problem is None:
        return []
    if mode == "geometry":
        if isinstance(focus, PartInterfaceNode) and focus in problem.part_interfaces():
            return [focus]
        owner = None
        if isinstance(focus, InstanceNode):
            owner = problem.owner_of_instance(focus)
        elif isinstance(focus, SurfaceNode):
            owner = problem.owner_of_surface(focus)
        elif isinstance(focus, CADOperationNode):
            owner = problem.owner_of_cad_operation(focus)
        return [owner] if owner is not None else []
    if mode == "loads":
        return [focus] if isinstance(focus, InterfaceNode) and focus in problem.interfaces() else []
    if mode == "materials":
        return [focus] if isinstance(focus, MaterialNode) and focus in problem.material_nodes() else []
    raise ValueError(f"Unknown definition manager mode: {mode}")
