"""Export the items declared by archived design components."""

from __future__ import annotations

import shutil
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NotRequired, TypedDict

from ...utils.paths import sanitize_name
from .._runtime import cpu_torch_defaults
from ..archive import OptimizationArchive


class _ComponentSelection(TypedDict):
    category: str
    name: str
    mode: str
    options: NotRequired[dict[str, object]]


def export_design_components(
    folder: str, iteration: int, destination: str, selections: list[_ComponentSelection],
    overwrite: bool = False,
) -> list[Path]:
    """Restore the selected components and publish their requested files and sidecars.

    Each selection specifies the category, component name, and component export mode.
    Optional keyword arguments in options are passed to that component.
    Output choices and file contents are defined by the component.
    """
    if not selections:
        raise ValueError("Select at least one component output.")
    archive = OptimizationArchive(folder)
    if not 1 <= iteration <= archive.completed_iteration:
        raise ValueError("Select an iteration that has been fully saved.")

    with cpu_torch_defaults(), TemporaryDirectory(prefix="morphopt-components-") as staging:
        stage = Path(staging)
        archive.initialize_params()
        components = {(category, obj.name): obj for category, obj in archive.design_components()}
        names = Counter(sanitize_name(name) for _, name in components)
        for entry in selections:
            category, name = entry["category"], entry["name"]
            component = archive.load_design_component(components[category, name], iteration)
            dirname = sanitize_name(name)
            directory = stage / category / dirname if names[dirname] > 1 else stage / dirname
            directory.mkdir(parents=True, exist_ok=True)
            component.export(directory, mode=entry["mode"], **entry.get("options", {}))

        # Include sidecars written by the component and check the whole batch before copying.
        output = Path(destination)
        files = sorted(path.relative_to(stage) for path in stage.rglob("*") if path.is_file())
        if not overwrite:
            for relative in files:
                if (output / relative).exists():
                    raise FileExistsError(output / relative)
        for relative in files:
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stage / relative, target)
        return [output / relative for relative in files]
