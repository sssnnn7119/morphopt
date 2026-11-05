"""Explicit objectives node types and their editable fields."""

from __future__ import annotations

from typing import ClassVar

from ....constants import CONSTANT
from ..base_nodes import ObjectiveTermNode
from ..fields import FieldSpec


_QUADRATIC_FIELDS = (
    FieldSpec(
        "memory_size", "ui.schema.fields.memory_size.label", "int",
        CONSTANT.KERNEL.UPDATER_OBJECTIVES.QUADRATIC_MEMORY_PAIRS, minimum=1,
        doc_key="ui.schema.fields.memory_size.help",
    ),
)


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
    gen: ClassVar[str] = "self.objectivefuncs.Sensitivity()"
    fields: ClassVar[tuple[FieldSpec, ...]] = ()


class QuadraticShapeDerivativeObjectiveNode(ShapeDerivativeObjectiveNode):
    """Historical quadratic shape objective, separate from ShapeDerivative."""

    type_name: ClassVar[str] = "QuadraticShapeDerivative"
    backend_class: ClassVar[str] = "QuadraticShapeDerivative"
    label_key: ClassVar[str] = "ui.schema.catalog.updater_objective.quadraticshapederivative.label"
    gen: ClassVar[str] = "self.objectivefuncs.QuadraticShapeDerivative(memory_size={memory_size})"
    memory_size: int
    fields: ClassVar[tuple[FieldSpec, ...]] = _QUADRATIC_FIELDS


class QuadraticSensitivityObjectiveNode(SensitivityObjectiveNode):
    """Historical quadratic material objective, separate from Sensitivity."""

    type_name: ClassVar[str] = "QuadraticSensitivity"
    backend_class: ClassVar[str] = "QuadraticSensitivity"
    label_key: ClassVar[str] = "ui.schema.catalog.updater_objective.quadraticsensitivity.label"
    gen: ClassVar[str] = "self.objectivefuncs.QuadraticSensitivity(memory_size={memory_size})"
    memory_size: int
    fields: ClassVar[tuple[FieldSpec, ...]] = _QUADRATIC_FIELDS


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
