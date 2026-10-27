"""One-file exporters, independent of field evaluation and Qt."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile
from typing import Any, Protocol

import numpy as np

from .context import cpu_torch_defaults, evaluation_defaults
from .fields import (
    RESULT_FIELDS,
    FieldContext,
    ResultLocation,
    ResultTable,
    combined_table,
)


class ResultExporter(Protocol):
    """Writer for a table of one finite-element record location."""

    def write(
        self, table: ResultTable, path: Path, metadata: dict[str, Any]
    ) -> None: ...


class CSVExporter:
    def write(self, table: ResultTable, path: Path, metadata: dict[str, Any]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(table.columns)
            writer.writerows(table.rows)


class NPZExporter:
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


EXPORTERS: dict[str, ResultExporter] = {"csv": CSVExporter(), "npz": NPZExporter()}


def export_saved_results(
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
        return export_results(
            controller,
            result,
            path,
            location=location,
            fields=fields,
            format=format,
            metadata=metadata,
            overwrite=overwrite,
        )


def export_results(
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
    writer = EXPORTERS[format or destination.suffix.lstrip(".").lower()]
    if not result.converged:
        raise ValueError("Only converged results can be exported.")
    if result.model_hash != controller.get_model_hash():
        raise ValueError("The result does not belong to this finite-element model.")
    if destination.exists() and not overwrite:
        raise FileExistsError(destination)
    context = FieldContext(controller, result)
    with evaluation_defaults(result):
        keys = (
            tuple(dict.fromkeys(fields))
            if fields is not None
            else tuple(
                key for key, provider in RESULT_FIELDS.items()
                if provider.location is location and provider.available(context)
            )
        )
        if not keys:
            raise ValueError("Choose at least one result field.")
        providers = tuple(RESULT_FIELDS[key] for key in keys)
        if any(provider.location is not location for provider in providers):
            raise ValueError("Choose fields from one result location only.")
        # A model with no usable Gauss points has no integration-point fields to export.
        providers = tuple(provider for provider in providers if provider.available(context))
        if not providers:
            raise ValueError("The selected model has no data for these physical quantities.")
        table = combined_table(context, location, providers)
        description = {
            "schema_version": 2,
            "location": location.value,
            "units": "model consistent units",
            "index_base": 1,
            "coordinate_frame": "global assembly axes",
            "model_hash": result.model_hash,
            "source": metadata or {},
            "fields": [
                {"key": provider.key, "description": provider.description}
                for provider in providers
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
