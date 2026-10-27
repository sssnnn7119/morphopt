"""Interface labels for finite-element contour fields."""

from __future__ import annotations

from ...postprocess import ContourField
from ..i18n import localization, tr


def contour_label_key(field: ContourField) -> str:
    """Map a physical field component to its localized interface label."""
    if field.source == "displacement":
        return (
            "ui.fea.contour_displacement"
            if field.key == "U"
            else f"ui.fea.contour_{field.key}"
        )
    if field.key == "S_Mises":
        return "ui.fea.contour_mises"
    return {
        "stress": "ui.fea.contour_stress",
        "strain": "ui.fea.contour_strain",
        "energy": "ui.fea.contour_energy",
    }[field.source]


def field_label(key: str, description: str) -> str:
    """Translate built-in fields and use the provider description for extensions."""
    return _translated_or(f"ui.fea.field_{key}", description)


def export_format_label(key: str) -> str:
    """Produce a file dialog filter for a registered result format."""
    return _translated_or(f"ui.files.{key}", f"{key.upper()} (*.{key})")


def _translated_or(key: str, fallback: str) -> str:
    if (
        key in localization.load_locale(localization.locale)
        or key in localization.load_locale(localization.fallback_locale)
    ):
        return tr(key)
    return fallback
