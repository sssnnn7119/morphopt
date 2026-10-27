"""Render history GIFs in a separate CPU process."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def execute(request_path: str) -> None:
    from ..postprocess import export_history_gif

    request = json.loads(Path(request_path).read_text(encoding="utf-8"))
    count = export_history_gif(**request)
    print(f"Exported {count} frames", flush=True)


if __name__ == "__main__":
    execute(sys.argv[1])
