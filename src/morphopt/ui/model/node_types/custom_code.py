"""Concrete nodes for user-authored helper and class code."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..base_nodes import Node


class MethodOverrideNode(Node):
    """Body of one overridden method; its signature comes from the base class."""

    kind = "method_override"
    _FIELDS = ("body",)

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict[str, Any] | None = None,
        children: Sequence[Node] | None = None,
    ) -> None:
        super().__init__(kind=kind, name=name, children=children)
        self.body: str = str((params or {}).get("body", ""))


class CustomClassNode(Node):
    """A module-level user class or framework subclass."""

    members: list[MethodOverrideNode | CustomFunctionNode]

    kind = "custom_class"
    _FIELDS = ("base_class", "class_type")

    @property
    def children(self) -> tuple[MethodOverrideNode | CustomFunctionNode, ...]:
        return tuple(self.members)

    def add_child(self, node: Node, index: int | None = None) -> Node:
        if not isinstance(node, MethodOverrideNode | CustomFunctionNode):
            return super().add_child(node, index)
        if index is None:
            self.members.append(node)
        else:
            self.members.insert(index, node)
        return node

    def remove_child(self, node: Node) -> None:
        if not isinstance(node, MethodOverrideNode | CustomFunctionNode):
            return super().remove_child(node)
        self.members.remove(node)

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict[str, Any] | None = None,
        children: Sequence[Node] | None = None,
    ) -> None:
        self.members: list[MethodOverrideNode | CustomFunctionNode] = []
        super().__init__(kind=kind, name=name, children=children)
        self.base_class: str = str((params or {}).get("base_class", ""))
        self.class_type: str = str((params or {}).get("class_type", "override"))


class CustomFunctionNode(Node):
    """A user-defined function inside a newly created class."""

    kind = "custom_function"
    _FIELDS = ("parameters", "body")

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict[str, Any] | None = None,
        children: Sequence[Node] | None = None,
    ) -> None:
        super().__init__(kind=kind, name=name, children=children)
        self.parameters: str = str((params or {}).get("parameters", "self"))
        self.body: str = str((params or {}).get("body", "pass"))


class HelperVariableNode(Node):
    """One named module-level value expression."""

    kind = "helper_variable"
    _FIELDS = ("value",)

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict[str, Any] | None = None,
        children: Sequence[Node] | None = None,
    ) -> None:
        super().__init__(kind=kind, name=name, children=children)
        self.value: str = str((params or {}).get("value", "None"))


class HelperFunctionNode(Node):
    """One named module-level function with explicit parameters and body."""

    kind = "helper_function"
    _FIELDS = ("parameters", "body")

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict[str, Any] | None = None,
        children: Sequence[Node] | None = None,
    ) -> None:
        super().__init__(kind=kind, name=name, children=children)
        self.parameters: str = str((params or {}).get("parameters", ""))
        self.body: str = str((params or {}).get("body", "pass"))
