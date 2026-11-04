"""Portable names shared by result creation and UI result discovery."""

import re


def sanitize_name(name: str) -> str:
    """Return a single filename component valid on Windows and Linux."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(" .")
    if not name:
        return "problem"
    reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
                *(f"{prefix}{index}" for prefix in ("COM", "LPT") for index in "123456789¹²³")}
    if name.split(".")[0].rstrip(" ").upper() in reserved:
        name = "_" + name
    return name
