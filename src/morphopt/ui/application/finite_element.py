"""Independent analysis copies of completed optimization iterations."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import torch
import torchfea

from ...postprocess import IterationModel, cpu_torch_defaults, normalize_export_name
from ..i18n import localized_message


@dataclass(frozen=True)
class FiniteElementResult:
    """One original work condition or an immutable completed analysis snapshot."""

    key: str
    source: IterationModel
    model_path: Path
    result_path: Path | None
    number: str | int | None = None
    created_at: datetime | None = None
    log_path: Path | None = None

    @property
    def is_original(self) -> bool:
        return self.number is None


class FiniteElementSession:
    """Own a private mesh/material/load model, independent of all optimization objects."""

    def __init__(self):
        self._workspace = TemporaryDirectory(prefix="morphopt-fea-")
        self.directory = Path(self._workspace.name)
        self.source: IterationModel | None = None
        self.controller = None
        self.result = None
        self.selected_result: FiniteElementResult | None = None
        self._analyses: list[FiniteElementResult] = []

    @staticmethod
    def _original_result(source: IterationModel) -> FiniteElementResult:
        source = IterationModel(
            str(Path(source.folder).resolve()), source.iteration, source.case
        )
        return FiniteElementResult(
            f"original_{source.case}", source, source.model_path, source.result_path
        )

    def result_options(
        self, folder: str, iteration: int
    ) -> tuple[FiniteElementResult, ...]:
        """List original cases and all completed analyses for this exact model."""
        source = IterationModel(str(Path(folder).resolve()), iteration)
        originals = tuple(
            self._original_result(IterationModel(source.folder, iteration, case))
            for case in source.cases()
        )
        if not originals:
            originals = (self._original_result(source),)
        analyses = tuple(
            entry
            for entry in self._analyses
            if entry.source.folder == source.folder
            and entry.source.iteration == iteration
        )
        return originals + analyses

    def import_iteration(self, source: IterationModel) -> None:
        self.select_result(self._original_result(source))

    def select_result(self, entry: FiniteElementResult) -> None:
        """Load a fresh private model so edits never mutate stored results."""
        if not entry.model_path.is_file():
            raise FileNotFoundError(
                localized_message(
                    "ui.fea.missing_iteration_model", iteration=entry.source.iteration
                )
            )
        with cpu_torch_defaults():
            controller = torchfea.load_model(str(entry.model_path))
            result = None
            if entry.result_path is not None:
                result = torchfea.solver.StaticResult.load(str(entry.result_path))
                controller.assembly.set_work_conditions(result.work_conditions)
                if result.model_hash != controller.get_model_hash():
                    raise ValueError(localized_message("ui.fea.model_result_mismatch"))
                if not result.converged:
                    result = None
        self.source, self.controller, self.result = entry.source, controller, result
        self.selected_result = entry

    def load_values(self) -> tuple[tuple[str, str, str, bool, np.ndarray], ...]:
        if self.controller is None:
            return ()
        return tuple(
            (
                name,
                type(load).__name__,
                self._load_target(load),
                load.enabled is not False,
                load._parameters.detach().cpu().numpy().copy(),
            )
            for name, load in self.controller.assembly._loads.items()
        )

    @staticmethod
    def _load_target(load) -> str:
        keys = (
            "instance_name",
            "_instance_name",
            "instance_name1",
            "instance_name2",
            "surface_set",
            "surface_name",
            "surface_name1",
            "surface_name2",
            "element_name",
            "_element_name",
            "rp_name",
            "rp_name1",
            "rp_name2",
            "obj_name",
        )
        return " · ".join(
            dict.fromkeys(
                str(getattr(load, key)) for key in keys if getattr(load, key, None)
            )
        )

    def apply_loads(self, values: dict[str, tuple[bool, list[float]]]) -> None:
        """Validate all edits before changing any load in the private model."""
        loads = self.controller.assembly._loads
        parsed = {}
        for name, (enabled, data) in values.items():
            load = loads[name]
            numbers = np.asarray(data, dtype=float)
            if (
                numbers.size != load._parameters.numel()
                or not np.isfinite(numbers).all()
            ):
                raise ValueError(
                    localized_message(
                        "ui.fea.invalid_load_values",
                        name=name,
                        count=load._parameters.numel(),
                    )
                )
            parsed[name] = (
                bool(enabled),
                torch.as_tensor(
                    numbers,
                    dtype=load._parameters.dtype,
                    device=load._parameters.device,
                ).reshape(load._parameters.shape),
            )
        for name, (enabled, tensor) in parsed.items():
            loads[name]._parameters = tensor
            loads[name].enabled = enabled
        self.result = None

    def solve_request(self) -> Path:
        with cpu_torch_defaults():
            self.controller.save_model(
                str(self.directory / "analysis.npz"), if_save_source_code=False
            )
        return self._write_request({"action": "solve"})

    def export_request(
        self,
        path: str,
        format: str,
        fields: list[str],
        *,
        location: str = "nodes",
        overwrite: bool = False,
    ) -> Path:
        if self.result is None:
            raise ValueError(localized_message("ui.fea.result_required"))
        with cpu_torch_defaults():
            self.controller.save_model(
                str(self.directory / "export_model.npz"), if_save_source_code=False
            )
            self.result.save(str(self.directory / "export_result.npz"))
        provenance = {
            "folder": self.source.folder,
            "iteration": self.source.iteration,
            "case": self.source.case,
        }
        if self.selected_result is not None:
            entry = self.selected_result
            provenance.update(
                result_id=entry.key,
                result_type="original" if entry.is_original else "finite_element",
            )
            if entry.created_at is not None:
                provenance.update(
                    analysis_number=entry.number,
                    created_at=entry.created_at.isoformat(),
                )
        return self._write_request(
            {
                "action": "export_fields",
                "destination": path,
                "format": format,
                "fields": fields,
                "location": location,
                "overwrite": overwrite,
                "source": provenance,
            }
        )

    def native_export_request(self, directory: str, name: str) -> Path:
        """Export stored iteration snapshots, independently of unsolved UI edits."""
        if self.source is None:
            raise ValueError(localized_message("ui.fea.result_required"))
        try:
            name = normalize_export_name(name)
        except ValueError as exc:
            raise ValueError(localized_message("ui.fea.invalid_export_name")) from exc
        snapshots = []
        for entry in self.result_options(self.source.folder, self.source.iteration):
            snapshots.append(
                {
                    "key": entry.key,
                    "result_path": str(entry.result_path)
                    if entry.result_path is not None
                    else None,
                    "case": entry.source.case,
                    "analysis_number": entry.number,
                    "created_at": entry.created_at.isoformat()
                    if entry.created_at is not None
                    else None,
                }
            )
        return self._write_request(
            {
                "action": "export_native",
                "destination": directory,
                "name": name,
                "iteration": self.source.iteration,
                "model_path": str(self.source.model_path),
                "results": snapshots,
                "source": self.source.folder,
            }
        )

    def _write_request(self, request: dict) -> Path:
        path = self.directory / "request.json"
        path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        return path

    def accept_solution(self, output: str = "") -> FiniteElementResult:
        """Archive a successful solve before publishing it to the result selector."""
        if self.source is None:
            raise ValueError(localized_message("ui.fea.result_required"))
        with cpu_torch_defaults():
            controller = torchfea.load_model(str(self.directory / "solved_model.npz"))
            result = torchfea.solver.StaticResult.load(
                str(self.directory / "result.npz")
            )
            if not result.converged or result.model_hash != controller.get_model_hash():
                raise ValueError(localized_message("ui.fea.model_result_mismatch"))
        number = len(self._analyses) + 1
        key = f"analysis_{number}"
        directory = self.directory / "results" / key
        directory.mkdir(parents=True)
        try:
            shutil.copyfile(
                self.directory / "solved_model.npz", directory / "model.npz"
            )
            shutil.copyfile(self.directory / "result.npz", directory / "result.npz")
            (directory / "output.txt").write_text(output, encoding="utf-8")
        except Exception:
            shutil.rmtree(directory)
            raise
        entry = FiniteElementResult(
            key,
            self.source,
            directory / "model.npz",
            directory / "result.npz",
            number,
            datetime.now().astimezone(),
            directory / "output.txt",
        )
        self._analyses.append(entry)
        self.controller, self.result = controller, result
        self.selected_result = entry
        return entry

    def close(self) -> None:
        self._workspace.cleanup()
