"""Transient navigation handles; they are never serialized in a definition."""
from __future__ import annotations

from ..model.node_types.parts import BoundaryPartNode, CADPartNode
from dataclasses import dataclass, field
from ..model.problem import Node, ProblemDefinition, UpdaterNode
from ..i18n import tr
from .labels import container_title, node_title, updater_group_title


class ParamsTreeNode(Node):
    """Navigation parent for the persisted geometry, loads and materials."""

    def __init__(self) -> None:
        super().__init__(kind="params_class", name="Params")


class CustomClassesTreeNode(Node):
    """Root-level collection of reusable custom classes."""

    def __init__(self) -> None:
        super().__init__(kind="custom_classes", name=container_title("custom_classes"))


class CustomClassGroupTreeNode(Node):
    """Transient collection for new classes or framework overrides."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind=kind, name=container_title(kind))


class HelperGroupTreeNode(Node):
    """Navigation group for helper variables or functions."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind=kind, name=container_title(kind))


class HelperCodeBlockTreeNode(Node):
    """Navigation entry for the one free-form module code block."""

    def __init__(self) -> None:
        super().__init__(kind="helper_code_block", name=container_title("helper_code_block"))


class HelperCodeTreeNode(Node):
    """Root collection for free code, helper variables and functions."""

    def __init__(self) -> None:
        super().__init__(kind="helper_code", name=container_title("helper_code"))


class LoadsTreeNode(Node):
    """Transient parent for load definitions and load-step cases."""

    def __init__(self) -> None:
        super().__init__(kind="loads_group", name=tr('ui.widgets.model_tree.loads'))


class UpdaterTreeNode(Node):
    """Transient tree entry for an updater section or one of its groups.

    Updater configuration remains owned by :class:`UpdaterNode`; these nodes
    are navigation handles only and are intentionally not inserted into the
    persisted problem tree.  Both sections carry ``config_index``: the model may
    run several sub-optimizers side by side, one per target (a boundary Part
    for geometry, a design material for materials).
    """

    def __init__(self, updater: UpdaterNode, group: str, config_index: int = 0) -> None:
        label = updater_group_title(group)
        configs = (
            updater.geometry if group.startswith("geometry") else updater.materials
        )
        config = configs[config_index] if 0 <= config_index < len(configs) else None
        target = config.get("target") if config is not None else None
        target_name = getattr(target, "name", "") if target is not None else ""
        if config is not None and not target_name:
            target_name = config.get("part_name") or config.get("material_name") or ""
        super().__init__(kind=f"updater_{group}", name=str(target_name or label))
        self.updater_parent = updater
        self.group = group
        self.config_index = int(config_index)

    @property
    def section_group(self) -> str:
        """Canonical updater section owning this navigation entry."""
        return "geometry" if self.group.startswith("geometry") else "materials"

    def config(self) -> dict | None:
        """Config dict this entry points at."""
        configs = (
            self.updater_parent.geometry
            if self.section_group == "geometry"
            else self.updater_parent.materials
        )
        return configs[self.config_index] if self.config_index < len(configs) else None


class UpdaterItemTreeNode(UpdaterTreeNode):
    """Navigation handle for one ordered item, backed by its config dictionary."""

    def __init__(
        self, updater: UpdaterNode, group: str, config_index: int, item: dict
    ) -> None:
        super().__init__(updater, group, config_index)
        self.kind = "updater_item"
        self.item = item
        self.name = str(item.get("custom_class") or item.get("type") or self.name)

    @property
    def category(self) -> str:
        if self.group.endswith("objectives"):
            return "objectives"
        if self.group.endswith("symmetry"):
            return "geometry_symmetry"
        return "constraints"


def node_key(node: Node | None):
    """Stable identity for transient Params/updater entries across rebuilds."""
    if node is None:
        return None
    if node.kind == "params_class":
        return ("params_class",)
    if node.kind in {
        "loads_group", "helper_code", "helper_code_block",
        "helper_variables_group", "helper_functions_group", "custom_classes",
        "new_classes_group", "override_classes_group",
    }:
        return (node.kind,)
    if isinstance(node, UpdaterItemTreeNode):
        return ("updater_item", id(node.updater_parent), node.group, node.config_index, id(node.item))
    if isinstance(node, UpdaterTreeNode):
        return (
            "updater",
            id(node.updater_parent),
            node.group,
            node.config_index,
        )
    return ("node", id(node))

@dataclass
class NavigationEntry:
    node: Node
    title: str
    bold: bool = False
    children: list[NavigationEntry] = field(default_factory=list)


