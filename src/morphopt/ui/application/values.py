"""Numeric text parsing shared by forms and non-Qt definition tools."""
from __future__ import annotations
import ast
import re
_FLOAT_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")

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


def field_text(value) -> str:
    """Display numeric containers without flattening matrix structure."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        if any(isinstance(item, (list, tuple)) for item in value):
            return repr(value)
        return ", ".join(map(str, value))
    return str(value)


def parse_field(text: str, spec: dict, helper_names=()):
    """One conversion policy for node fields and updater parameter dictionaries."""
    kind = spec["type"]
    stripped = text.strip()
    if kind in {"int", "float"}:
        try:
            return (int if kind == "int" else float)(text)
        except ValueError:
            return stripped if kind == "int" else text
    if kind == "mat" or kind.startswith("vec"):
        if stripped in helper_names:
            return stripped
        try:
            expression = ast.parse(stripped, mode="eval")
        except SyntaxError:
            expression = None
        if expression is not None and any(isinstance(node, ast.Name) for node in ast.walk(expression)):
            return stripped
        return parse_mat(text) if kind == "mat" else parse_vec_text(text, ints=bool(spec.get("ints")))
    return text
