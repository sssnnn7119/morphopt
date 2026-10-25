"""Explicit cad node types and their editable fields."""

from __future__ import annotations

from typing import ClassVar

from ....constants import CONSTANT
from ..base_nodes import CADOperationNode
from ..fields import FieldSpec


class BoxOperationNode(CADOperationNode):
    """UI definition of Box."""

    type_name: ClassVar[str] = "Box"
    backend_class: ClassVar[str] = "Box"
    label_key: ClassVar[str] = "ui.schema.catalog.cad_operation.box.label"
    group: ClassVar[str] = "primitive"
    operation_kind: ClassVar[str] = "box"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.CAD_OPERATIONS.BOX
    x: float | str
    y: float | str
    z: float | str
    dx: float | str
    dy: float | str
    dz: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "x",
            "ui.schema.fields.x.label.x",
            "float",
            Defaults.X.DEFAULT,
        ),
        FieldSpec(
            "y",
            "ui.schema.fields.y.label.y",
            "float",
            Defaults.Y.DEFAULT,
        ),
        FieldSpec(
            "z",
            "ui.schema.fields.z.label.z",
            "float",
            Defaults.Z.DEFAULT,
        ),
        FieldSpec(
            "dx",
            "ui.schema.fields.dx.label.dx",
            "float",
            Defaults.DX.DEFAULT,
        ),
        FieldSpec(
            "dy",
            "ui.schema.fields.dy.label.dy",
            "float",
            Defaults.DY.DEFAULT,
        ),
        FieldSpec(
            "dz",
            "ui.schema.fields.dz.label.dz",
            "float",
            Defaults.DZ.DEFAULT,
        ),
    )


class WedgeOperationNode(BoxOperationNode):
    """UI definition of Wedge."""

    type_name: ClassVar[str] = "Wedge"
    backend_class: ClassVar[str] = "Wedge"
    label_key: ClassVar[str] = "ui.schema.catalog.cad_operation.wedge.label"
    group: ClassVar[str] = "primitive"
    operation_kind: ClassVar[str] = "wedge"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.CAD_OPERATIONS.WEDGE
    ltx: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        *BoxOperationNode.fields,
        FieldSpec(
            "ltx",
            "ui.schema.fields.ltx.label.ltx",
            "float",
            Defaults.LTX.DEFAULT,
        ),
    )


class CylinderOperationNode(CADOperationNode):
    """UI definition of Cylinder."""

    type_name: ClassVar[str] = "Cylinder"
    backend_class: ClassVar[str] = "Cylinder"
    label_key: ClassVar[str] = "ui.schema.catalog.cad_operation.cylinder.label"
    group: ClassVar[str] = "primitive"
    operation_kind: ClassVar[str] = "cylinder"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.CAD_OPERATIONS.CYLINDER
    x: float | str
    y: float | str
    z: float | str
    dx: float | str
    dy: float | str
    dz: float | str
    radius: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "x",
            "ui.schema.fields.x.label.x",
            "float",
            Defaults.X.DEFAULT,
        ),
        FieldSpec(
            "y",
            "ui.schema.fields.y.label.y",
            "float",
            Defaults.Y.DEFAULT,
        ),
        FieldSpec(
            "z",
            "ui.schema.fields.z.label.z",
            "float",
            Defaults.Z.DEFAULT,
        ),
        FieldSpec(
            "dx",
            "ui.schema.fields.dx.label.dx",
            "float",
            Defaults.DX.DEFAULT,
        ),
        FieldSpec(
            "dy",
            "ui.schema.fields.dy.label.dy",
            "float",
            Defaults.DY.DEFAULT,
        ),
        FieldSpec(
            "dz",
            "ui.schema.fields.dz.label.dz",
            "float",
            Defaults.DZ.DEFAULT,
        ),
        FieldSpec(
            "radius",
            "ui.schema.fields.radius.label.radius",
            "float",
            Defaults.RADIUS.DEFAULT,
            doc_key="ui.schema.fields.radius.help.text",
        ),
    )


