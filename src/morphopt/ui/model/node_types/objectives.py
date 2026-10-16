"""Explicit objectives node types and their editable fields."""

from __future__ import annotations

from typing import ClassVar

from ....constants import CONSTANT
from ..base_nodes import ObjectiveTermNode
from ..fields import FieldSpec


class ShapeDerivativeObjectiveNode(ObjectiveTermNode):
    """UI definition of ShapeDerivative."""

    type_name: ClassVar[str] = "ShapeDerivative"
    backend_class: ClassVar[str] = "ShapeDerivative"
    label_key: ClassVar[str] = (
        "ui.schema.catalog.updater_objective.shapederivative.label"
    )
    group: ClassVar[str] = "geometry"
    gen: ClassVar[str] = "self.objectivefuncs.ShapeDerivative()"
    fields: ClassVar[tuple[FieldSpec, ...]] = ()


class SensitivityObjectiveNode(ObjectiveTermNode):
    """UI definition of Sensitivity."""

    type_name: ClassVar[str] = "Sensitivity"
    backend_class: ClassVar[str] = "Sensitivity"
    label_key: ClassVar[str] = "ui.schema.catalog.updater_objective.sensitivity.label"
    group: ClassVar[str] = "materials"
    gen: ClassVar[str] = (
        "self.objectivefuncs.Sensitivity(normalize_gradient={normalize_gradient})"
    )
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.UPDATER_OBJECTIVES.SENSITIVITY
    normalize_gradient: bool
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "normalize_gradient",
            "ui.schema.fields.normalize_gradient.label.normalize_gradient",
            "bool",
            Defaults.NORMALIZE_GRADIENT.DEFAULT,
            doc_key="ui.schema.fields.normalize_gradient.help.text",
        ),
    )


class DensityFieldMinimizeObjectiveNode(ObjectiveTermNode):
    """UI definition of DensityFieldMinimize."""

    type_name: ClassVar[str] = "DensityFieldMinimize"
    backend_class: ClassVar[str] = "DensityFieldMinimize"
    label_key: ClassVar[str] = (
        "ui.schema.catalog.updater_objective.densityfieldminimize.label"
    )
    group: ClassVar[str] = "materials"
    gen: ClassVar[str] = "self.objectivefuncs.DensityFieldMinimize(scale={scale})"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.UPDATER_OBJECTIVES.DENSITYFIELDMINIMIZE
    scale: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "scale",
            "ui.schema.fields.scale.label.scale",
            "float",
            Defaults.SCALE.DEFAULT,
            doc_key="ui.schema.fields.scale.help.text",
        ),
    )
