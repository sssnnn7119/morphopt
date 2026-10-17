"""One-shot FEA/export subprocess; intentionally imports no Qt widgets."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def execute(request_path: str) -> None:
    import torch
    import torchfea

    torch.set_default_dtype(torch.float64)
    torch.set_default_device("cpu")
    torchfea.enable_logging()
    request_file = Path(request_path)
    directory = request_file.parent
    request = json.loads(request_file.read_text(encoding="utf-8"))
    if request["action"] == "solve":
        controller = torchfea.load_model(str(directory / "analysis.npz"))
        result = controller.solve(if_initialize=False)
        if not result.converged:
            raise RuntimeError(
                "The finite-element solution did not converge; no result was accepted."
            )
        controller.save_model(
            str(directory / "solved_model.npz"), if_save_source_code=False
        )
        result.save(str(directory / "result.npz"))
        print("FEA completed.", flush=True)
    elif request["action"] == "export":
        from ..postprocess import export_results

        controller = torchfea.load_model(str(directory / "export_model.npz"))
        result = torchfea.solver.StaticResult.load(str(directory / "export_result.npz"))
        output = export_results(
            controller,
            result,
            request["destination"],
            format=request["format"],
            location=request["location"],
            fields=request["fields"],
            metadata=request["source"],
            overwrite=request.get("overwrite", False),
        )
        print(str(output), flush=True)
    else:
        raise ValueError(f"Unknown analysis action: {request['action']}")


if __name__ == "__main__":
    execute(sys.argv[1])
