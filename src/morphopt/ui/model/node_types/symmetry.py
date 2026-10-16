"""Explicit symmetry node types and their editable fields."""

from __future__ import annotations

from typing import ClassVar

from ....constants import CONSTANT
from ..base_nodes import SurfaceConstraintNode
from ..fields import FieldSpec


class BspMirrorConstraintNode(SurfaceConstraintNode):
    """UI definition of BspMirrorConstraint."""

    type_name: ClassVar[str] = "BspMirror"
    backend_class: ClassVar[str] = "BspMirrorConstraint"
    label_key: ClassVar[str] = "ui.schema.catalog.symmetry_constraint.bspmirror.label"
    factory: ClassVar[str] = "BSP"
    method: ClassVar[str] = "mirror"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.SURFACE_CONSTRAINTS.BSPMIRROR
    plane: str
    offset: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "plane",
            "ui.schema.fields.plane.label.text",
            "combo",
            Defaults.PLANE.DEFAULT,
            doc_key="ui.schema.fields.plane.help.xz_y_0_xy_z_offset",
            choices=Defaults.PLANE.CHOICES,
        ),
        FieldSpec(
            "offset",
            "ui.schema.fields.offset.label.text",
            "float",
            Defaults.OFFSET.DEFAULT,
            doc_key="ui.schema.fields.offset.help.xy_xz_0",
        ),
    )


class CPGEOMirrorConstraintNode(SurfaceConstraintNode):
    """UI definition of CPGEOMirrorConstraint."""

    type_name: ClassVar[str] = "CPGEOMirror"
    backend_class: ClassVar[str] = "CPGEOMirrorConstraint"
    label_key: ClassVar[str] = "ui.schema.catalog.symmetry_constraint.cpgeomirror.label"
    factory: ClassVar[str] = "CPGEO"
    method: ClassVar[str] = "mirror"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.SURFACE_CONSTRAINTS.CPGEOMIRROR
    plane: str
    offset: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "plane",
            "ui.schema.fields.plane.label.text",
            "combo",
            Defaults.PLANE.DEFAULT,
            doc_key="ui.schema.fields.plane.help.offset",
            choices=Defaults.PLANE.CHOICES,
        ),
        FieldSpec(
            "offset",
            "ui.schema.fields.offset.label.text",
            "float",
            Defaults.OFFSET.DEFAULT,
        ),
    )


class CPGEORotationConstraintNode(SurfaceConstraintNode):
    """UI definition of CPGEORotationalSymmetryConstraint."""

    type_name: ClassVar[str] = "CPGEORotation"
    backend_class: ClassVar[str] = "CPGEORotationalSymmetryConstraint"
    label_key: ClassVar[str] = (
        "ui.schema.catalog.symmetry_constraint.cpgeorotation.label"
    )
    factory: ClassVar[str] = "CPGEO"
    method: ClassVar[str] = "rotate"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.SURFACE_CONSTRAINTS.CPGEOROTATION
    axis: str
    order: int | str
    center: list[float] | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "axis",
            "ui.schema.fields.axis.label.text",
            "combo",
            Defaults.AXIS.DEFAULT,
            doc_key="ui.schema.fields.axis.help.text",
            choices=Defaults.AXIS.CHOICES,
        ),
        FieldSpec(
            "order",
            "ui.schema.fields.order.label.text",
            "int",
            Defaults.ORDER.DEFAULT,
            minimum=Defaults.ORDER.MIN,
        ),
        FieldSpec(
            "center",
            "ui.schema.fields.center.label.text",
            "vec3",
            Defaults.CENTER.DEFAULT,
        ),
    )


class BspRelationConstraintNode(SurfaceConstraintNode):
    """UI definition of BspSurfaceRelationConstraint."""

    type_name: ClassVar[str] = "BspRelation"
    backend_class: ClassVar[str] = "BspSurfaceRelationConstraint"
    label_key: ClassVar[str] = "ui.schema.catalog.symmetry_constraint.bsprelation.label"
    factory: ClassVar[str] = "BSP"
    method: ClassVar[str] = "relate"
    related_surface: ClassVar[bool] = True
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.SURFACE_CONSTRAINTS.BSPRELATION
    pose: list[float] | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "pose",
            "ui.schema.fields.pose.label.tx_ty_tz_rx_ry_rz",
            "vec6",
            Defaults.POSE.DEFAULT,
        ),
    )


class CPGEORelationConstraintNode(SurfaceConstraintNode):
    """UI definition of CPGEOSurfaceRelationConstraint."""

    type_name: ClassVar[str] = "CPGEORelation"
    backend_class: ClassVar[str] = "CPGEOSurfaceRelationConstraint"
    label_key: ClassVar[str] = (
        "ui.schema.catalog.symmetry_constraint.cpgeorelation.label"
    )
    factory: ClassVar[str] = "CPGEO"
    method: ClassVar[str] = "relate"
    related_surface: ClassVar[bool] = True
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.SURFACE_CONSTRAINTS.CPGEORELATION
    pose: list[float] | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "pose",
            "ui.schema.fields.pose.label.tx_ty_tz_rx_ry_rz",
            "vec6",
            Defaults.POSE.DEFAULT,
        ),
    )


class CustomSurfaceConstraintNode(SurfaceConstraintNode):
    """UI definition of Custom."""

    type_name: ClassVar[str] = "Custom"
    backend_class: ClassVar[str] = ""
    label_key: ClassVar[str] = "ui.schema.catalog.symmetry_constraint.custom.label"
    factory: ClassVar[str | None] = None
    method: ClassVar[str | None] = None
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.SURFACE_CONSTRAINTS.CUSTOM
    code: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "code",
            "ui.schema.fields.code.label.constraint_function_body",
            "code",
            Defaults.CODE.DEFAULT,
            doc_key="ui.schema.fields.code.help.custom_code_executed_by_apply_surface_constraints",
        ),
    )
