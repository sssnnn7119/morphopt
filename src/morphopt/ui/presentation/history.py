"""History records projected into table columns, independently of Qt."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from ..i18n import tr


@dataclass(frozen=True)
class HistoryTable:
    headers: list[str]
    rows: list[list[str | None]]
    objectives: list[float]


def _metric_count(metrics) -> int:
    if metrics is None or metrics.size == 0:
        return 0
    return metrics.shape[-1] if metrics.ndim > 1 else 1


def _deformation_columns(deformation) -> tuple[list[str], object]:
    if deformation is None or deformation.size == 0:
        return [], None
    if deformation.ndim == 2:
        return ([tr('ui.widgets.observation_pages.u0_value', value_0=index)
                 for index in range(deformation.shape[1])],
                deformation)
    if deformation.ndim == 3:
        tasks, dimensions = deformation.shape[1:]
        labels = [tr('ui.widgets.observation_pages.u_value_value', value_0=task, value_1=dimension)
                  for task in range(tasks)
                  for dimension in range(dimensions)]
        return labels, deformation.reshape(deformation.shape[0], -1)
    return [], None


def _row_values(row_index, objective, metrics, metric_count, times,
                elements, nodes, flat_deformation) -> list[str | None]:
    values: list[str | None] = [str(row_index + 1), f"{objective:.6f}"]
    for metric_index in range(metric_count):
        if metrics is None or row_index >= len(metrics):
            values.append(None)
            continue
        metric_row = metrics[row_index]
        metric_value = (metric_row[metric_index] if np.ndim(metric_row)
                        else metric_row)
        values.append(f"{metric_value:.6f}")
    if times is not None and row_index < len(times):
        values.extend(f"{value:.2f}" for value in times[row_index][:4])
        values.extend([None] * max(0, 4 - len(times[row_index][:4])))
    else:
        values.extend([None] * 4)
    values.append(str(elements[row_index]) if elements is not None and row_index < len(elements)
                  else None)
    values.append(str(nodes[row_index]) if nodes is not None and row_index < len(nodes)
                  else None)
    if flat_deformation is not None and row_index < len(flat_deformation):
        values.extend(f"{value:.4e}" for value in flat_deformation[row_index])
    return values


def history_table(history) -> HistoryTable:
    objectives = list(history.history_objective)
    metrics = history.history_metrics
    count = _metric_count(metrics)
    deformation_labels, flat = _deformation_columns(history.history_deformation)
    headers = (
        [tr('ui.widgets.observation_pages.iteration'), tr('ui.widgets.observation_pages.objective')]
        + [tr('ui.widgets.observation_pages.metric_value', value_0=index) for index in range(count)]
        + [tr('ui.widgets.observation_pages.init'), tr('ui.widgets.observation_pages.fea'), tr('ui.widgets.observation_pages.sens'), tr('ui.widgets.observation_pages.update'), tr('ui.widgets.observation_pages.elements'), tr('ui.widgets.observation_pages.nodes')]
        + deformation_labels
    )
    rows = [_row_values(
        index,
        objective,
        metrics,
        count,
        history.history_time,
        history.history_num_elements,
        history.history_num_nodes,
        flat,
    ) for index, objective in enumerate(objectives)]
    return HistoryTable(headers, rows, objectives)
