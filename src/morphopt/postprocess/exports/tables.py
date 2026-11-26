"""Serialize selected finite-element fields using the registered table writers."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol

import numpy as np

from .._runtime import cpu_torch_defaults
from ..archive import load_solved_model
from ..fields import RESULT_FIELDS, FiniteElementResults, ResultLocation, ResultTable


class TableWriter(Protocol):
    """Writer for a table of one finite-element record location."""

    def write(
        self, table: ResultTable, path: Path, metadata: dict[str, Any]
    ) -> None:
        """Write one physical-field table using the concrete output format.

        Args:
            table (ResultTable): Result table containing column definitions and a row iterator.
            path (Path): Filesystem path read, restored, or written by this operation.
            metadata (dict[str, Any]): Asset or result provenance stored with the exported data.
        """
        ...


class CSVWriter:
    """Write a result table as UTF-8 CSV, retaining the declared column order."""
    def write(self, table: ResultTable, path: Path, metadata: dict[str, Any]) -> None:
        """Write table columns and rows as UTF-8 CSV.

        The shared metadata argument is accepted by the writer interface; CSV stores the table
        itself.

        Args:
            table (ResultTable): Result table containing column definitions and a row iterator.
            path (Path): Filesystem path read, restored, or written by this operation.
            metadata (dict[str, Any]): Asset or result provenance stored with the exported data.
        """
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(table.columns)
            writer.writerows(table.rows)


class NPZWriter:
    """Write a result table and its provenance as a compressed NumPy archive."""
    def write(self, table: ResultTable, path: Path, metadata: dict[str, Any]) -> None:
        """Write each table column and JSON provenance into a compressed NumPy archive.

        Args:
            table (ResultTable): Result table containing column definitions and a row iterator.
            path (Path): Filesystem path read, restored, or written by this operation.
            metadata (dict[str, Any]): Asset or result provenance stored with the exported data.
        """
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
    """Load a saved model and solution, then export selected physical fields.

    Args:
        model_path (str | Path): Path to the saved TorchFEA finite-element model.
        result_path (str | Path): Path to the saved TorchFEA solution.
        path (str | Path): Filesystem path read, restored, or written by this operation.
        location (ResultLocation | str): Result record location: nodes, elements, reference
            points, or integration points.
        fields (tuple[str, ...] | list[str] | None): Requested field keys; None selects the
            available defaults for the record location.
        format (str | None): Output table format; None selects the writer from the filename
            suffix.
        metadata (dict[str, Any] | None): Asset or result provenance stored with the exported
            data.
        overwrite (bool): Allow replacing an existing output file when True.

    Returns:
        Path: Destination of the written physical-field table.
    """
    with cpu_torch_defaults():
        controller, result = load_solved_model(model_path, result_path)
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
    """Export one record location, merging all selected quantities into columns.

    Args:
        controller (Any): Controller providing the current model and execution state.
        result (Any): Finite-element solution or completed operation result.
        path (str | Path): Filesystem path read, restored, or written by this operation.
        location (ResultLocation | str): Result record location: nodes, elements, reference
            points, or integration points.
        fields (tuple[str, ...] | list[str] | None): Requested field keys; None selects the
            available defaults for the record location.
        format (str | None): Output table format; None selects the writer from the filename
            suffix.
        metadata (dict[str, Any] | None): Asset or result provenance stored with the exported
            data.
        overwrite (bool): Allow replacing an existing output file when True.

    Returns:
        Path: Destination of the complete CSV or NPZ table published after field extraction.
    """
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
    with TemporaryDirectory(dir=destination.parent) as directory:
        staged = Path(directory) / destination.name
        writer.write(table, staged, description)
        if overwrite:
            staged.replace(destination)
        else:
            with staged.open("rb") as source:
                output = destination.open("xb")
                try:
                    with output:
                        shutil.copyfileobj(source, output)
                except BaseException:
                    destination.unlink(missing_ok=True)
                    raise
    return destination
