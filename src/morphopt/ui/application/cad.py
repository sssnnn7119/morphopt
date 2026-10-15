"""Build CAD Part previews from the UI's ordered operation nodes."""

from __future__ import annotations

import torchfea

from ...optcore.modelparams.parts import CADPart
from ..model.problem import CADOperationNode, PartNode, ProblemDefinition
from ..model.schemas import CAD_OPERATION_TYPES
from .expressions import DefinitionValues


def cad_operation_from_node(
    operation: CADOperationNode,
    namespace: dict[str, object] | None = None,
) -> torchfea.cad.CADOperation:
    """Create the corresponding TorchFEA CAD object for one UI operation."""
    operation_type = operation.operation_type
    spec = CAD_OPERATION_TYPES[operation_type]

    if operation_type == "StepImport":
        return torchfea.cad.StepImport(
            operation.operation_id,
            filename=operation.filename or "import.step",
            data=operation.data or "",
        )

    operation_class = getattr(torchfea.cad, operation_type)
    kwargs: dict[str, object] = {"id": operation.operation_id}
    for field in spec["params"]:
        key = field["key"]
        value = operation.get_field(key)
        if (
            field["type"] == "float"
            and isinstance(value, str)
            and namespace is not None
        ):
            value = eval(compile(value, "<CAD parameter>", "eval"), namespace)
        if value is not None:
            kwargs[key] = value
    return operation_class(**kwargs)


def cad_part_from_node(
    node: PartNode, problem: ProblemDefinition | None = None
) -> CADPart:
    """Create a preview Part from its structured, ordered CAD feature list."""
    operations = node.cad_operations()
    values = DefinitionValues(problem)
    namespace = values.namespace

    class PreviewCADPart(CADPart):
        def define_operations(self) -> None:
            for operation_node in operations:
                self.add_operation(
                    cad_operation_from_node(operation_node, namespace)
                )

    part = PreviewCADPart(
        mesh_size=values.resolve(node.mesh_size) if node.mesh_size is not None else 2.0,
        mesh_order=values.resolve(node.mesh_order) if node.mesh_order is not None else 1,
        exterior_surface=node.exterior_surface or "extern",
        part_name=node.resolved_part_name() or "CADPreview",
    )
    part.initialize()
    return part


def cad_brep_records_from_node(
    node: PartNode, problem: ProblemDefinition | None = None
) -> list[dict]:
    """Return OCC face and edge geometry for the CAD viewport."""
    part = cad_part_from_node(node, problem)
    if not part.operations:
        return []
    return torchfea.cad.preview_brep(part.operations)
