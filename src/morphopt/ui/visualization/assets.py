"""Build raw geometry-asset scenes without changing the definition."""

from __future__ import annotations

import base64
from pathlib import Path
from tempfile import TemporaryDirectory

import pyvista as pv

from ..codegen.assets import DefinitionAsset
from ..model.node_types.parts import CADPartNode, INPPartNode
from ..model.problem import CADOperationNode, ProblemDefinition
from ..theme import theme_manager
from .geometry import PreviewGeometry
from .scene import MessageItem, PreviewScene


def geometry_asset_scene(asset: DefinitionAsset) -> PreviewScene:
    """Display the imported file in local coordinates, before later CAD operations."""
    problem = ProblemDefinition()
    if asset.format == "step":
        operation = CADOperationNode.create("StepImport", operation_id="asset_import")
        operation.filename = asset.name
        operation.data = base64.b64encode(asset.content).decode("ascii")
        part = CADPartNode(name=asset.name, children=[operation])
        scene = PreviewGeometry().build(problem, "part", part)
    else:
        with TemporaryDirectory(prefix="morphopt_asset_") as directory:
            path = Path(directory) / asset.name
            path.write_bytes(asset.content)
            if asset.format == "stl":
                scene = PreviewScene()
                scene.add_base(
                    asset.name, pv.read(path),
                    color=theme_manager.palette.viewer.geometry.uninstanced_color,
                    show_edges=False, smooth_shading=True,
                )
            elif asset.format == "inp":
                part = INPPartNode(
                    name=asset.name, mesh_file=str(path),
                    inp_part_name=asset.node.inp_part_name,
                )
                scene = PreviewGeometry().build(problem, "part", part)
            else:
                raise ValueError(f"Unsupported geometry asset format: {asset.format}")
    errors = [item.text for item in scene.items if isinstance(item, MessageItem)]
    if errors:
        raise ValueError("\n".join(errors))
    return scene
