"""The unified worker restores and converts a complete CAD definition."""

import json
from pathlib import Path
import subprocess
import sys

from morphopt.ui.application import ProblemLibrary
from morphopt.ui.model.node_types.cad import BoxOperationNode
from morphopt.ui.model.node_types.parts import BoundaryPartNode, CADPartNode


def test_cad_conversion_worker_returns_embedded_brep_and_structured_response(tmp_path):
    problem = ProblemLibrary.create_blank()
    part = CADPartNode(name="body")
    part.add_cad_operation(BoxOperationNode(name="box", dx=2, dy=3, dz=4))
    problem.add_part(part)
    before = problem.to_dict()
    request = tmp_path / "定义.json"
    request.write_text(
        json.dumps({"action": "convert_cad", "problem": before, "part": part.name}),
        encoding="utf-8",
    )
    process = subprocess.run(
        [sys.executable, "-c",
         "import sys; from morphopt.ui.worker import execute; execute(sys.argv[1]); "
         "assert 'PySide6.QtWidgets' not in sys.modules", str(request)],
        capture_output=True, timeout=45,
    )
    assert process.returncode == 0, process.stderr.decode("utf-8", errors="replace")
    response = json.loads((tmp_path / "response.json").read_text(encoding="utf-8"))
    replacement = BoundaryPartNode.from_dict(json.loads(Path(response["path"]).read_text()))
    assert replacement.name == part.name
    assert len(replacement.surfaces) == 1
    surface = replacement.surfaces[0]
    assert surface.data
    assert len(json.loads(surface.brep_metadata)["face_map"]) == 6
    assert problem.to_dict() == before
