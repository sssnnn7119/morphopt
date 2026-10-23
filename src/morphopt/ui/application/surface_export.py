"""Export BoundaryPart surfaces from a selected persisted design iteration."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from ...shapeopt.boundary_part import BoundaryPart
from ...shapeopt.surfaces.brep_surface import BREPSurface
from ..i18n import localized_message
from ..launcher import sanitize_name
from .results import ResultSession, last_completed_iteration

if TYPE_CHECKING:
    from ...optcore.modelparams.params import Params


@dataclass(frozen=True)
class BoundarySurfaceExport:
    part: str
    index: int
    surface_type: str
    formats: tuple[str, ...]


def boundary_surface_options(params: Params) -> tuple[BoundarySurfaceExport, ...]:
    """List all BoundaryPart boundaries, including fixed outer/cavity surfaces."""
    return tuple(
        BoundarySurfaceExport(name, index, type(surface).__name__,
                              ("stl",) if surface.is_discrete else ("stp", "stl"))
        for name, part in params.geometry.interfaces.items()
        if isinstance(part, BoundaryPart)
        for index, surface in enumerate(part.surfaceinterfaces)
    )


def export_boundary_surfaces(
    folder: str,
    iteration: int,
    destination: str,
    selections: list[dict],
    overwrite: bool = False,
) -> list[Path]:
    """Restore archived control points in a private session and export each surface."""
    if not 1 <= iteration <= last_completed_iteration(folder):
        raise ValueError(localized_message("ui.surface_export.invalid_iteration"))
    session = ResultSession()
    if not session.bind(folder) or session.params is None:
        raise ValueError(localized_message("ui.surface_export.model_unavailable"))
    options = {(item.part, item.index): item for item in boundary_surface_options(session.params)}
    targets = []
    for selection in selections:
        item = options[selection["part"], selection["index"]]
        format = selection["format"]
        if format not in item.formats:
            raise ValueError(localized_message("ui.surface_export.unsupported_format"))
        relative = Path(sanitize_name(item.part)) / f"surface_{item.index}.{format}"
        targets.append((item, format, relative))
    if not targets or len({relative for _item, _format, relative in targets}) != len(targets):
        raise ValueError(localized_message("ui.surface_export.invalid_selection"))

    log = str(Path(folder) / "log")
    for name in dict.fromkeys(item.part for item, _format, _relative in targets):
        part = session.params.geometry.interfaces[name]
        archive = Path(log) / part.pathlog_required()[0] / part.name
        for item, _format, _relative in targets:
            if item.part != name or not part.surfaceinterfaces[item.index].num_variables:
                continue
            stem = archive / f"Surface-{item.index}_iter-{iteration}"
            if not stem.is_file() and not stem.with_suffix(".npz").is_file():
                raise FileNotFoundError(localized_message(
                    "ui.surface_export.missing_surface", part=name, index=item.index, iteration=iteration,
                ))
        if any(surface.num_variables for surface in part.surfaceinterfaces):
            part.load(foldpath=log, iteration=iteration)

    output = Path(destination)
    with TemporaryDirectory(prefix="morphopt-surfaces-") as staging:
        stage = Path(staging)
        for item, format, relative in targets:
            surface = session.params.geometry.interfaces[item.part].surfaceinterfaces[item.index]
            surface.synchronize()
            directory = stage / relative.parent
            directory.mkdir(parents=True, exist_ok=True)
            if format == "stl" and not surface.is_discrete:
                # Tessellate the closed STEP boundary, including BSP end caps.
                with TemporaryDirectory(prefix="morphopt-surface-step-") as temporary:
                    native = Path(temporary) / surface.output_data(temporary, relative.stem)
                    BREPSurface(native).get_mesh().triangulate().save(directory / relative.name, binary=True)
            else:
                surface.output_data(str(directory), relative.stem)
            if not (stage / relative).is_file():
                raise RuntimeError(localized_message("ui.surface_export.file_not_created", path=str(relative)))
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
