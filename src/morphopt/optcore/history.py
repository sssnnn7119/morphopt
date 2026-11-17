"""Iteration records with generic CSV persistence."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch

from .protocal import ProtocalInitializable, ProtocalSavable


class History(ProtocalInitializable, ProtocalSavable):
    """Store one dictionary per completed iteration without a fixed field schema.

    append() copies tensors and NumPy arrays to plain Python values. CSV persistence retains
    nested dictionaries and lists as JSON cells. Providers own their field names; the history
    container does not evaluate objectives or modify optimization state.
    """

    def __init__(self) -> None:
        """Create an empty collection of completed iteration records."""
        self.records: list[dict[str, Any]] = []

    @property
    def iteration(self) -> int:
        """Return the number of completed iteration records currently loaded.

        Returns:
            int: Record count; zero represents an empty history.
        """
        return len(self.records)

    def initialize(self) -> None:
        """Clear all loaded records before a new run or an archive restore."""
        self.records.clear()

    def append(self, **record: Any) -> None:
        """Append a complete iteration, copying tensors and arrays to plain values.

        Args:
            **record: Named observations for one completed iteration. Nested dictionaries and
                sequences are accepted; tensors and arrays are copied to plain Python values.

        Raises:
            ValueError: No observations are supplied.
        """
        if not record:
            raise ValueError("A history record must contain at least one field.")
        self.records.append(self._plain(record))

    @staticmethod
    def _plain(value: Any) -> Any:
        """Recursively detach numerical values into JSON-compatible record data.

        Args:
            value (Any): Observation or nested container to copy into the history record.

        Returns:
            Any: Plain scalar, list, or dictionary preserving the observation structure. Tensor
                storage and autograd graphs are not retained.
        """
        if isinstance(value, torch.Tensor):
            return value.detach().cpu().tolist()
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, dict):
            return {key: History._plain(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [History._plain(item) for item in value]
        return value

    def save(self, foldpath: str, iteration: int | None = None) -> None:
        """Write fields in registration order; JSON cells preserve nested values.

        Args:
            foldpath (str): Existing log directory receiving history_record.csv.
            iteration (int | None): Number of completed records to write; None writes all records.
        """
        records = self.records if iteration is None else self.records[:iteration]
        fields = list(dict.fromkeys(key for record in records for key in record))
        with (Path(foldpath) / "history_record.csv").open(
            "w", encoding="utf-8", newline=""
        ) as stream:
            writer = csv.writer(stream)
            writer.writerow(fields)
            for record in records:
                writer.writerow([
                    json.dumps(record[key], ensure_ascii=False) if key in record else ""
                    for key in fields
                ])

    def load(self, foldpath: str, iteration: int | None = None) -> None:
        """Read the same records, optionally keeping only a completed prefix.

        Args:
            foldpath (str): Log directory containing history_record.csv.
            iteration (int | None): Number of completed records to retain; None loads the complete
                saved history.
        """
        self.initialize()
        path = Path(foldpath) / "history_record.csv"
        if not path.is_file():
            return
        with path.open(encoding="utf-8", newline="") as stream:
            self.records = [
                {key: json.loads(value) for key, value in row.items()
                 if value != ""}
                for row in csv.DictReader(stream)
            ]
        if iteration is not None:
            self.records = self.records[:iteration]