class DefinitionNavigation:
    """Build the tree projection without creating widgets or changing data."""
    def __init__(self, problem: ProblemDefinition):
        self.problem = problem

    def entry(
        self,
        node: Node,
        title: str | None = None,
        *,
        bold: bool = False,
        children=(),
    ) -> NavigationEntry:
        return NavigationEntry(
            node,
            title or self.title(node),
            bold,
            list(children),
        )

    def title(self, node: Node) -> str:
        return node_title(self.problem, node)

    def build(self) -> list[NavigationEntry]:
        problem = self.problem
        free_code = self.entry(HelperCodeBlockTreeNode(), bold=True)
        helper_groups = [
            self.entry(
                HelperGroupTreeNode(kind),
                bold=True,
                children=[self.entry(node) for node in nodes],
            )
            for kind, nodes in (
                ("helper_variables_group", problem.helper_variables),
                ("helper_functions_group", problem.helper_functions),
            )
        ]
        helper_code = self.entry(
            HelperCodeTreeNode(), bold=True, children=[free_code, *helper_groups]
        )
        params = self.entry(ParamsTreeNode(), bold=True)
        controller = self.entry(problem.root, bold=True, children=[params])
        if problem.geometry is not None:
            geometry = self.entry(problem.geometry, bold=True)
            params.children.append(geometry)
            for part in problem.parts():
                children = [self.entry(node) for node in part.instances]
                if isinstance(part, CADPartNode):
                    children.extend(self.entry(node) for node in part.operations)
                if isinstance(part, BoundaryPartNode):
                    children.extend(self.entry(node) for node in part.surfaces)
                geometry.children.append(self.entry(part, children=children))
        loads = self.entry(LoadsTreeNode(), bold=True)
        params.children.append(loads)
        if problem.loads is not None:
            loads.children.append(self.entry(
                problem.loads,
                bold=True,
                children=[self.entry(node) for node in problem.fea_components()],
            ))
        if problem.steps is not None:
            loads.children.append(self.entry(problem.steps, bold=True))
        if problem.materials is not None:
            params.children.append(self.entry(
                problem.materials,
                bold=True,
                children=[self.entry(node) for node in problem.material_nodes()],
            ))
        if problem.solver is not None:
            controller.children.append(self.entry(problem.solver, bold=True))
        if problem.updater is not None:
            updater = self.entry(problem.updater, bold=True)
            controller.children.append(updater)
            if problem.objective is not None:
                updater.children.append(self.entry(problem.objective, bold=True))
            for kind, configs, groups in (
                ("geometry", problem.updater.geometry, ("geometry_objectives", "geometry_symmetry", "geometry_penalty")),
                ("materials", problem.updater.materials, ("materials_objectives", "materials_penalty")),
            ):
                for index in range(len(configs)):
                    children = []
                    for group in groups:
                        key = (
                            "objective_functions" if group.endswith("objectives")
                            else "symmetry_constraints" if group.endswith("symmetry")
                            else "constraints"
                        )
                        children.append(self.entry(
                            UpdaterTreeNode(problem.updater, group, index),
                            children=[
                                self.entry(UpdaterItemTreeNode(problem.updater, group, index, item))
                                for item in configs[index].get(key, [])
                            ],
                        ))
                    updater.children.append(self.entry(
                        UpdaterTreeNode(problem.updater, kind, index),
                        bold=True,
                        children=children,
                    ))
        custom_classes = self.entry(CustomClassesTreeNode(), bold=True, children=[])
        for kind, class_type in (("new_classes_group", "new"), ("override_classes_group", "override")):
            custom_classes.children.append(self.entry(
                CustomClassGroupTreeNode(kind),
                bold=True,
                children=[
                    self.entry(custom, children=[self.entry(method) for method in custom.members])
                    for custom in problem.custom_classes
                    if custom.class_type == class_type
                ],
            ))
        helper_code.children.append(custom_classes)
        return [helper_code, controller]


def node_path(problem: ProblemDefinition, node: Node | None) -> tuple[int, ...] | None:
    """Locate a persisted or virtual node without retaining Python identities.

    Paths are relative to one document snapshot, including helper and updater
    groups. They are UI bookmarks, not part of the .morph file format.
    """
    key = node_key(node)
    if key is None:
        return None

    def visit(entries: list[NavigationEntry], prefix: tuple[int, ...]) -> tuple[int, ...] | None:
        for index, entry in enumerate(entries):
            path = (*prefix, index)
            if node_key(entry.node) == key:
                return path
            found = visit(entry.children, path)
            if found is not None:
                return found
        return None

    return visit(DefinitionNavigation(problem).build(), ())


def node_at_path(problem: ProblemDefinition, path: tuple[int, ...] | None) -> Node | None:
    """Resolve a snapshot bookmark, retaining its parent if a child is absent."""
    entries = DefinitionNavigation(problem).build()
    node = None
    for index in path or ():
        if not 0 <= index < len(entries):
            break
        entry = entries[index]
        node, entries = entry.node, entry.children
    return node
