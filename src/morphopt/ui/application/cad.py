"""Build CAD Part previews and exports from ordered UI operation nodes."""

from __future__ import annotations

from pathlib import Path

import torchfea

from ...constants import CONSTANT
from ...optcore.modelparams.parts import CADPart
from ..model.problem import CADOperationNode, PartNode, ProblemDefinition
from ..model.registry import (
    CAD_OPERATION_TYPES,
)
from .expressions import DefinitionValues
from ..model.node_types.parts import CADPartNode
from ..model.node_types.cad import StepImportOperationNode


def cad_operation_from_node(
    operation: CADOperationNode,
    namespace: dict[str, object] | None = None,
) -> torchfea.cad.CADOperation:
    """Create the corresponding TorchFEA CAD object for one UI operation."""
    operation_type = operation.operation_type
    spec = CAD_OPERATION_TYPES[operation_type]

    if isinstance(operation, StepImportOperationNode):
        return torchfea.cad.StepImport(
            operation.operation_id,
            filename=operation.filename or "import.step",
            data=operation.data or "",
        )

    operation_class = getattr(torchfea.cad, operation_type)
    kwargs: dict[str, object] = {"id": operation.operation_id}
    for field in spec.fields:
        key = field.key
        value = operation.get_field(key)
        if (
            field.type == "float"
            and isinstance(value, str)
            and namespace is not None
        ):
            value = eval(compile(value, "<CAD parameter>", "eval"), namespace)
        if value is not None:
            kwargs[key] = value
    return operation_class(**kwargs)


def cad_part_from_node(
    node: CADPartNode, problem: ProblemDefinition | None = None
) -> CADPart:
    """Create a preview Part from its structured, ordered CAD feature list."""
    operations = node.operations
    values = DefinitionValues(problem)
    namespace = values.namespace

    class PreviewCADPart(CADPart):
        def define_operations(self) -> None:
            for operation_node in operations:
                self.add_operation(
                    cad_operation_from_node(operation_node, namespace)
                )

    part = PreviewCADPart(
        mesh_size=(
            values.resolve(node.mesh_size)
            if node.mesh_size is not None
            else CONSTANT.UI.SCHEMA_FIELDS.PARTS.CADPART.MESH_SIZE.DEFAULT
        ),
        mesh_order=values.resolve(node.mesh_order) if node.mesh_order is not None else 1,
        exterior_surface=node.exterior_surface or "extern",
        part_name=node.assembly_name or "CADPreview",
    )
    part.initialize()
    return part


def cad_brep_records_from_node(
    node: CADPartNode, problem: ProblemDefinition | None = None
) -> list[dict]:
    """Return OCC face and edge geometry for the CAD viewport."""
    part = cad_part_from_node(node, problem)
    if not part.operations:
        return []
    return torchfea.cad.preview_brep(part.operations)


def export_cad_step(
    node: CADPartNode, path: str | Path, problem: ProblemDefinition | None = None
) -> None:
    """Export the Part's final CAD solids in local coordinates without meshing."""
    namespace = DefinitionValues(problem).namespace
    operations = [cad_operation_from_node(item, namespace) for item in node.operations]
    torchfea.cad.export_step(operations, str(path))