class SphereOperationNode(CADOperationNode):
    """UI definition of Sphere."""

    type_name: ClassVar[str] = "Sphere"
    backend_class: ClassVar[str] = "Sphere"
    label_key: ClassVar[str] = "ui.schema.catalog.cad_operation.sphere.label"
    group: ClassVar[str] = "primitive"
    operation_kind: ClassVar[str] = "sphere"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.CAD_OPERATIONS.SPHERE
    x: float | str
    y: float | str
    z: float | str
    radius: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "x",
            "ui.schema.fields.x.label.x",
            "float",
            Defaults.X.DEFAULT,
        ),
        FieldSpec(
            "y",
            "ui.schema.fields.y.label.y",
            "float",
            Defaults.Y.DEFAULT,
        ),
        FieldSpec(
            "z",
            "ui.schema.fields.z.label.z",
            "float",
            Defaults.Z.DEFAULT,
        ),
        FieldSpec(
            "radius",
            "ui.schema.fields.radius.label.radius",
            "float",
            Defaults.RADIUS.DEFAULT,
            doc_key="ui.schema.fields.radius.help.text",
        ),
    )


class ConeOperationNode(CADOperationNode):
    """UI definition of Cone."""

    type_name: ClassVar[str] = "Cone"
    backend_class: ClassVar[str] = "Cone"
    label_key: ClassVar[str] = "ui.schema.catalog.cad_operation.cone.label"
    group: ClassVar[str] = "primitive"
    operation_kind: ClassVar[str] = "cone"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.CAD_OPERATIONS.CONE
    x: float | str
    y: float | str
    z: float | str
    dx: float | str
    dy: float | str
    dz: float | str
    radius1: float | str
    radius2: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "x",
            "ui.schema.fields.x.label.x",
            "float",
            Defaults.X.DEFAULT,
        ),
        FieldSpec(
            "y",
            "ui.schema.fields.y.label.y",
            "float",
            Defaults.Y.DEFAULT,
        ),
        FieldSpec(
            "z",
            "ui.schema.fields.z.label.z",
            "float",
            Defaults.Z.DEFAULT,
        ),
        FieldSpec(
            "dx",
            "ui.schema.fields.dx.label.dx",
            "float",
            Defaults.DX.DEFAULT,
        ),
        FieldSpec(
            "dy",
            "ui.schema.fields.dy.label.dy",
            "float",
            Defaults.DY.DEFAULT,
        ),
        FieldSpec(
            "dz",
            "ui.schema.fields.dz.label.dz",
            "float",
            Defaults.DZ.DEFAULT,
        ),
        FieldSpec(
            "radius1",
            "ui.schema.fields.radius1.label.radius1",
            "float",
            Defaults.RADIUS1.DEFAULT,
        ),
        FieldSpec(
            "radius2",
            "ui.schema.fields.radius2.label.radius2",
            "float",
            Defaults.RADIUS2.DEFAULT,
        ),
    )


class TorusOperationNode(CADOperationNode):
    """UI definition of Torus."""

    type_name: ClassVar[str] = "Torus"
    backend_class: ClassVar[str] = "Torus"
    label_key: ClassVar[str] = "ui.schema.catalog.cad_operation.torus.label"
    group: ClassVar[str] = "primitive"
    operation_kind: ClassVar[str] = "torus"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.CAD_OPERATIONS.TORUS
    x: float | str
    y: float | str
    z: float | str
    major_radius: float | str
    minor_radius: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "x",
            "ui.schema.fields.x.label.x",
            "float",
            Defaults.X.DEFAULT,
        ),
        FieldSpec(
            "y",
            "ui.schema.fields.y.label.y",
            "float",
            Defaults.Y.DEFAULT,
        ),
        FieldSpec(
            "z",
            "ui.schema.fields.z.label.z",
            "float",
            Defaults.Z.DEFAULT,
        ),
        FieldSpec(
            "major_radius",
            "ui.schema.fields.major_radius.label.major_radius",
            "float",
            Defaults.MAJOR_RADIUS.DEFAULT,
        ),
        FieldSpec(
            "minor_radius",
            "ui.schema.fields.minor_radius.label.minor_radius",
            "float",
            Defaults.MINOR_RADIUS.DEFAULT,
        ),
    )


