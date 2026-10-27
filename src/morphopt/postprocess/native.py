"""Archive native TorchFEA models and solutions without changing their contents."""

from collections.abc import Iterable
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil


@dataclass(frozen=True)
class NativeResultSnapshot:
    key: str
    result_path: str | None
    case: str | None = None
    analysis_number: str | int | None = None
    created_at: str | None = None


def normalize_export_name(name: str) -> str:
    """Accept a portable filename prefix, never a path or Windows device name."""
    name = name.strip()
    reserved = {
        "CON", "PRN", "AUX", "NUL",
        *(f"{kind}{index}" for kind in ("COM", "LPT") for index in range(1, 10)),
    }
    if (
        not name
        or name.endswith(".")
        or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
        or name.split(".")[0].upper() in reserved
    ):
        raise ValueError("Invalid export filename prefix.")
    return name


def export_native_results(
    directory: str | Path,
    *,
    name: str,
    iteration: int,
    model_path: str | Path,
    results: Iterable[NativeResultSnapshot],
    source: str,
) -> Path:
    """Copy one iteration and every saved case/analysis into a new directory.

    All results share the iteration model. Restore each result's work_conditions
    before using it with that model. Files remain directly loadable by
    torchfea.load_model() and StaticResult.load().
    """
    name = normalize_export_name(name)
    model_name = f"{name}_femodel.npz"
    files = {model_name: Path(model_path)}
    records = []
    for result in results:
        if result.analysis_number is None:
            result_name = f"{name}_case{result.case}.npz"
        else:
            result_name = f"{name}_analysis{result.analysis_number}.npz"
        if result.result_path is not None:
            files[result_name] = Path(result.result_path)
        records.append(
            {
                "key": result.key,
                "model": model_name,
                "result": result_name if result.result_path is not None else None,
                "case": result.case,
                "analysis_number": result.analysis_number,
                "created_at": result.created_at,
            }
        )
    # Check the complete snapshot list before creating any output files.
    for path in files.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    parent = Path(directory)
    parent.mkdir(parents=True, exist_ok=True)
    suffix = 1
    while True:
        target = parent / (name + (f"_{suffix}" if suffix > 1 else ""))
        try:
            target.mkdir()
            break
        except FileExistsError:
            suffix += 1
    try:
        for file_name, path in files.items():
            shutil.copyfile(path, target / file_name)
        manifest = {
            "format": "torchfea",
            "version": 1,
            "source": source,
            "name": name,
            "iteration": iteration,
            "model": model_name,
            "results": records,
            "restore_work_conditions": True,
        }
        (target / f"{name}_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        shutil.rmtree(target)
        raise
    return target
