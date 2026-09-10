"""Numeric list parsing for the UI forms.

Coordinate / size lists are parsed as ``float``; index-like lists can opt into
keeping integers (``ints=True``).  Nested python literals (``[[..],[..]]``) are
kept.
"""

from __future__ import annotations

import ast
import re

from ..i18n import T

_FLOAT_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")

#: labels for degree-of-freedom check boxes (dof index -> short name)
DOF_LABELS = {0: "X", 1: "Y", 2: "Z", 3: "Rx", 4: "Ry", 5: "Rz"}
DOF_COUNT = 6

_CHOICE_LABELS = {
    ("obj_type", "auto"): ("自动", "Auto"),
    ("obj_type", "node"): ("节点", "Node"),
    ("obj_type", "element"): ("单元", "Element"),
    ("obj_type", "part"): ("部件", "Part"),
}


def display_choice(key: str, value) -> str:
    """Return a localized label while retaining the backend choice value."""
    labels = _CHOICE_LABELS.get((key, str(value)))
    return T(*labels) if labels else str(value)


def combo_value(combo) -> object:
    """Read a combo's backend value, or custom text when it was edited."""
    index = combo.currentIndex()
    if index >= 0 and combo.currentText() == combo.itemText(index):
        return combo.itemData(index)
    return combo.currentText()


def _normalize(v, ints: bool = False):
    """Convert values to float, or keep integral as int when ``ints``."""
    if isinstance(v, float) and ints and v.is_integer():
        return int(v)
    if isinstance(v, int) and not ints:
        return float(v)
    if isinstance(v, list):
        return [_normalize(x, ints) for x in v]
    return v


def parse_vec_text(text: str, ints: bool = False):
    """Parse '0,1,2', '0 1 2' or '[1,[1]]' into numbers.

    ``ints=False`` (default) -> floats (coordinates etc.).
    ``ints=True`` -> keep integers as int (index lists).
    """
    text = text.strip()
    if not text:
        return []
    try:
        val = ast.literal_eval(text)
        if isinstance(val, list):
            return _normalize(val, ints)
    except (ValueError, SyntaxError):
        pass
    nums = [m for m in _FLOAT_RE.findall(text)]
    out = []
    for m in nums:
        f = float(m)
        out.append(int(f) if ints and f.is_integer() else f)
    return out


def parse_mat(text: str):
    """Parse a python-literal matrix like [[1,2],[3,4]] (or flat numbers)."""
    text = text.strip()
    if not text:
        return []
    try:
        return _normalize(ast.literal_eval(text))
    except (ValueError, SyntaxError):
        flat = parse_vec_text(text)
        return [[flat[2 * i], flat[2 * i + 1]] for i in range(len(flat) // 2)]
