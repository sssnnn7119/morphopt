"""Versioned optimization history stored in the run ``logs`` directory."""

from __future__ import annotations

import csv
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path

from morphopt.logging import get_logger

from .protocols import JsonObject, JsonValue

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class HistoryRecord:
    """Immutable summary of one completed outer iteration.

    Tensor values are converted to detached Python scalars before a record is
    created, which keeps the log independent of a live autograd graph.
    """

    iteration: int
    objective: float
    metrics_by_case: tuple[tuple[float, ...], ...] = ()
    phase_times: Mapping[str, float] = field(default_factory=dict)
    num_elements: int = 0
    num_nodes: int = 0
    maximum_deformation: float = 0.0
    converged_by_case: tuple[bool, ...] = ()
    result_path: Path | None = None
    updater_summary: Mapping[str, JsonValue] = field(default_factory=dict)


class History:
    """Store and restore :class:`HistoryRecord` objects.

    ``logs/history.json`` is the structured source and ``logs/history.csv`` is
    its flat reporting view.  Checkpoint directories contain only resumable
    model state; history is never copied into a checkpoint.
    """

    _SCHEMA_VERSION = 1

    def __init__(
        self, result_root: str | Path = ".results", metric_names: tuple[str, ...] = ()
    ) -> None:
        """Create an empty history for one result directory."""
        self._result_root = Path(result_root)
        """Directory containing history and result artifacts."""
        self._metric_names = tuple(metric_names)
        """Ordered names for metrics stored in records."""
        self._records: list[HistoryRecord] = []
        """In-memory records for the active run."""
        self._record_by_iteration: dict[int, HistoryRecord] = {}
        """Fast lookup by iteration number."""
        self._initialized = False
        """History lifecycle initialization state."""

    @property
    def result_root(self) -> Path:
        """Return the history result root."""
        return self._result_root

    @property
    def metric_names(self) -> tuple[str, ...]:
        """Return display metric names in stable order."""
        return self._metric_names

    @property
    def log_directory(self) -> Path:
        """Return the directory containing the structured history logs."""
        return self._result_root / "logs"

    def initialize(self) -> None:
        """Clear records and mark the history ready for a new run."""
        self._records.clear()
        self._record_by_iteration.clear()
        self._initialized = True

    def add_record(self, record: HistoryRecord) -> None:
        """Validate and insert a record, replacing an equal iteration."""
        self._validate_record(record)
        if not self._initialized:
            self.initialize()
        self._record_by_iteration[record.iteration] = record
        self._records = [
            self._record_by_iteration[key] for key in sorted(self._record_by_iteration)
        ]

    def get_records(self) -> tuple[HistoryRecord, ...]:
        """Return records in ascending iteration order."""
        return tuple(self._records)

    def get_record(self, iteration: int) -> HistoryRecord:
        """Return one record or raise ``KeyError`` when it is absent."""
        try:
            return self._record_by_iteration[int(iteration)]
        except KeyError as exc:
            raise KeyError(f"No history record for iteration {iteration}") from exc

    def get_current_iteration(self) -> int | None:
        """Return the latest completed iteration, if any."""
        return self._records[-1].iteration if self._records else None

    def get_series(self, name: str, case_index: int | None = None) -> tuple[float, ...]:
        """Return a scalar history series for plotting or convergence checks."""
        values: list[float] = []
        for record in self._records:
            if name == "objective":
                values.append(float(record.objective))
            elif name == "maximum_deformation":
                values.append(float(record.maximum_deformation))
            elif name == "num_elements":
                values.append(float(record.num_elements))
            elif name == "num_nodes":
                values.append(float(record.num_nodes))
            elif name == "metric":
                if case_index is None:
                    raise ValueError("case_index is required for metric series")
                values.append(float(record.metrics_by_case[case_index][0]))
            elif name in self._metric_names:
                if case_index is None:
                    raise ValueError("case_index is required for metric series")
                metric_index = self._metric_names.index(name)
                values.append(float(record.metrics_by_case[case_index][metric_index]))
            else:
                raise KeyError(f"Unknown history series: {name}")
        return tuple(values)

    def get_result_paths(self) -> tuple[Path, ...]:
        """Return result directories recorded by completed iterations."""
        return tuple(
            record.result_path
            for record in self._records
            if record.result_path is not None
        )

    def save(
        self, folder_path: str | Path | None = None, iteration: int | None = None
    ) -> None:
        """Write the current history snapshot below ``logs``.

        ``folder_path`` names the run root.  Passing the ``logs`` directory
        itself is also accepted for small tools that operate directly on log
        files; no other copy is written.
        """
        folder = self._resolve_log_directory(folder_path)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / "history.json"
        payload = {
            "schema_version": self._SCHEMA_VERSION,
            "metric_names": list(self._metric_names),
            "current_iteration": self.get_current_iteration(),
            "records": [self._serialize_record(record) for record in self._records],
        }
        self._write_atomic(target, payload)
        self._write_csv_atomic(folder / "history.csv")

    def load(self, folder_path: str | Path, iteration: int | None = None) -> None:
        """Parse records from a run's ``logs/history.json`` file."""
        target = self._resolve_log_directory(folder_path) / "history.json"
        if not target.exists():
            raise FileNotFoundError(target)
        payload = json.loads(target.read_text(encoding="utf-8"))
        if int(payload.get("schema_version", 0)) != self._SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported history schema: {payload.get('schema_version')}"
            )
        self._metric_names = tuple(payload.get("metric_names", ()))
        self.initialize()
        for item in payload.get("records", ()):
            record = self._deserialize_record(item)
            if iteration is None or record.iteration <= iteration:
                self.add_record(record)

    def _validate_record(self, record: HistoryRecord) -> None:
        if record.iteration < 0:
            raise ValueError("History iteration must be non-negative")
        if not isinstance(record.objective, (int, float)):
            raise TypeError("History objective must be numeric")

    def _resolve_log_directory(self, folder_path: str | Path | None) -> Path:
        """Normalize a run root or explicit ``logs`` path to one directory."""
        folder = self._result_root if folder_path is None else Path(folder_path)
        return folder if folder.name == "logs" else folder / "logs"

    def _serialize_record(self, record: HistoryRecord) -> JsonObject:
        data = asdict(record)
        data["result_path"] = (
            str(record.result_path) if record.result_path is not None else None
        )
        data["metrics_by_case"] = [list(values) for values in record.metrics_by_case]
        data["converged_by_case"] = list(record.converged_by_case)
        return data

    def _deserialize_record(self, data: Mapping[str, JsonValue]) -> HistoryRecord:
        return HistoryRecord(
            iteration=int(data["iteration"]),
            objective=float(data["objective"]),
            metrics_by_case=tuple(
                tuple(float(value) for value in values)
                for values in data.get("metrics_by_case", ())
            ),
            phase_times={
                str(key): float(value)
                for key, value in data.get("phase_times", {}).items()
            },
            num_elements=int(data.get("num_elements", 0)),
            num_nodes=int(data.get("num_nodes", 0)),
            maximum_deformation=float(data.get("maximum_deformation", 0.0)),
            converged_by_case=tuple(
                bool(value) for value in data.get("converged_by_case", ())
            ),
            result_path=Path(data["result_path"]) if data.get("result_path") else None,
            updater_summary=data.get("updater_summary", {}),
        )

    def _write_atomic(self, target: Path, payload: Mapping[str, JsonValue]) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", dir=target.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, target)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise

    def _write_csv_atomic(self, target: Path) -> None:
        """Write a flat, spreadsheet-friendly history snapshot atomically."""
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", dir=target.parent
        )
        base_fieldnames = (
            "iteration",
            "objective",
            "metrics_by_case",
            "phase_times",
            "num_elements",
            "num_nodes",
            "maximum_deformation",
            "converged_by_case",
            "result_path",
            "updater_summary",
        )
        case_count = max(
            (len(record.metrics_by_case) for record in self._records), default=0
        )
        metric_fieldnames = tuple(
            f"case_{case_index}_{str(metric_name).replace(' ', '_')}"
            for case_index in range(case_count)
            for metric_name in self._metric_names
        )
        fieldnames = (*base_fieldnames, *metric_fieldnames)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fieldnames)
                writer.writeheader()
                for record in self._records:
                    row = {
                        "iteration": record.iteration,
                        "objective": record.objective,
                        "metrics_by_case": json.dumps(
                            record.metrics_by_case, ensure_ascii=False
                        ),
                        "phase_times": json.dumps(
                            dict(record.phase_times), ensure_ascii=False
                        ),
                        "num_elements": record.num_elements,
                        "num_nodes": record.num_nodes,
                        "maximum_deformation": record.maximum_deformation,
                        "converged_by_case": json.dumps(record.converged_by_case),
                        "result_path": str(record.result_path)
                        if record.result_path is not None
                        else "",
                        "updater_summary": json.dumps(
                            dict(record.updater_summary), ensure_ascii=False
                        ),
                    }
                    for case_index, metrics in enumerate(record.metrics_by_case):
                        for metric_index, value in enumerate(metrics):
                            if metric_index < len(self._metric_names):
                                metric_name = str(
                                    self._metric_names[metric_index]
                                ).replace(" ", "_")
                                row[f"case_{case_index}_{metric_name}"] = value
                    writer.writerow(row)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, target)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