class StepImportOperationNode(CADOperationNode):
    """UI definition of StepImport."""

    type_name: ClassVar[str] = "StepImport"
    backend_class: ClassVar[str] = "StepImport"
    label_key: ClassVar[str] = "ui.schema.catalog.cad_operation.stepimport.label"
    group: ClassVar[str] = "import"
    operation_kind: ClassVar[str] = "step_import"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.CAD_OPERATIONS.STEPIMPORT
    filename: str
    data: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "filename",
            "ui.schema.fields.filename.label.step_file",
            "str",
            Defaults.FILENAME.DEFAULT,
            doc_key="ui.schema.fields.filename.help.the_step_geometry_is_embedded_in_the_model",
            read_only=True,
        ),
        FieldSpec(
            "data",
            "ui.schema.fields.data.label.step_data",
            "str",
            Defaults.DATA.DEFAULT,
            hidden=True,
        ),
    )


class FuseOperationNode(CADOperationNode):
    """UI definition of Fuse."""

    type_name: ClassVar[str] = "Fuse"
    backend_class: ClassVar[str] = "Fuse"
    label_key: ClassVar[str] = "ui.schema.catalog.cad_operation.fuse.label"
    group: ClassVar[str] = "boolean"
    operation_kind: ClassVar[str] = "fuse"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.CAD_OPERATIONS.FUSE
    object_id: str
    tool_id: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "object_id",
            "ui.schema.fields.object_id.label.object_id",
            "combo",
            Defaults.OBJECT_ID.DEFAULT,
        ),
        FieldSpec(
            "tool_id",
            "ui.schema.fields.tool_id.label.tool_id",
            "combo",
            Defaults.TOOL_ID.DEFAULT,
        ),
    )


class CutOperationNode(CADOperationNode):
    """UI definition of Cut."""

    type_name: ClassVar[str] = "Cut"
    backend_class: ClassVar[str] = "Cut"
    label_key: ClassVar[str] = "ui.schema.catalog.cad_operation.cut.label"
    group: ClassVar[str] = "boolean"
    operation_kind: ClassVar[str] = "cut"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.CAD_OPERATIONS.CUT
    object_id: str
    tool_id: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "object_id",
            "ui.schema.fields.object_id.label.object_id",
            "combo",
            Defaults.OBJECT_ID.DEFAULT,
        ),
        FieldSpec(
            "tool_id",
            "ui.schema.fields.tool_id.label.tool_id",
            "combo",
            Defaults.TOOL_ID.DEFAULT,
        ),
    )


class IntersectOperationNode(CADOperationNode):
    """UI definition of Intersect."""

    type_name: ClassVar[str] = "Intersect"
    backend_class: ClassVar[str] = "Intersect"
    label_key: ClassVar[str] = "ui.schema.catalog.cad_operation.intersect.label"
    group: ClassVar[str] = "boolean"
    operation_kind: ClassVar[str] = "intersect"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.CAD_OPERATIONS.INTERSECT
    object_id: str
    tool_id: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "object_id",
            "ui.schema.fields.object_id.label.object_id",
            "combo",
            Defaults.OBJECT_ID.DEFAULT,
        ),
        FieldSpec(
            "tool_id",
            "ui.schema.fields.tool_id.label.tool_id",
            "combo",
            Defaults.TOOL_ID.DEFAULT,
        ),
    )


class TranslateOperationNode(CADOperationNode):
    """UI definition of Translate."""

    type_name: ClassVar[str] = "Translate"
    backend_class: ClassVar[str] = "Translate"
    label_key: ClassVar[str] = "ui.schema.catalog.cad_operation.translate.label"
    group: ClassVar[str] = "transform"
    operation_kind: ClassVar[str] = "translate"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.CAD_OPERATIONS.TRANSLATE
    input_id: str
    dx: float | str
    dy: float | str
    dz: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "input_id",
            "ui.schema.fields.input_id.label.input_id",
            "combo",
            Defaults.INPUT_ID.DEFAULT,
        ),
        FieldSpec(
            "dx",
            "ui.schema.fields.dx.label.dx",
            "float",
            Defaults.DX.DEFAULT,
        ),
        FieldSpec(
            "dy",
            "ui.schema.fields.dy.label.dy",
            "float",
            Defaults.DY.DEFAULT,
        ),
        FieldSpec(
            "dz",
            "ui.schema.fields.dz.label.dz",
            "float",
            Defaults.DZ.DEFAULT,
        ),
    )


