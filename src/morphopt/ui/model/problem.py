"""Generic node-tree data model for an optimization problem definition."""

from __future__ import annotations

from typing import Any, Iterable, Iterator, Optional


class Node:
    """A node in the problem-definition tree.

    Parameters
    ----------
    kind:
        Machine-readable node type, e.g. ``"surface"``, ``"interface"``,
        ``"material"``.  Every kind maps to a field schema in
        :mod:`morphopt.ui.model.schemas`.
    name:
        Display / reference name.  For load interfaces this is the name used
        in the load-step matrix and in generated FEA code (e.g. ``pressure_1``).
    params:
        Dictionary of field values.  Keys must match the constructor
        arguments of the backend class that ``kind`` stands for.
    children:
        Ordered child nodes (e.g. surfaces inside ``geometry``).
    """

    def __init__(self, kind: str, name: str = "", params: Optional[dict] = None,
                 children: Optional[list["Node"]] = None) -> None:
        self.kind = kind
        self.name = name
        self.params: dict[str, Any] = dict(params or {})
        self.children: list[Node] = list(children or [])

    # ------------------------------------------------------------------ tree
    def add_child(self, node: "Node", index: Optional[int] = None) -> "Node":
        if index is None:
            self.children.append(node)
        else:
            self.children.insert(index, node)
        return node

    def remove_child(self, node: "Node") -> None:
        self.children.remove(node)

    def child(self, kind: str) -> Optional["Node"]:
        return next((c for c in self.children if c.kind == kind), None)

    def children_of(self, kind: str) -> list["Node"]:
        return [c for c in self.children if c.kind == kind]

    def iter_nodes(self) -> Iterator["Node"]:
        yield self
        for child in self.children:
            yield from child.iter_nodes()

    def find(self, predicate) -> Optional["Node"]:
        """Depth-first search for the first node satisfying ``predicate``."""
        for node in self.iter_nodes():
            if predicate(node):
                return node
        return None

    # ----------------------------------------------------------- persistence
    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "name": self.name,
            "params": self.params,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Node":
        return cls(
            kind=data.get("kind", ""),
            name=data.get("name", ""),
            params=dict(data.get("params", {}) or {}),
            children=[cls.from_dict(c) for c in data.get("children", [])],
        )

    # ---------------------------------------------------------------- misc
    def clone(self) -> "Node":
        return Node.from_dict(self.to_dict())

    def __repr__(self) -> str:
        return f"<Node {self.kind!r} name={self.name!r} params={list(self.params)} children={len(self.children)}>"


class ProblemDefinition:
    """Top-level description of one optimization problem.

    Attributes mirror the handful of top-level arguments a generated
    ``ThisController`` needs plus the whole editable parameter tree.
    """

    SCHEMES = ("simp", "shapeopt", "codesign")

    def __init__(
        self,
        scheme: str = "shapeopt",
        label: str = "Untitled",
        result_folder: str = ".results/",
        device: str = "cpu",
        restart_per_iteration: int = 10,
        root: Optional[Node] = None,
    ) -> None:
        if scheme not in self.SCHEMES:
            raise ValueError(f"Unknown scheme {scheme!r}; expected one of {self.SCHEMES}")
        self.scheme = scheme
        self.label = label
        self.result_folder = result_folder
        self.device = device
        self.restart_per_iteration = restart_per_iteration
        self.root = root if root is not None else Node("problem", name=label)

    # ------------------------------------------------------------ accessors
    def node(self, kind: str) -> Optional[Node]:
        return self.root.find(lambda n: n.kind == kind)

    def nodes(self, kind: str) -> list[Node]:
        return [n for n in self.root.iter_nodes() if n.kind == kind]

    def surfaces(self) -> list[Node]:
        return [n for n in self.root.iter_nodes() if n.kind == "surface"]

    def interfaces(self) -> list[Node]:
        return [n for n in self.root.iter_nodes() if n.kind == "interface"]

    # ----------------------------------------------------------- persistence
    def to_dict(self) -> dict:
        return {
            "version": 1,
            "scheme": self.scheme,
            "label": self.label,
            "result_folder": self.result_folder,
            "device": self.device,
            "restart_per_iteration": self.restart_per_iteration,
            "root": self.root.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProblemDefinition":
        return cls(
            scheme=data.get("scheme", "shapeopt"),
            label=data.get("label", "Untitled"),
            result_folder=data.get("result_folder", ".results/"),
            device=data.get("device", "cpu"),
            restart_per_iteration=data.get("restart_per_iteration", 10),
            root=Node.from_dict(data.get("root", {"kind": "problem"})),
        )


def find_node(root: Node, kind: str, name: Optional[str] = None) -> Optional[Node]:
    """Find a node by kind (and optionally name)."""
    return root.find(lambda n: n.kind == kind and (name is None or n.name == name))


def list_node_paths(root: Node) -> list[str]:
    """Return human-readable paths of every node (for debugging / display)."""
    out: list[str] = []

    def walk(node: Node, prefix: str) -> None:
        label = node.name or node.kind
        path = f"{prefix}/{label}" if prefix else label
        out.append(path)
        for c in node.children:
            walk(c, path)

    walk(root, "")
    return out
