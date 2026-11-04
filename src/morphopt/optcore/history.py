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
    """Store one ordinary dictionary per iteration, without a field schema."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    @property
    def iteration(self) -> int:
        return len(self.records)

    def initialize(self) -> None:
        self.records.clear()

    def append(self, **record: Any) -> None:
        """Append a complete iteration, copying tensors and arrays to plain values."""
        if not record:
            raise ValueError("A history record must contain at least one field.")
        self.records.append(self._plain(record))

    @staticmethod
    def _plain(value: Any) -> Any:
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
        """Write fields in registration order; JSON cells preserve nested values."""
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
        """Read the same records, optionally keeping only a completed prefix."""
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
