"""Immutable field declarations shared by nodes and parameter editors."""
from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


def _mutable_value(value: object) -> Any:
    if isinstance(value, tuple):
        return [_mutable_value(item) for item in value]
    return deepcopy(value)


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """Static UI metadata; every node receives its own default value."""

    key: str
    label_key: str
    type: str
    default: object = ""
    doc_key: str = ""
    choices: tuple[object, ...] = ()
    size: int = 6
    minimum: float | None = None
    maximum: float | None = None
    ints: bool = False
    read_only: bool = False
    hidden: bool = False
    editable: bool = True
    components: tuple[str, ...] = ()
    item_type: str = "float"

    def new_default(self) -> Any:
        """Return new default.

        Returns:
            Any: New default.
        """
        return _mutable_value(self.default)


def field_defaults(fields: Iterable[FieldSpec]) -> dict[str, Any]:
    """Return field defaults.

    Args:
        fields (Iterable[FieldSpec]): Requested field keys; None selects the available defaults
            for the record location.

    Returns:
        dict[str, Any]: Field defaults.
    """
    return {field.key: field.new_default() for field in fields}
