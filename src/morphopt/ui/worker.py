"""One-shot geometry, finite-element, and export tasks without Qt imports."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def execute(request_path: str | Path) -> dict[str, Any]:
    """Execute a named task and write its structured response beside the request."""
    path = Path(request_path)
    directory = path.parent
    request = json.loads(path.read_text(encoding="utf-8"))
    action = request.pop("action")
    if action == "solve":
        import torchfea

        from ..postprocess import cpu_torch_defaults

        torchfea.enable_logging()
        with cpu_torch_defaults():
            controller = torchfea.load_model(str(directory / "analysis.npz"))
            result = controller.solve(if_initialize=False)
            if not result.converged:
                raise RuntimeError("The finite-element solution did not converge.")
            controller.save_model(
                str(directory / "solved_model.npz"), if_save_source_code=False
            )
            result.save(str(directory / "result.npz"))
        print("FEA completed.", flush=True)
        response = {"model": "solved_model.npz", "result": "result.npz"}
    elif action == "convert_cad":
        from .application.cad import convert_cad_to_boundary
        from .model.node_types.parts import CADPartNode
        from .model.problem import ProblemDefinition

        problem = ProblemDefinition.from_dict(request["problem"])
        source = next(part for part in problem.parts() if part.name == request["part"])
        if not isinstance(source, CADPartNode):
            raise TypeError("CAD conversion requires a CADPart definition.")
        replacement = convert_cad_to_boundary(source, problem, directory / "assets")
        output = directory / "boundary.json"
        output.write_text(
            json.dumps(replacement.to_dict(), ensure_ascii=False), encoding="utf-8"
        )
        response = {"path": str(output)}
    elif action == "export_fields":
        from ..postprocess import export_saved_fields

        output = export_saved_fields(
            directory / "export_model.npz",
            directory / "export_result.npz",
            request["destination"],
            format=request["format"],
            location=request["location"],
            fields=request["fields"],
            metadata=request["source"],
            overwrite=request["overwrite"],
        )
        response = {"path": str(output)}
    elif action == "export_native":
        from ..postprocess import NativeResultSnapshot, export_native_results

        request["directory"] = request.pop("destination")
        request["results"] = tuple(
            NativeResultSnapshot(**entry) for entry in request["results"]
        )
        response = {"path": str(export_native_results(**request))}
    elif action == "export_surfaces":
        from ..postprocess import export_boundary_surfaces

        response = {
            "paths": [str(output) for output in export_boundary_surfaces(**request)]
        }
    elif action == "export_gif":
        from ..postprocess import export_history_gif

        response = {"frames": export_history_gif(**request)}
    else:
        raise ValueError(f"Unknown worker action: {action}")
    (directory / "response.json").write_text(
        json.dumps(response, ensure_ascii=False), encoding="utf-8"
    )
    if "path" in response:
        print(response["path"], flush=True)
    return response


if __name__ == "__main__":
    execute(sys.argv[1])
