"""Export archived boundary geometry in a CPU subprocess without Qt widgets."""
from __future__ import annotations

import json
from pathlib import Path
import sys


def execute(request_path: str) -> None:
    import torch

    from .application.surface_export import export_boundary_surfaces

    torch.set_default_dtype(torch.float64)
    torch.set_default_device("cpu")
    request = json.loads(Path(request_path).read_text(encoding="utf-8"))
    for path in export_boundary_surfaces(**request):
        print(path, flush=True)


if __name__ == "__main__":
    execute(sys.argv[1])
