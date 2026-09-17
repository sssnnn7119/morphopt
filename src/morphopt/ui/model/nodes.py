"""Nodes used by the model-tree presentation layer."""

from typing import Generic, TypeVar


NodeValue = TypeVar("NodeValue")


class ModelNode(Generic[NodeValue]):
    """Named tree node carrying its corresponding domain value."""

    def __init__(self, name: str, value: NodeValue | None = None) -> None:
        self.name = name
        """Display name shown in the tree."""
        self.value = value
        """Domain object or configuration represented by the node."""
