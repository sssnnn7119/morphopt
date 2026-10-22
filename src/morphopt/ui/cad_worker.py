"""CAD conversion subprocess; geometry work is isolated from the UI event loop."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def execute(request_path: str) -> None:
    from .application.cad import convert_cad_to_boundary
    from .model.node_types.parts import CADPartNode
    from .model.problem import ProblemDefinition

    path = Path(request_path)
    request = json.loads(path.read_text(encoding="utf-8"))
    problem = ProblemDefinition.from_dict(request["problem"])
    source = next(part for part in problem.parts() if part.name == request["part"])
    if not isinstance(source, CADPartNode):
        raise TypeError("CAD conversion requires a CADPart definition.")
    replacement = convert_cad_to_boundary(source, problem, path.parent / "assets")
    (path.parent / "boundary.json").write_text(
        json.dumps(replacement.to_dict(), ensure_ascii=False), encoding="utf-8",
    )


if __name__ == "__main__":
    execute(sys.argv[1])
