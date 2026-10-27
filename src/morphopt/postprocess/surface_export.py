"""Export archived BoundaryPart surfaces as STEP or STL files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any

from ..paths import sanitize_name
from .archive import OptimizationArchive
from .context import cpu_torch_defaults

if TYPE_CHECKING:
    from ..optcore.modelparams.params import Params


@dataclass(frozen=True)
class BoundarySurfaceExport:
    """One BoundaryPart surface and the formats supported by its geometry."""

    part: str
    index: int
    surface_type: str
    formats: tuple[str, ...]


def boundary_surface_options(
    params: Params,
) -> tuple[BoundarySurfaceExport, ...]:
    """List BoundaryPart surfaces and the file formats each supports."""
    from ..shapeopt.boundary_part import BoundaryPart

    return tuple(
        BoundarySurfaceExport(
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
        targets: list[tuple[BoundarySurfaceExport, str, Path]] = []
        for selection in selections:
            item = options.get((selection.get("part"), selection.get("index")))
            if item is None:
                raise ValueError("A selected boundary surface is unavailable.")
            file_format = selection.get("format")
            if file_format not in item.formats:
                raise ValueError(
                    f"Surface {item.part}/surface_{item.index} does not support {file_format!r}."
                )
            relative = Path(sanitize_name(item.part)) / f"surface_{item.index}.{file_format}"
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
                surface = params.geometry.interfaces[item.part].surfaceinterfaces[item.index]
                surface.synchronize()
                directory = stage / relative.parent
                directory.mkdir(parents=True, exist_ok=True)
                if file_format == "stl" and not surface.is_discrete:
                    from ..shapeopt.surfaces.brep_surface import BREPSurface

                    with TemporaryDirectory(prefix="morphopt-surface-step-") as temporary:
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
