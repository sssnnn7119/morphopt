"""Export TorchFEA snapshots and Abaqus input decks."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from ...utils.paths import sanitize_name
from .._runtime import cpu_torch_defaults
from ..archive import OptimizationArchive, load_solved_model


@dataclass(frozen=True)
class NativeResultSnapshot:
    """Describe one native TorchFEA result selected for export with its shared model."""
    key: str
    result_path: str | None
    case: str | None = None
    analysis_number: str | int | None = None
    created_at: str | None = None

    def filename(self, prefix: str) -> str:
        """Return the native solution filename recorded in the export manifest."""
        label = (
            f"case{self.case}" if self.analysis_number is None else f"analysis{self.analysis_number}"
        )
        return normalize_export_name(f"{prefix}_{label}.npz")


def normalize_export_name(name: str) -> str:
    """Accept a portable filename prefix, never a path or Windows device name.

    Args:
        name (str): Name identifying the item in its owning collection.

    Returns:
        str: Accept a portable filename prefix, never a path or Windows device name.
    """
    name = name.strip()
    if not name or sanitize_name(name) != name:
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

    All results share the iteration model. Restore each result's work_conditions before using it
    with that model. Files remain directly loadable by torchfea.load_model() and
    StaticResult.load().

    Args:
        directory (str | Path): Directory in which output files or child directories are
            created.
        name (str): Name identifying the item in its owning collection.
        iteration (int): Iteration index associated with the saved or current model state.
        model_path (str | Path): Path to the saved TorchFEA finite-element model.
        results (Iterable[NativeResultSnapshot]): Results retained in their registered load-case
            or export order.
        source (str): Source object, path, or metadata from which the operation reads its input.

    Returns:
        Path: Copy one iteration and every saved case/analysis into a new directory.
    """
    name = normalize_export_name(name)
    model_name = f"{name}_femodel.npz"
    files = {model_name: Path(model_path)}
    records = []
    for result in results:
        result_name = None
        if result.result_path is not None:
            result_name = result.filename(name)
            files[result_name] = Path(result.result_path)
        records.append(
            {
                "key": result.key,
                "model": model_name,
                "result": result_name,
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


def export_history_inp(
    folder: str, iteration: int, case: str | None, destination: str, nlgeom: bool = True,
) -> Path:
    """Export the undeformed iteration mesh. A named case includes a static analysis step.

    With case=None, write the part meshes and their named sets in local coordinates
    for import into Abaqus/CAE, independently of material and interaction mappings.
    """
    import torchfea

    archive = OptimizationArchive(folder)
    output = Path(destination)
    with cpu_torch_defaults(), TemporaryDirectory(dir=output.parent) as temporary:
        model_path = archive.fea_model_path(iteration)
        staged = Path(temporary) / "model.inp"
        if case is None:
            controller = torchfea.load_model(str(model_path))
            part_file = Path(temporary) / "part.inp"
            with staged.open("wb") as output_stream:
                output_stream.write(b"*Heading\nMorphOpt part meshes\n")
                for name, part in controller.assembly._parts.items():
                    part.export_inp(str(part_file), name)
                    with part_file.open("rb") as stream:
                        shutil.copyfileobj(stream, output_stream)
        else:
            controller, _ = load_solved_model(model_path, archive.fea_result_path(case, iteration))
            # Abaqus uses the standard volumetric law for the exported Neo-Hookean model.
            for part in controller.assembly._parts.values():
                for block in part.elems.values():
                    for name, material in block.materials.items():
                        if type(material) is torchfea.materials.NeoHookeanLnJ:
                            block.set_materials(
                                torchfea.materials.NeoHookean(material.mu, material.kappa), name=name
                            )
            controller.export_inp(staged, nlgeom=nlgeom)
        staged.replace(output)
    return output
