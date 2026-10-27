"""Export archived boundary geometry in a CPU subprocess without Qt widgets."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def execute(request_path: str) -> None:
    from ..postprocess import export_boundary_surfaces

    request = json.loads(Path(request_path).read_text(encoding="utf-8"))
    for path in export_boundary_surfaces(**request):
        print(path, flush=True)


if __name__ == "__main__":
    execute(sys.argv[1])
