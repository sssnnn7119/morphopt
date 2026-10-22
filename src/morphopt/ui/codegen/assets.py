"""Collect the files referenced by a generated Python module."""

from __future__ import annotations

import ast
import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from ..model.node_types.cad import StepImportOperationNode
from ..model.node_types.parts import BoundaryPartNode, CADPartNode, INPPartNode
from ..model.node_types.surfaces import MeshSurfaceNode, BREPSurfaceNode
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
    asset_keys: dict[str, str] = {}
    constants = {constant.name: constant.value for constant in problem.helper_variables}

    def add_asset(
        node: Node, filename: str, content: bytes, format: str,
        reference: str, source: str | None = None,
        metadata: bytes = b"",
    ) -> DefinitionAsset:
        name = Path(filename).name
        digest = hashlib.sha256(content + metadata).hexdigest()
        if name in files and asset_keys[name] != digest:
            path = Path(name)
            name = f"{path.stem}_{digest[:16]}{path.suffix}"
        if name not in files:
            files[name] = DefinitionAsset(
                name, content, format, "geometry", source, node, []
            )
            asset_keys[name] = digest
        asset = files[name]
        asset.references.append(reference)
        paths[id(node)] = asset.relative_path
        return asset

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
                if isinstance(surface, MeshSurfaceNode):
                    add_file(surface, surface.path_stl, "stl", f"{part.name}/{surface.name}")
                elif isinstance(surface, BREPSurfaceNode) and surface.data:
                    reference = f"{part.name}/{surface.name}"
                    mapping = json.loads(surface.face_map)
                    metadata = json.dumps(mapping, indent=2).encode("utf-8") if mapping else b""
                    asset = add_asset(
                        surface, surface.filename,
                        base64.b64decode(surface.data, validate=True), "step", reference,
                        metadata=metadata,
                    )
                    if mapping:
                        name = str(Path(asset.name).with_suffix(".faces.json"))
                        if name not in files:
                            files[name] = DefinitionAsset(
                                name, metadata, "json", "metadata", None, surface, [],
                            )
                        files[name].references.append(reference)
    return paths, files
