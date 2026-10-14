"""Transient navigation handles; they are never serialized in a definition."""
from __future__ import annotations
from dataclasses import dataclass, field
from ..model.problem import Node, ProblemDefinition
from ..i18n import tr
from .labels import (
    container_title,
    surface_title_text,
    part_interface_title_text,
    instance_title_text,
    cad_operation_title_text,
    interface_title_text,
    material_title_text,
    updater_title_text,
    display_node_title,
)

class ParamsTreeNode(Node):
    """Navigation parent for the persisted geometry, loads and materials."""

    def __init__(self) -> None:
        super().__init__(kind="params_class", name="Params")


class HelperCodeTreeNode(Node):
    """Navigation entry for module-level code stored on the problem."""

    def __init__(self) -> None:
        super().__init__(kind="helper_code", name="Helper code")


class HelperGroupTreeNode(Node):
    """Navigation group under Helper code."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind=kind, name=container_title(kind))


class HelperCodeBlockTreeNode(Node):
    """Navigation entry for the one free-form module code block."""

    def __init__(self) -> None:
        super().__init__(kind="helper_code_block", name=container_title("helper_code_block"))


class LoadsTreeNode(Node):
    """Transient parent for load definitions and load-step cases."""

    def __init__(self) -> None:
        super().__init__(kind="loads_group", name=tr('ui.widgets.model_tree.loads'))


class UpdaterTreeNode(Node):
    """Transient tree entry for an updater section or one of its groups.

    Updater configuration remains owned by :class:`UpdaterNode`; these nodes
    are navigation handles only and are intentionally not inserted into the
    persisted problem tree.  Both sections carry ``config_index``: the model may
    run several sub-optimizers side by side, one per target (a boundary part
    interface for geometry, a material interface for materials).
    """

    def __init__(self, updater: Node, group: str, config_index: int = 0) -> None:
        label = {
            "geometry": tr('ui.widgets.model_tree.geometry_optimizer'),
            "materials": tr('ui.widgets.model_tree.material_optimizer'),
            "geometry_objectives": tr('ui.widgets.model_tree.sub_optimizer_objectives'),
            "geometry_symmetry": tr('ui.widgets.model_tree.geometry_symmetry_constraints'),
            "geometry_penalty": tr('ui.widgets.model_tree.geometry_penalty_constraints'),
            "materials_objectives": tr('ui.widgets.model_tree.sub_optimizer_objectives'),
            "materials_penalty": tr('ui.widgets.model_tree.material_penalty_constraints'),
        }.get(group, group)
        super().__init__(kind=f"updater_{group}", name=label)
        self.updater_parent = updater
        self.group = group
        self.config_index = int(config_index)
        self.code_reference = (
            "UpdaterBoundaryPart" if group.startswith("geometry") else "UpdaterSIMPMaterial"
        )

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


def node_key(node: Node | None):
    """Stable identity for transient Params/updater entries across rebuilds."""
    if node is None:
        return None
    if node.kind == "params_class":
        return ("params_class",)
    if node.kind in {"helper_code", "helper_code_block", "helper_variables_group", "helper_functions_group"}:
        return (node.kind,)
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
            display_node_title(self.problem, title or self.title(node), node),
            bold,
            list(children),
        )

    def title(self, node: Node) -> str:
        if node.kind == "part_interface":
            return part_interface_title_text(node)
        if node.kind == "instance":
            return instance_title_text(node)
        if node.kind == "cad_operation":
            return cad_operation_title_text(node)
        if node.kind == "interface":
            return interface_title_text(node)
        if node.kind == "material":
            return material_title_text(node)
        if node.kind.startswith("updater_"):
            return updater_title_text(self.problem, node)
        if node.kind in {"helper_variable", "helper_function"}:
            return node.name
        if node.kind == "surface":
            owner = self.problem.owner_of_surface(node)
            return surface_title_text(node, owner.surfaces().index(node))
        return container_title(node.kind)

    def build(self) -> list[NavigationEntry]:
        problem = self.problem
        helpers = self.entry(HelperCodeTreeNode(), bold=True, children=[self.entry(HelperCodeBlockTreeNode())])
        for kind, nodes in (("helper_variables_group", problem.helper_variables), ("helper_functions_group", problem.helper_functions)):
            helpers.children.append(self.entry(
                HelperGroupTreeNode(kind),
                bold=True,
                children=[self.entry(node) for node in nodes],
            ))
        params = self.entry(ParamsTreeNode(), bold=True)
        controller = self.entry(problem.root, bold=True, children=[params])
        if problem.geometry is not None:
            geometry = self.entry(problem.geometry, bold=True)
            params.children.append(geometry)
            for part in problem.part_interfaces():
                children = [self.entry(node) for node in part.instances()]
                children.extend(self.entry(node) for node in part.cad_operations())
                children.extend(self.entry(
                    node,
                    surface_title_text(node, index),
                ) for index, node in enumerate(part.surfaces()))
                geometry.children.append(self.entry(part, children=children))
        loads = self.entry(LoadsTreeNode(), bold=True)
        params.children.append(loads)
        if problem.loads is not None:
            loads.children.append(self.entry(
                problem.loads,
                bold=True,
                children=[self.entry(node) for node in problem.interfaces()],
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
                    children = [self.entry(UpdaterTreeNode(problem.updater, group, index)) for group in groups]
                    updater.children.append(self.entry(
                        UpdaterTreeNode(problem.updater, kind, index),
                        bold=True,
                        children=children,
                    ))
        return [helpers, controller]
