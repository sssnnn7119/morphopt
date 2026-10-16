"""Pure routing from model-tree nodes to definition editor pages."""

from __future__ import annotations
from ..i18n import localized_message

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
    CUSTOM_CLASSES = auto()
    CONTROLLER = auto()
    HELPER_CODE = auto()
    HELPER_VARIABLES = auto()
    HELPER_FUNCTIONS = auto()


@dataclass(frozen=True)
class EditorRoute:
    kind: EditorKind
    node: Node | None = None
    focus: Node | None = None


def route_editor(node: Node | None) -> EditorRoute:
    """Select an editor without touching Qt or mutating the definition."""
    if node is None:
        return EditorRoute(EditorKind.PROPERTIES)
    if node.kind == "problem":
        return EditorRoute(EditorKind.CONTROLLER, node)
    if node.kind in {"custom_classes", "new_classes_group", "override_classes_group"}:
        return EditorRoute(EditorKind.CUSTOM_CLASSES, node)
    if node.kind in {"custom_class", "method_override", "custom_function"}:
        return EditorRoute(EditorKind.CUSTOM_CLASS, node)
    if node.kind in {"helper_code", "helper_code_block"}:
        return EditorRoute(EditorKind.HELPER_CODE, node)
    if node.kind in {"helper_variables_group", "helper_variable"}:
        return EditorRoute(EditorKind.HELPER_VARIABLES, focus=node)
    if node.kind in {"helper_functions_group", "helper_function"}:
        return EditorRoute(EditorKind.HELPER_FUNCTIONS, focus=node)
    if node.kind == "solver":
        return EditorRoute(EditorKind.SOLVER, node)
    if node.kind == "geometry":
        return EditorRoute(EditorKind.GEOMETRY, node)
    if node.kind in {"part", "instance", "surface", "cad_operation"}:
        return EditorRoute(EditorKind.GEOMETRY, focus=node)
    if node.kind in {"loads_group", "loads"}:
        return EditorRoute(EditorKind.LOADS, focus=None)
    if node.kind == "fea_component":
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
    """Return the items owned by a definition page, in model order."""
    from ..model.problem import (
        CADOperationNode,
        InstanceNode,
        MaterialNode,
        PartNode,
        SurfaceNode,
    )

    if problem is None:
        return []
    if mode == "geometry":
        if isinstance(focus, PartNode) and focus in problem.parts():
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
        # Load definitions belong to their collection editor. Selecting one in
        # the tree only focuses its card; it must not hide the other loads.
        return list(problem.fea_components())
    if mode == "helper_variables":
        return list(problem.helper_variables)
    if mode == "helper_functions":
        return list(problem.helper_functions)
    if mode == "materials":
        return [focus] if isinstance(focus, MaterialNode) and focus in problem.material_nodes() else []
    raise ValueError(localized_message("ui.errors.editor_routing.unknown_definition_manager_mode_value", value_0=mode))
