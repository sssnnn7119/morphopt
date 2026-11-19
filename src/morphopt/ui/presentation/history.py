"""Project ordinary iteration records into table cells and numeric curves."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from numbers import Real
from typing import Any

from ...optcore.history import History
from ..i18n import tr


@dataclass(frozen=True)
class HistoryTable:
    """Provide localized history headers, formatted table rows, and numeric plotting series."""
    headers: list[str]
    rows: list[list[str | None]]
    curves: list[tuple[str, list[float]]]


def _flatten(value: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _flatten(item, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _flatten(item, (*path, str(index)))
    else:
        yield path, value


def _title(path: tuple[str, ...]) -> str:
    labels = {
        ("objective",): "objective",
        ("time", "init"): "init",
        ("time", "fea"): "fea",
        ("time", "sens"): "sens",
        ("time", "update"): "update",
        ("num_elements",): "elements",
        ("num_nodes",): "nodes",
    }
    if path[0] == "metrics" and len(path) > 1:
        return tr("ui.widgets.observation_pages.metric_value", value_0=".".join(path[1:]))
    if path[0] == "optimizers" and len(path) > 2:
        fields = {
            ("iterations",): "inner_iterations",
            ("solves",): "inner_solves",
            ("update_strategy_state", "tolerance"): "tolerance",
        }
        field = path[2:]
        if field in fields:
            title = tr(f"ui.history.{fields[field]}")
        elif field[0] == "constraint_weights" and len(field) == 2:
            title = tr("ui.history.penalty_field", penalty=field[1], field=tr("ui.history.weight"))
        elif field[:2] == ("update_strategy_state", "penalties") and len(field) == 4:
            label = (
                tr(f"ui.history.{field[3]}")
                if field[3] in {"violation", "peak_z"} else field[3]
            )
            title = tr("ui.history.penalty_field", penalty=field[2], field=label)
        else:
            title = ".".join(field)
        return tr("ui.history.optimizer_field", updater=path[1], field=title)
    if path in labels:
        return tr(f"ui.widgets.observation_pages.{labels[path]}")
    return ".".join(path)


def history_table(history: History) -> HistoryTable:
    """Return history table.

    Args:
        history (History): Iteration records supplying the table, curves, or result selection.

    Returns:
        HistoryTable: History table.
    """
    cells = [dict(_flatten(record)) for record in history.records]
    paths = list(dict.fromkeys(path for row in cells for path in row if path != ("iteration",)))
    titles = [_title(path) for path in paths]
    headers = [tr("ui.widgets.observation_pages.iteration"), *titles]
    rows = []
    for index, row in enumerate(cells, 1):
        values: list[str | None] = [str(history.records[index - 1].get("iteration", index))]
        for path in paths:
            value = row.get(path)
            values.append(
                f"{value:.6g}" if isinstance(value, Real)
                else str(value) if value is not None else None
            )
        rows.append(values)
    curves = []
    for path, title in zip(paths, titles):
        values = [row.get(path) for row in cells]
        if any(isinstance(value, Real) for value in values) and all(
            value is None or isinstance(value, Real) for value in values
        ):
            curves.append((title, [float(value) if value is not None else float("nan") for value in values]))
    return HistoryTable(headers, rows, curves)
