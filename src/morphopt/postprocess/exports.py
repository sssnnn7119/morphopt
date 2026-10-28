"""Write field tables, native results, boundary surfaces, and history animations.

Every file-writing entry point is defined here. Numerical field evaluation is
owned by FiniteElementResults, saved state by OptimizationArchive, and scene
construction by visualization. UI callers supply paths and export options.
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
from collections.abc import Iterable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import TYPE_CHECKING, Any, Protocol

import numpy as np

from ..paths import sanitize_name
from ._runtime import cpu_torch_defaults
from .archive import OptimizationArchive
from .fields import RESULT_FIELDS, FiniteElementResults, ResultLocation, ResultTable
from .visualization import history_frames

if TYPE_CHECKING:
    from ..optcore.modelparams.params import Params


class TableWriter(Protocol):
    """Writer for a table of one finite-element record location."""

    def write(
        self, table: ResultTable, path: Path, metadata: dict[str, Any]
    ) -> None: ...


class CSVWriter:
    def write(self, table: ResultTable, path: Path, metadata: dict[str, Any]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(table.columns)
            writer.writerows(table.rows)


class NPZWriter:
    def write(self, table: ResultTable, path: Path, metadata: dict[str, Any]) -> None:
        rows = list(table.rows)
        columns = {}
        for index, name in enumerate(table.columns):
            values = [row[index] for row in rows]
            if name in ("instance", "element_block", "reference_point"):
                columns[name] = np.asarray(values, dtype=str)
            elif any(value is None for value in values):
                columns[name] = np.asarray(
                    [np.nan if value is None else value for value in values],
                    dtype=float,
                )
            else:
                columns[name] = np.asarray(values)
        columns["__metadata__"] = np.asarray(json.dumps(metadata, ensure_ascii=False))
        with path.open("wb") as stream:
            np.savez_compressed(stream, **columns)


TABLE_WRITERS: dict[str, TableWriter] = {"csv": CSVWriter(), "npz": NPZWriter()}


def export_saved_fields(
    model_path: str | Path,
    result_path: str | Path,
    path: str | Path,
    *,
    location: ResultLocation | str = ResultLocation.NODES,
    fields: tuple[str, ...] | list[str] | None = None,
    format: str | None = None,
    metadata: dict[str, Any] | None = None,
    overwrite: bool = False,
) -> Path:
    """Load a saved model and solution, then export selected physical fields."""
    import torchfea

    with cpu_torch_defaults():
        controller = torchfea.load_model(str(model_path))
        result = torchfea.solver.StaticResult.load(str(result_path))
        controller.assembly.set_work_conditions(result.work_conditions)
        return export_fields(
            controller,
            result,
            path,
            location=location,
            fields=fields,
            format=format,
            metadata=metadata,
            overwrite=overwrite,
        )


def export_fields(
    controller: Any,
    result: Any,
    path: str | Path,
    *,
    location: ResultLocation | str = ResultLocation.NODES,
    fields: tuple[str, ...] | list[str] | None = None,
    format: str | None = None,
    metadata: dict[str, Any] | None = None,
    overwrite: bool = False,
) -> Path:
    """Export one record location, merging all selected quantities into columns."""
    destination = Path(path)
    location = ResultLocation(location)
    writer = TABLE_WRITERS[format or destination.suffix.lstrip(".").lower()]
    if not result.converged:
        raise ValueError("Only converged results can be exported.")
    if result.model_hash != controller.get_model_hash():
        raise ValueError("The result does not belong to this finite-element model.")
    if destination.exists() and not overwrite:
        raise FileExistsError(destination)
    table = FiniteElementResults(controller, result).table(location, fields)
    description = {
        "schema_version": 2,
        "location": location.value,
        "units": "model consistent units",
        "index_base": 1,
        "coordinate_frame": "global assembly axes",
        "model_hash": result.model_hash,
        "source": metadata or {},
        "fields": [
            {"key": key, "description": RESULT_FIELDS[key].description}
            for key in table.fields
        ],
        "columns": table.columns,
    }
    # Publish only complete files; preserve an existing file on extraction failure.
    temporary = None
    try:
        with NamedTemporaryFile(
            dir=destination.parent, prefix=f".{destination.name}.", delete=False
        ) as stream:
            temporary = Path(stream.name)
        writer.write(table, temporary, description)
        if overwrite:
            os.replace(temporary, destination)
        else:
            # Exclusive creation also works on filesystems without hard links.
            created = False
            try:
                with destination.open("xb") as output:
                    created = True
                    with temporary.open("rb") as source:
                        shutil.copyfileobj(source, output)
            except Exception:
                if created:
                    destination.unlink(missing_ok=True)
                raise
        return destination
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
        "CON",
        "PRN",
        "AUX",
        "NUL",
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


@dataclass(frozen=True)
class BoundarySurfaceInfo:
    """One BoundaryPart surface and the formats supported by its geometry."""

    part: str
    index: int
    surface_type: str
    formats: tuple[str, ...]


def boundary_surface_options(
    params: Params,
) -> tuple[BoundarySurfaceInfo, ...]:
    """List BoundaryPart surfaces and the file formats each supports."""
    from ..shapeopt.boundary_part import BoundaryPart

    return tuple(
        BoundarySurfaceInfo(
            part_name,
            index,
            type(surface).__name__,
            ("stl",) if surface.is_discrete else ("stp", "stl"),
        )
        for part_name, part in params.geometry.interfaces.items()
        if isinstance(part, BoundaryPart)
        for index, surface in enumerate(part.surfaceinterfaces)
    )


def export_boundary_surfaces(
    folder: str,
    iteration: int,
    destination: str,
    selections: list[dict[str, Any]],
    overwrite: bool = False,
) -> list[Path]:
    """Restore and export surfaces using the archive's CPU tensor settings."""
    with cpu_torch_defaults():
        archive = OptimizationArchive(folder)
        if not 1 <= iteration <= archive.completed_iteration:
            raise ValueError("Select an iteration that has been fully saved.")

        params = archive.initialize_params()
        if params is None:
            raise ValueError("The archived geometry definition is unavailable.")
        options = {
            (item.part, item.index): item for item in boundary_surface_options(params)
        }
        targets: list[tuple[BoundarySurfaceInfo, str, Path]] = []
        for selection in selections:
            item = options.get((selection.get("part"), selection.get("index")))
            if item is None:
                raise ValueError("A selected boundary surface is unavailable.")
            file_format = selection.get("format")
            if file_format not in item.formats:
                raise ValueError(
                    f"Surface {item.part}/surface_{item.index} does not support {file_format!r}."
                )
            relative = (
                Path(sanitize_name(item.part)) / f"surface_{item.index}.{file_format}"
            )
            targets.append((item, file_format, relative))
        relative_paths = [relative for _item, _format, relative in targets]
        if not targets or len(set(relative_paths)) != len(relative_paths):
            raise ValueError("Select surfaces with distinct output filenames.")

        for part_name in dict.fromkeys(item.part for item, _format, _path in targets):
            part = params.geometry.interfaces[part_name]
            part_archive = archive.log_folder / part.pathlog_required()[0] / part.name
            for item, _format, _path in targets:
                if item.part != part_name:
                    continue
                surface = part.surfaceinterfaces[item.index]
                if not surface.num_variables:
                    continue
                stem = part_archive / f"Surface-{item.index}_iter-{iteration}"
                if not stem.is_file() and not stem.with_suffix(".npz").is_file():
                    raise FileNotFoundError(
                        f"Missing archived parameters for {part_name}/surface_{item.index} "
                        f"at iteration {iteration}."
                    )
            if any(surface.num_variables for surface in part.surfaceinterfaces):
                archive.load_geometry_part(part_name, iteration)

        output = Path(destination)
        with TemporaryDirectory(prefix="morphopt-surfaces-") as staging:
            stage = Path(staging)
            for item, file_format, relative in targets:
                surface = params.geometry.interfaces[item.part].surfaceinterfaces[
                    item.index
                ]
                surface.synchronize()
                directory = stage / relative.parent
                directory.mkdir(parents=True, exist_ok=True)
                if file_format == "stl" and not surface.is_discrete:
                    from ..shapeopt.surfaces.brep_surface import BREPSurface

                    with TemporaryDirectory(
                        prefix="morphopt-surface-step-"
                    ) as temporary:
                        native_path = Path(temporary) / surface.output_data(
                            temporary, relative.stem
                        )
                        BREPSurface(native_path).get_mesh().triangulate().save(
                            directory / relative.name, binary=True
                        )
                else:
                    surface.output_data(str(directory), relative.stem)
                if not (stage / relative).is_file():
                    raise RuntimeError(f"Surface export did not create {relative}.")

            files = sorted(path for path in stage.rglob("*") if path.is_file())
            destinations = [output / path.relative_to(stage) for path in files]
            if not overwrite:
                for path in destinations:
                    if path.exists():
                        raise FileExistsError(path)
            for source, target in zip(files, destinations, strict=True):
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        return destinations


def export_history_gif(
    folder: str,
    destination: str,
    mode: str,
    target: dict[str, str],
    first_iteration: int,
    last_iteration: int,
    fps: int,
    camera: dict[str, Any],
    window_size: tuple[int, int],
    style: dict[str, Any],
) -> int:
    """Write archived design or deformation frames using the supplied view."""
    import imageio.v2 as imageio

    archive = OptimizationArchive(folder)
    if not 1 <= first_iteration <= last_iteration <= archive.completed_iteration:
        raise ValueError("The selected iteration range is not available.")
    if fps < 1:
        raise ValueError("GIF frame rate must be at least 1 frame per second.")
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}.partial.gif")
    count = 0
    frames = history_frames(
        archive,
        range(first_iteration, last_iteration + 1),
        mode=mode,
        target=target,
        camera=camera,
        window_size=window_size,
        style=style,
    )
    try:
        with (
            cpu_torch_defaults(),
            closing(frames),
            imageio.get_writer(
                temporary, mode="I", duration=1000 / fps, loop=0
            ) as writer,
        ):
            for frame in frames:
                writer.append_data(frame)
                count += 1
        if count == 0:
            raise ValueError("No frames are available in the selected iteration range.")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return count
