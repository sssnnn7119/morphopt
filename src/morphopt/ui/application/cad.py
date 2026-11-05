"""Build CAD Part previews and exports from ordered UI operation nodes."""

from __future__ import annotations

import base64
import json
import runpy
from pathlib import Path

import torchfea

from ...constants import CONSTANT
from ...optcore.modelparams.parts import CADPart
from ..model.node_types.cad import StepImportOperationNode
from ..model.node_types.parts import BoundaryPartNode, CADPartNode
from ..model.node_types.surfaces import BREPSurfaceNode
from ..model.problem import CADOperationNode, ProblemDefinition
from ..model.registry import (
    CAD_OPERATION_TYPES,
)
from .expressions import DefinitionValues


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
        if field.type == "float" and isinstance(value, str) and namespace is not None:
            value = eval(compile(value, "<CAD parameter>", "eval"), namespace)
        if value is not None:
            kwargs[key] = value
    return operation_class(**kwargs)


def cad_operations_from_node(
    node: CADPartNode, problem: ProblemDefinition | None = None
) -> tuple[torchfea.cad.CADOperation, ...]:
    """Resolve the current UI CAD operations for preview or export."""
    namespace = DefinitionValues(problem).namespace
    return tuple(
        cad_operation_from_node(operation, namespace)
        for operation in node.operations
    )


def cad_preview_signature(
    node: CADPartNode, problem: ProblemDefinition | None = None
) -> tuple[str, ...]:
    """Return a stable signature for the resolved CAD preview geometry."""
    return tuple(
        f"{type(operation).__qualname__}:"
        f"{json.dumps(vars(operation), sort_keys=True, default=repr)}"
        for operation in cad_operations_from_node(node, problem)
    )


def cad_part_from_node(
    node: CADPartNode, problem: ProblemDefinition | None = None
) -> CADPart:
    """Create a preview Part from its structured, ordered CAD feature list."""
    values = DefinitionValues(problem)
    operations = tuple(
        cad_operation_from_node(operation, values.namespace)
        for operation in node.operations
    )

    class PreviewCADPart(CADPart):
        def define_operations(self) -> None:
            for operation in operations:
                self.add_operation(operation)

    part = PreviewCADPart(
        mesh_size=(
            values.resolve(node.mesh_size)
            if node.mesh_size is not None
            else CONSTANT.UI.SCHEMA_FIELDS.PARTS.CADPART.MESH_SIZE.DEFAULT
        ),
        mesh_order=values.resolve(node.mesh_order)
        if node.mesh_order is not None
        else 1,
        exterior_surface=node.exterior_surface or "extern",
        part_name=node.assembly_name or "CADPreview",
    )
    part.initialize()
    return part


def cad_brep_records_from_node(
    node: CADPartNode, problem: ProblemDefinition | None = None
) -> list[dict]:
    """Return OCC face and edge geometry for the CAD viewport."""
    operations = cad_operations_from_node(node, problem)
    if not operations:
        return []
    return torchfea.cad.preview_brep(operations)


def export_cad_step(
    node: CADPartNode, path: str | Path, problem: ProblemDefinition | None = None
) -> None:
    """Export the Part's final CAD solids in local coordinates without meshing."""
    operations = cad_operations_from_node(node, problem)
    torchfea.cad.export_step(operations, str(path))


def convert_cad_to_boundary(
    node: CADPartNode,
    problem: ProblemDefinition,
    asset_directory: str | Path,
) -> BoundaryPartNode:
    """Convert the generated CAD definition to embedded BREP boundary assets.

    This function constructs the replacement without changing the problem.
    The caller commits it through ProblemDefinition.replace_part().
    """
    from .definitions import ProblemLibrary

    directory = Path(asset_directory)
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "conversion.py"
    ProblemLibrary.export_python(problem, script)
    namespace = runpy.run_path(str(script), run_name="morphopt_cad_conversion")
    geometry = namespace["ThisController"].Params.GeometryParams()
    if not geometry.interfaces:
        geometry.define_interface()
    part = geometry.interface(node.name)
    if not isinstance(part, CADPart):
        raise TypeError("The selected definition must generate a CADPart.")
    part.initialize()
    boundary = part.to_boundary_part(directory / "boundaries")
    replacement = BoundaryPartNode(
        name=node.name,
        fea_seed_size=boundary.mesh_size,
        mesh_order=boundary.mesh_order,
        exterior_surface=boundary.exterior_surface,
    )
    for index, surface in enumerate(boundary.surface_interfaces()):
        path = surface.path_step
        replacement.add_surface(
            BREPSurfaceNode(
                name=f"surface_{index}",
                flip=index > 0,
                filename=f"{node.name}_surface_{index}.stp",
                data=base64.b64encode(path.read_bytes()).decode("ascii"),
                brep_metadata=json.dumps(surface.metadata()),
            )
        )
    return replacement
