"""Explicit parts node types and their editable fields."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar

from ....constants import CONSTANT
from ...i18n import localized_message
from ..base_nodes import CADOperationNode, Node, PartNode, SurfaceNode
from ..fields import FieldSpec

if TYPE_CHECKING:
    from .structural import InstanceNode


class BoundaryPartNode(PartNode):
    """UI definition of BoundaryPart."""

    surfaces: list[SurfaceNode]

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict[str, Any] | None = None,
        children: Sequence[InstanceNode | SurfaceNode] | None = None,
        **values: Any,
    ) -> None:
        self.surfaces: list[SurfaceNode] = []
        super().__init__(
            kind=kind, name=name, params=params, children=children, **values
        )

    @property
    def children(self) -> tuple[InstanceNode | SurfaceNode, ...]:
        return (*self.instances, *self.surfaces)

    def add_child(self, node: Node, index: int | None = None) -> Node:
        if not isinstance(node, SurfaceNode):
            return super().add_child(node, index)
        if index is None:
            self.surfaces.append(node)
        else:
            self.surfaces.insert(index, node)
        return node

    def remove_child(self, node: Node) -> None:
        if isinstance(node, SurfaceNode):
            self.surfaces.remove(node)
        else:
            super().remove_child(node)

    def add_surface(
        self, surface: SurfaceNode, index: int | None = None
    ) -> SurfaceNode:
        self.add_child(surface, index)
        return surface

    def surface_count(self) -> int:
        return len(self.surfaces)

    type_name: ClassVar[str] = "BoundaryPart"
    backend_class: ClassVar[str] = "BoundaryPart"
    label_key: ClassVar[str] = (
        "ui.schema.catalog.part.boundarypart.label"
    )
    is_updatable: ClassVar[bool] = True
    has_surfaces: ClassVar[bool] = True
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.PARTS.BOUNDARYPART
    fea_seed_size: float | str
    mesh_order: int | str
    exterior_surface: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "fea_seed_size",
            "ui.schema.fields.fea_seed_size.label.fea_seed_size",
            "float",
            Defaults.FEA_SEED_SIZE.DEFAULT,
            doc_key="ui.schema.fields.fea_seed_size.help.gmsh_volume_mesh_seed_size",
            minimum=Defaults.FEA_SEED_SIZE.MIN,
        ),
        FieldSpec(
            "mesh_order",
            "ui.schema.fields.mesh_order.label.mesh_order",
            "combo",
            Defaults.MESH_ORDER.DEFAULT,
            doc_key="ui.schema.fields.mesh_order.help.element_order_of_the_generated_mesh",
            choices=Defaults.MESH_ORDER.CHOICES,
            editable=False,
        ),
        FieldSpec(
            "exterior_surface",
            "ui.schema.fields.exterior_surface.label.exterior_surface",
            "str",
            Defaults.EXTERIOR_SURFACE.DEFAULT,
            doc_key="ui.schema.fields.exterior_surface.help.surface_set_used_as_the_part_exterior_surface_empty_none",
        ),
    )


class INPPartNode(PartNode):
    """UI definition of INPPart."""

    type_name: ClassVar[str] = "INPPart"
    backend_class: ClassVar[str] = "INPPart"
    label_key: ClassVar[str] = "ui.schema.catalog.part.inppart.label"
    has_surfaces: ClassVar[bool] = False
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.PARTS.INPPART
    mesh_file: str
    inp_part_name: str
    exterior_surface: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "mesh_file",
            "ui.schema.fields.mesh_file.label.inp_file",
            "file",
            Defaults.MESH_FILE.DEFAULT,
            doc_key="ui.schema.fields.mesh_file.help.abaqus_inp_mesh_file_holding_the_part",
        ),
        FieldSpec(
            "inp_part_name",
            "ui.schema.fields.inp_part_name.label.part_in_file",
            "str",
            Defaults.INP_PART_NAME.DEFAULT,
            doc_key="ui.schema.fields.inp_part_name.help.part_name_inside_the_inp_empty_selects_the_only_part",
        ),
        FieldSpec(
            "exterior_surface",
            "ui.schema.fields.exterior_surface.label.exterior_surface",
            "str",
            Defaults.EXTERIOR_SURFACE.DEFAULT,
            doc_key="ui.schema.fields.exterior_surface.help.surface_set_used_as_the_part_exterior_surface_empty_none",
        ),
    )


class BasePartNode(PartNode):
    """UI definition of BasePart."""

    type_name: ClassVar[str] = "BasePart"
    backend_class: ClassVar[str] = "BasePart"
    label_key: ClassVar[str] = (
        "ui.schema.catalog.part.basepart.label"
    )
    custom_only: ClassVar[bool] = True
    has_surfaces: ClassVar[bool] = False
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.PARTS.BASEPART
    exterior_surface: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "exterior_surface",
            "ui.schema.fields.exterior_surface.label.exterior_surface",
            "str",
            Defaults.EXTERIOR_SURFACE.DEFAULT,
            doc_key="ui.schema.fields.exterior_surface.help.surface_set_used_as_the_part_exterior_surface_empty_none",
        ),
    )


class BoxPartNode(PartNode):
    """UI definition of BoxPart."""

    type_name: ClassVar[str] = "BoxPart"
    backend_class: ClassVar[str] = "BoxPart"
    label_key: ClassVar[str] = "ui.schema.catalog.part.boxpart.label"
    has_surfaces: ClassVar[bool] = False
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.PARTS.BOXPART
    length: float | str
    height: float | str
    depth: float | str
    mesh_size: float | str
    mesh_order: int | str
    exterior_surface: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "length",
            "ui.schema.fields.length.label.text",
            "float",
            Defaults.LENGTH.DEFAULT,
            doc_key="ui.schema.fields.length.help.z",
            minimum=Defaults.LENGTH.MIN,
        ),
        FieldSpec(
            "height",
            "ui.schema.fields.height.label.text",
            "float",
            Defaults.HEIGHT.DEFAULT,
            doc_key="ui.schema.fields.height.help.text",
            minimum=Defaults.HEIGHT.MIN,
        ),
        FieldSpec(
            "depth",
            "ui.schema.fields.depth.label.text",
            "float",
            Defaults.DEPTH.DEFAULT,
            doc_key="ui.schema.fields.depth.help.text",
            minimum=Defaults.DEPTH.MIN,
        ),
        FieldSpec(
            "mesh_size",
            "ui.schema.fields.mesh_size.label.text",
            "float",
            Defaults.MESH_SIZE.DEFAULT,
            minimum=Defaults.MESH_SIZE.MIN,
        ),
        FieldSpec(
            "mesh_order",
            "ui.schema.fields.mesh_order.label.mesh_order",
            "combo",
            Defaults.MESH_ORDER.DEFAULT,
            doc_key="ui.schema.fields.mesh_order.help.text",
            choices=Defaults.MESH_ORDER.CHOICES,
            editable=False,
        ),
        FieldSpec(
            "exterior_surface",
            "ui.schema.fields.exterior_surface.label.exterior_surface",
            "str",
            Defaults.EXTERIOR_SURFACE.DEFAULT,
            doc_key="ui.schema.fields.exterior_surface.help.surface_set_used_as_the_part_exterior_surface_empty_none",
        ),
    )


class CADPartNode(PartNode):
    """UI definition of CADPart."""

    operations: list[CADOperationNode]

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict[str, Any] | None = None,
        children: Sequence[InstanceNode | CADOperationNode] | None = None,
        **values: Any,
    ) -> None:
        self.operations: list[CADOperationNode] = []
        super().__init__(
            kind=kind, name=name, params=params, children=children, **values
        )

    @property
    def children(self) -> tuple[InstanceNode | CADOperationNode, ...]:
        return (*self.instances, *self.operations)

    def add_child(self, node: Node, index: int | None = None) -> Node:
        if not isinstance(node, CADOperationNode):
            return super().add_child(node, index)
        if index is None:
            self.operations.append(node)
        else:
            self.operations.insert(index, node)
        return node

    def remove_child(self, node: Node) -> None:
        if isinstance(node, CADOperationNode):
            self.operations.remove(node)
        else:
            super().remove_child(node)

    def add_cad_operation(
        self, operation: CADOperationNode, index: int | None = None
    ) -> CADOperationNode:
        if any(item.operation_id == operation.operation_id for item in self.operations):
            raise ValueError(
                localized_message(
                    "ui.errors.nodes.cad_operation_id_value_already_exists",
                    value_0=operation.operation_id,
                )
            )
        self.add_child(operation, index)
        return operation

    def live_cad_operations(
        self, operations: list[CADOperationNode] | None = None
    ) -> list[CADOperationNode]:
        history = self.operations if operations is None else operations
        consumed = {
            input_id
            for operation in history
            for input_id in (operation.object_id, operation.tool_id, operation.input_id)
            if input_id
        }
        return [
            operation for operation in history if operation.operation_id not in consumed
        ]

    type_name: ClassVar[str] = "CADPart"
    backend_class: ClassVar[str] = "CADPart"
    label_key: ClassVar[str] = "ui.schema.catalog.part.cadpart.label"
    has_surfaces: ClassVar[bool] = False
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.PARTS.CADPART
    mesh_size: float | str
    mesh_order: int | str
    exterior_surface: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "mesh_size",
            "ui.schema.fields.mesh_size.label.text",
            "float",
            Defaults.MESH_SIZE.DEFAULT,
            minimum=Defaults.MESH_SIZE.MIN,
        ),
        FieldSpec(
            "mesh_order",
            "ui.schema.fields.mesh_order.label.mesh_order",
            "combo",
            Defaults.MESH_ORDER.DEFAULT,
            doc_key="ui.schema.fields.mesh_order.help.text",
            choices=Defaults.MESH_ORDER.CHOICES,
            editable=False,
        ),
        FieldSpec(
            "exterior_surface",
            "ui.schema.fields.exterior_surface.label.exterior_surface",
            "str",
            Defaults.EXTERIOR_SURFACE.DEFAULT,
            doc_key="ui.schema.fields.exterior_surface.help.surface_set_used_as_the_part_exterior_surface_empty_none",
        ),
    )


class OffsetBoundaryPartNode(BoundaryPartNode):
    """UI definition of OffsetBoundaryPart."""

    type_name: ClassVar[str] = "OffsetBoundaryPart"
    backend_class: ClassVar[str] = "OffsetBoundaryPart"
    label_key: ClassVar[str] = (
        "ui.schema.catalog.part.offsetboundarypart.label"
    )
    is_updatable: ClassVar[bool] = True
    has_surfaces: ClassVar[bool] = True
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.PARTS.OFFSETBOUNDARYPART
    shell_thickness: float | str
    num_layers: int | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        *BoundaryPartNode.fields,
        FieldSpec(
            "shell_thickness",
            "ui.schema.fields.shell_thickness.label.offset_thickness",
            "float",
            Defaults.SHELL_THICKNESS.DEFAULT,
            minimum=Defaults.SHELL_THICKNESS.MIN,
        ),
        FieldSpec(
            "num_layers",
            "ui.schema.fields.num_layers.label.offset_layers",
            "int",
            Defaults.NUM_LAYERS.DEFAULT,
            minimum=Defaults.NUM_LAYERS.MIN,
        ),
    )