class RotateOperationNode(CADOperationNode):
    """UI definition of Rotate."""

    type_name: ClassVar[str] = "Rotate"
    backend_class: ClassVar[str] = "Rotate"
    label_key: ClassVar[str] = "ui.schema.catalog.cad_operation.rotate.label"
    group: ClassVar[str] = "transform"
    operation_kind: ClassVar[str] = "rotate"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.CAD_OPERATIONS.ROTATE
    input_id: str
    x: float | str
    y: float | str
    z: float | str
    ax: float | str
    ay: float | str
    az: float | str
    angle: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "input_id",
            "ui.schema.fields.input_id.label.input_id",
            "combo",
            Defaults.INPUT_ID.DEFAULT,
        ),
        FieldSpec(
            "x",
            "ui.schema.fields.x.label.x",
            "float",
            Defaults.X.DEFAULT,
        ),
        FieldSpec(
            "y",
            "ui.schema.fields.y.label.y",
            "float",
            Defaults.Y.DEFAULT,
        ),
        FieldSpec(
            "z",
            "ui.schema.fields.z.label.z",
            "float",
            Defaults.Z.DEFAULT,
        ),
        FieldSpec(
            "ax",
            "ui.schema.fields.ax.label.ax",
            "float",
            Defaults.AX.DEFAULT,
        ),
        FieldSpec(
            "ay",
            "ui.schema.fields.ay.label.ay",
            "float",
            Defaults.AY.DEFAULT,
        ),
        FieldSpec(
            "az",
            "ui.schema.fields.az.label.az",
            "float",
            Defaults.AZ.DEFAULT,
        ),
        FieldSpec(
            "angle",
            "ui.schema.fields.angle.label.angle",
            "float",
            Defaults.ANGLE.DEFAULT,
        ),
    )


class DilateOperationNode(CADOperationNode):
    """UI definition of Dilate."""

    type_name: ClassVar[str] = "Dilate"
    backend_class: ClassVar[str] = "Dilate"
    label_key: ClassVar[str] = "ui.schema.catalog.cad_operation.dilate.label"
    group: ClassVar[str] = "transform"
    operation_kind: ClassVar[str] = "dilate"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.CAD_OPERATIONS.DILATE
    input_id: str
    x: float | str
    y: float | str
    z: float | str
    sx: float | str
    sy: float | str
    sz: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "input_id",
            "ui.schema.fields.input_id.label.input_id",
            "combo",
            Defaults.INPUT_ID.DEFAULT,
        ),
        FieldSpec(
            "x",
            "ui.schema.fields.x.label.x",
            "float",
            Defaults.X.DEFAULT,
        ),
        FieldSpec(
            "y",
            "ui.schema.fields.y.label.y",
            "float",
            Defaults.Y.DEFAULT,
        ),
        FieldSpec(
            "z",
            "ui.schema.fields.z.label.z",
            "float",
            Defaults.Z.DEFAULT,
        ),
        FieldSpec(
            "sx",
            "ui.schema.fields.sx.label.sx",
            "float",
            Defaults.SX.DEFAULT,
        ),
        FieldSpec(
            "sy",
            "ui.schema.fields.sy.label.sy",
            "float",
            Defaults.SY.DEFAULT,
        ),
        FieldSpec(
            "sz",
            "ui.schema.fields.sz.label.sz",
            "float",
            Defaults.SZ.DEFAULT,
        ),
    )


class MirrorOperationNode(CADOperationNode):
    """UI definition of Mirror."""

    type_name: ClassVar[str] = "Mirror"
    backend_class: ClassVar[str] = "Mirror"
    label_key: ClassVar[str] = "ui.schema.catalog.cad_operation.mirror.label"
    group: ClassVar[str] = "transform"
    operation_kind: ClassVar[str] = "mirror"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.CAD_OPERATIONS.MIRROR
    input_id: str
    a: float | str
    b: float | str
    c: float | str
    d: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "input_id",
            "ui.schema.fields.input_id.label.input_id",
            "combo",
            Defaults.INPUT_ID.DEFAULT,
        ),
        FieldSpec(
            "a",
            "ui.schema.fields.a.label.a",
            "float",
            Defaults.A.DEFAULT,
        ),
        FieldSpec(
            "b",
            "ui.schema.fields.b.label.b",
            "float",
            Defaults.B.DEFAULT,
        ),
        FieldSpec(
            "c",
            "ui.schema.fields.c.label.c",
            "float",
            Defaults.C.DEFAULT,
        ),
        FieldSpec(
            "d",
            "ui.schema.fields.d.label.d",
            "float",
            Defaults.D.DEFAULT,
        ),
    )
