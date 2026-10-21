"""Collect the files referenced by a generated Python module."""

from __future__ import annotations

import ast
import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path

from ..model.node_types.cad import StepImportOperationNode
from ..model.node_types.parts import BoundaryPartNode, CADPartNode, INPPartNode
from ..model.node_types.surfaces import FixedSTLSurfaceNode
from ..model.problem import Node, ProblemDefinition

PYTHON_ASSET_DIRECTORY = "morphopt_assets"


@dataclass
class DefinitionAsset:
    """One exported resource and the definition entries that reference it."""

    name: str
    content: bytes
    format: str
    category: str
    source: str | None
    node: Node
    references: list[str]

    @property
    def relative_path(self) -> str:
        return (Path(PYTHON_ASSET_DIRECTORY) / self.name).as_posix()


def collect_python_assets(
    problem: ProblemDefinition,
) -> tuple[dict[int, str], dict[str, DefinitionAsset]]:
    """Return node paths and file contents using destination-independent names."""
    paths: dict[int, str] = {}
    files: dict[str, DefinitionAsset] = {}
    constants = {constant.name: constant.value for constant in problem.helper_variables}

    def add_asset(
        node: Node, filename: str, content: bytes, format: str,
        reference: str, source: str | None = None,
    ) -> None:
        name = Path(filename).name
        if name in files and files[name].content != content:
            path = Path(name)
            digest = hashlib.sha256(content).hexdigest()[:16]
            name = f"{path.stem}_{digest}{path.suffix}"
        if name not in files:
            files[name] = DefinitionAsset(
                name, content, format, "geometry", source, node, []
            )
        asset = files[name]
        asset.references.append(reference)
        paths[id(node)] = asset.relative_path

    def add_file(node: Node, value: str, format: str, reference: str) -> None:
        paths[id(node)] = ""
        if not value:
            return
        if value in constants:
            value = ast.literal_eval(constants[value])
        source = Path(value).expanduser()
        add_asset(node, source.name, source.read_bytes(), format, reference, str(source))

    for part in problem.parts():
        if isinstance(part, INPPartNode):
            add_file(part, part.mesh_file, "inp", part.name)
        elif isinstance(part, CADPartNode):
            for operation in part.operations:
                if isinstance(operation, StepImportOperationNode):
                    paths[id(operation)] = ""
                    if operation.data:
                        add_asset(
                            operation,
                            operation.filename or f"{operation.operation_id}.step",
                            base64.b64decode(operation.data, validate=True),
                            "step", f"{part.name}/{operation.operation_id}",
                        )
        elif isinstance(part, BoundaryPartNode):
            for surface in part.surfaces:
                if isinstance(surface, FixedSTLSurfaceNode):
                    add_file(surface, surface.path_stl, "stl", f"{part.name}/{surface.name}")
    return paths, files
