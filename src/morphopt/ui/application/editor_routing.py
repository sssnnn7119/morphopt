"""Pure routing from model-tree nodes to definition editor pages."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from ..model.problem import Node


class EditorKind(Enum):
    """Stable identifiers for pages in the definition editor stack."""

    PROPERTIES = auto()
    SOLVER = auto()
    LOADS = auto()
    STEPS = auto()
    OPTIMIZER_OVERVIEW = auto()
    UPDATER = auto()
    OBJECTIVE = auto()
    TORCHFEA_MODEL = auto()
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
    if node.kind in {"loads_group", "loads"}:
        return EditorRoute(EditorKind.LOADS, node)
    if node.kind == "steps":
        return EditorRoute(EditorKind.STEPS, node)
    if node.kind == "updater":
        return EditorRoute(EditorKind.OPTIMIZER_OVERVIEW, node)
    if node.kind.startswith("updater_"):
        return EditorRoute(EditorKind.UPDATER, node.updater_parent, node)
    if node.kind == "objective":
        return EditorRoute(EditorKind.OBJECTIVE, node)
    if (
        node.kind == "part_interface"
        and node.interface_type == "TorchFEAPartInterface"
    ):
        return EditorRoute(EditorKind.TORCHFEA_MODEL, node)
    return EditorRoute(EditorKind.PROPERTIES, node)
