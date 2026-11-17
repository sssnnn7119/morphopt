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
        """Initialize MethodOverrideNode and its configuration state.

        Args:
            kind (str | None): Registered category or provider identifier used to dispatch the
                operation.
            name (str): Name identifying the item in its owning collection.
            params (dict[str, Any] | None): Editable parameter fields of this definition node or
                interface configuration.
            children (Sequence[Node] | None): Child definition nodes in registration order.
        """
        super().__init__(kind=kind, name=name, children=children)
        self.body: str = str((params or {}).get("body", ""))


class CustomClassNode(Node):
    """A module-level user class or framework subclass."""

    members: list[MethodOverrideNode | CustomFunctionNode]

    kind = "custom_class"
    _FIELDS = ("base_class", "class_type")

    @property
    def children(self) -> tuple[MethodOverrideNode | CustomFunctionNode, ...]:
        """Return children.

        Returns:
            tuple[MethodOverrideNode | CustomFunctionNode, ...]: Children.
        """
        return tuple(self.members)

    def add_child(self, node: Node, index: int | None = None) -> Node:
        """Add child.

        Args:
            node (Node): Definition node being inspected or edited.
            index (int | None): Zero-based position within the relevant collection.

        Returns:
            Node: Add child.
        """
        if not isinstance(node, MethodOverrideNode | CustomFunctionNode):
            return super().add_child(node, index)
        if index is None:
            self.members.append(node)
        else:
            self.members.insert(index, node)
        return node

    def remove_child(self, node: Node) -> None:
        """Remove child.

        Args:
            node (Node): Definition node being inspected or edited.
        """
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
        """Initialize CustomClassNode and its configuration state.

        Args:
            kind (str | None): Registered category or provider identifier used to dispatch the
                operation.
            name (str): Name identifying the item in its owning collection.
            params (dict[str, Any] | None): Editable parameter fields of this definition node or
                interface configuration.
            children (Sequence[Node] | None): Child definition nodes in registration order.
        """
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
        """Initialize CustomFunctionNode and its configuration state.

        Args:
            kind (str | None): Registered category or provider identifier used to dispatch the
                operation.
            name (str): Name identifying the item in its owning collection.
            params (dict[str, Any] | None): Editable parameter fields of this definition node or
                interface configuration.
            children (Sequence[Node] | None): Child definition nodes in registration order.
        """
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
        """Initialize HelperVariableNode and its configuration state.

        Args:
            kind (str | None): Registered category or provider identifier used to dispatch the
                operation.
            name (str): Name identifying the item in its owning collection.
            params (dict[str, Any] | None): Editable parameter fields of this definition node or
                interface configuration.
            children (Sequence[Node] | None): Child definition nodes in registration order.
        """
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
        """Initialize HelperFunctionNode and its configuration state.

        Args:
            kind (str | None): Registered category or provider identifier used to dispatch the
                operation.
            name (str): Name identifying the item in its owning collection.
            params (dict[str, Any] | None): Editable parameter fields of this definition node or
                interface configuration.
            children (Sequence[Node] | None): Child definition nodes in registration order.
        """
        super().__init__(kind=kind, name=name, children=children)
        self.parameters: str = str((params or {}).get("parameters", ""))
        self.body: str = str((params or {}).get("body", "pass"))
