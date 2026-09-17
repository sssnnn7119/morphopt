"""Material-to-element assignment record."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ElementMaterialAssignment:
    """Immutable mapping from a Part element family to a material name."""
    part_name: str
    element_name: str
    material_name: str
