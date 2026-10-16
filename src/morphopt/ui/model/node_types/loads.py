"""Explicit loads node types and their editable fields."""

from __future__ import annotations

from typing import ClassVar

from ....constants import CONSTANT
from ..base_nodes import FEAComponentNode
from ..fields import FieldSpec


class PressureNode(FEAComponentNode):
    """UI definition of Pressure."""

    type_name: ClassVar[str] = "Pressure"
    backend_class: ClassVar[str] = "Pressure"
    label_key: ClassVar[str] = "ui.schema.catalog.component.pressure.label"
    name_hint: ClassVar[str] = "pressure_"
    num_values: ClassVar[int] = 1
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.FEA_COMPONENTS.PRESSURE
    instance_name: str
    surface_name: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "instance_name",
            "ui.schema.fields.instance_name.label.instance",
            "combo",
            Defaults.INSTANCE_NAME.DEFAULT,
            doc_key="ui.schema.fields.instance_name.help.torchfea_instance",
            choices=Defaults.INSTANCE_NAME.CHOICES,
        ),
        FieldSpec(
            "surface_name",
            "ui.schema.fields.surface_name.label.surface",
            "combo",
            Defaults.SURFACE_NAME.DEFAULT,
            doc_key="ui.schema.fields.surface_name.help.surface_set_on_the_instance_auto_surface_0_all_surface_1_all",
            choices=Defaults.SURFACE_NAME.CHOICES,
        ),
    )


class ConcentratedForceNode(FEAComponentNode):
    """UI definition of ConcentratedForce."""

    type_name: ClassVar[str] = "ConcentratedForce"
    backend_class: ClassVar[str] = "ConcentratedForce"
    label_key: ClassVar[str] = "ui.schema.catalog.component.concentratedforce.label"
    name_hint: ClassVar[str] = "force_"
    num_values: ClassVar[int] = 3
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.FEA_COMPONENTS.CONCENTRATEDFORCE
    rp_name: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "rp_name",
            "ui.schema.fields.rp_name.label.reference_point",
            "combo",
            Defaults.RP_NAME.DEFAULT,
            doc_key="ui.schema.fields.rp_name.help.rp_created_by_a_referencepoint_component",
            choices=Defaults.RP_NAME.CHOICES,
        ),
    )


class ConcentratedMomentNode(FEAComponentNode):
    """UI definition of ConcentratedMoment."""

    type_name: ClassVar[str] = "ConcentratedMoment"
    backend_class: ClassVar[str] = "ConcentratedMoment"
    label_key: ClassVar[str] = "ui.schema.catalog.component.concentratedmoment.label"
    name_hint: ClassVar[str] = "moment_"
    num_values: ClassVar[int] = 3
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.FEA_COMPONENTS.CONCENTRATEDMOMENT
    rp_name: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "rp_name",
            "ui.schema.fields.rp_name.label.reference_point",
            "combo",
            Defaults.RP_NAME.DEFAULT,
            doc_key="ui.schema.fields.rp_name.help.rp_created_by_a_referencepoint_component",
            choices=Defaults.RP_NAME.CHOICES,
        ),
    )


class BodyForceNode(FEAComponentNode):
    """UI definition of BodyForce."""

    type_name: ClassVar[str] = "Bodyforce"
    backend_class: ClassVar[str] = "BodyForce"
    label_key: ClassVar[str] = "ui.schema.catalog.component.bodyforce.label"
    name_hint: ClassVar[str] = "body_"
    num_values: ClassVar[int] = 3
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.FEA_COMPONENTS.BODYFORCE
    element_name: str
    instance_name: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "element_name",
            "ui.schema.fields.element_name.label.element",
            "combo",
            Defaults.ELEMENT_NAME.DEFAULT,
            doc_key="ui.schema.fields.element_name.help.text",
            choices=Defaults.ELEMENT_NAME.CHOICES,
        ),
        FieldSpec(
            "instance_name",
            "ui.schema.fields.instance_name.label.instance",
            "combo",
            Defaults.INSTANCE_NAME.DEFAULT,
            doc_key="ui.schema.fields.instance_name.help.torchfea_instance",
            choices=Defaults.INSTANCE_NAME.CHOICES,
        ),
    )


class SpringToGroundNode(FEAComponentNode):
    """UI definition of SpringToGround."""

    type_name: ClassVar[str] = "SpringToGround"
    backend_class: ClassVar[str] = "SpringToGround"
    label_key: ClassVar[str] = "ui.schema.catalog.component.springtoground.label"
    name_hint: ClassVar[str] = "spring_"
    num_values: ClassVar[int] = 5
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.FEA_COMPONENTS.SPRINGTOGROUND
    rp_name: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "rp_name",
            "ui.schema.fields.rp_name.label.reference_point",
            "combo",
            Defaults.RP_NAME.DEFAULT,
            doc_key="ui.schema.fields.rp_name.help.text",
            choices=Defaults.RP_NAME.CHOICES,
        ),
    )


class SpringBetweenRPsNode(FEAComponentNode):
    """UI definition of SpringBetweenRPs."""

    type_name: ClassVar[str] = "SpringBetweenRPs"
    backend_class: ClassVar[str] = "SpringBetweenRPs"
    label_key: ClassVar[str] = "ui.schema.catalog.component.springbetweenrps.label"
    name_hint: ClassVar[str] = "spring_"
    num_values: ClassVar[int] = 2
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.FEA_COMPONENTS.SPRINGBETWEENRPS
    rp_name1: str
    rp_name2: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "rp_name1",
            "ui.schema.fields.rp_name1.label.rp_1",
            "combo",
            Defaults.RP_NAME1.DEFAULT,
            doc_key="ui.schema.fields.rp_name1.help.text",
            choices=Defaults.RP_NAME1.CHOICES,
        ),
        FieldSpec(
            "rp_name2",
            "ui.schema.fields.rp_name2.label.rp_2",
            "combo",
            Defaults.RP_NAME2.DEFAULT,
            doc_key="ui.schema.fields.rp_name2.help.text",
            choices=Defaults.RP_NAME2.CHOICES,
        ),
    )


class PenaltyDoFNode(FEAComponentNode):
    """UI definition of PenaltyDoF."""

    type_name: ClassVar[str] = "PenaltyDoF"
    backend_class: ClassVar[str] = "PenaltyDoF"
    label_key: ClassVar[str] = "ui.schema.catalog.component.penaltydof.label"
    name_hint: ClassVar[str] = "lock_"
    num_values: ClassVar[int] = 2
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.FEA_COMPONENTS.PENALTYDOF
    obj_name: str
    s: int | str
    obj_type: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "obj_name",
            "ui.schema.fields.obj_name.label.object",
            "str",
            Defaults.OBJ_NAME.DEFAULT,
            doc_key="ui.schema.fields.obj_name.help.text",
        ),
        FieldSpec(
            "s",
            "ui.schema.fields.s.label.dof",
            "int",
            Defaults.S.DEFAULT,
            doc_key="ui.schema.fields.s.help.text",
        ),
        FieldSpec(
            "obj_type",
            "ui.schema.fields.obj_type.label.obj_type",
            "combo",
            Defaults.OBJ_TYPE.DEFAULT,
            doc_key="ui.schema.fields.obj_type.help.text",
            choices=Defaults.OBJ_TYPE.CHOICES,
        ),
    )


class BoundaryConditionNode(FEAComponentNode):
    """UI definition of BoundaryCondition."""

    type_name: ClassVar[str] = "BoundaryCondition"
    backend_class: ClassVar[str] = "BoundaryCondition"
    label_key: ClassVar[str] = "ui.schema.catalog.component.boundarycondition.label"
    name_hint: ClassVar[str] = "bc_"
    num_values: ClassVar[int] = 0
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.FEA_COMPONENTS.BOUNDARYCONDITION
    instance_name: str
    set_nodes_name: str
    index_dof: list[int]
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "instance_name",
            "ui.schema.fields.instance_name.label.instance",
            "combo",
            Defaults.INSTANCE_NAME.DEFAULT,
            doc_key="ui.schema.fields.instance_name.help.torchfea_instance",
            choices=Defaults.INSTANCE_NAME.CHOICES,
        ),
        FieldSpec(
            "set_nodes_name",
            "ui.schema.fields.set_nodes_name.label.node_set",
            "combo",
            Defaults.SET_NODES_NAME.DEFAULT,
            doc_key="ui.schema.fields.set_nodes_name.help.text",
            choices=Defaults.SET_NODES_NAME.CHOICES,
        ),
        FieldSpec(
            "index_dof",
            "ui.schema.fields.index_dof.label.fixed_dofs_index_dof",
            "dofs",
            Defaults.INDEX_DOF.DEFAULT,
            doc_key="ui.schema.fields.index_dof.help.check_dofs_to_fix_x_y_z_rx_ry_rz",
            size=Defaults.INDEX_DOF.SIZE,
        ),
    )


class BoundaryConditionRPNode(FEAComponentNode):
    """UI definition of ReferencePointBoundaryCondition."""

    type_name: ClassVar[str] = "BoundaryConditionRP"
    backend_class: ClassVar[str] = "ReferencePointBoundaryCondition"
    label_key: ClassVar[str] = "ui.schema.catalog.component.boundaryconditionrp.label"
    name_hint: ClassVar[str] = "bc_rp_"
    num_values: ClassVar[int] = 0
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.FEA_COMPONENTS.BOUNDARYCONDITIONRP
    rp_name: str
    index_dof: list[int]
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "rp_name",
            "ui.schema.fields.rp_name.label.reference_point",
            "combo",
            Defaults.RP_NAME.DEFAULT,
            doc_key="ui.schema.fields.rp_name.help.text",
            choices=Defaults.RP_NAME.CHOICES,
        ),
        FieldSpec(
            "index_dof",
            "ui.schema.fields.index_dof.label.fixed_dofs_index_dof",
            "dofs",
            Defaults.INDEX_DOF.DEFAULT,
            doc_key="ui.schema.fields.index_dof.help.check_dofs_to_fix_x_y_z_rx_ry_rz",
            size=Defaults.INDEX_DOF.SIZE,
        ),
    )


class CoupleNode(FEAComponentNode):
    """UI definition of Couple."""

    type_name: ClassVar[str] = "Couple"
    backend_class: ClassVar[str] = "Couple"
    label_key: ClassVar[str] = "ui.schema.catalog.component.couple.label"
    name_hint: ClassVar[str] = "couple_"
    num_values: ClassVar[int] = 0
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.FEA_COMPONENTS.COUPLE
    rp_name: str
    instance_name: str
    set_nodes_name: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "rp_name",
            "ui.schema.fields.rp_name.label.reference_point",
            "combo",
            Defaults.RP_NAME.DEFAULT,
            doc_key="ui.schema.fields.rp_name.help.text",
            choices=Defaults.RP_NAME.CHOICES,
        ),
        FieldSpec(
            "instance_name",
            "ui.schema.fields.instance_name.label.instance",
            "combo",
            Defaults.INSTANCE_NAME.DEFAULT,
            doc_key="ui.schema.fields.instance_name.help.torchfea_instance",
            choices=Defaults.INSTANCE_NAME.CHOICES,
        ),
        FieldSpec(
            "set_nodes_name",
            "ui.schema.fields.set_nodes_name.label.node_set",
            "combo",
            Defaults.SET_NODES_NAME.DEFAULT,
            doc_key="ui.schema.fields.set_nodes_name.help.text",
            choices=Defaults.SET_NODES_NAME.CHOICES,
        ),
    )


class ReferencePointNode(FEAComponentNode):
    """UI definition of ReferencePoint."""

    type_name: ClassVar[str] = "ReferencePoint"
    backend_class: ClassVar[str] = "ReferencePoint"
    label_key: ClassVar[str] = "ui.schema.catalog.component.referencepoint.label"
    name_hint: ClassVar[str] = "RP_"
    num_values: ClassVar[int] = 0
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.FEA_COMPONENTS.REFERENCEPOINT
    rp_location: list[float] | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "rp_location",
            "ui.schema.fields.rp_location.label.rp_location",
            "vec3",
            Defaults.RP_LOCATION.DEFAULT,
            doc_key="ui.schema.fields.rp_location.help.reference_point_position",
        ),
    )


class ContactNode(FEAComponentNode):
    """UI definition of Contact."""

    type_name: ClassVar[str] = "Contact"
    backend_class: ClassVar[str] = "Contact"
    label_key: ClassVar[str] = "ui.schema.catalog.component.contact.label"
    name_hint: ClassVar[str] = "contact_"
    num_values: ClassVar[int] = 0
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.FEA_COMPONENTS.CONTACT
    instance_name1: str
    surface_name1: str
    instance_name2: str
    surface_name2: str
    penalty_threshold_h: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "instance_name1",
            "ui.schema.fields.instance_name1.label.instance_1",
            "combo",
            Defaults.INSTANCE_NAME1.DEFAULT,
            doc_key="ui.schema.fields.instance_name1.help.text",
            choices=Defaults.INSTANCE_NAME1.CHOICES,
        ),
        FieldSpec(
            "surface_name1",
            "ui.schema.fields.surface_name1.label.surface_1",
            "combo",
            Defaults.SURFACE_NAME1.DEFAULT,
            doc_key="ui.schema.fields.surface_name1.help.select_or_type_a_surface_set_of_another_part",
            choices=Defaults.SURFACE_NAME1.CHOICES,
        ),
        FieldSpec(
            "instance_name2",
            "ui.schema.fields.instance_name2.label.instance_2",
            "combo",
            Defaults.INSTANCE_NAME2.DEFAULT,
            doc_key="ui.schema.fields.instance_name2.help.text",
            choices=Defaults.INSTANCE_NAME2.CHOICES,
        ),
        FieldSpec(
            "surface_name2",
            "ui.schema.fields.surface_name2.label.surface_2",
            "combo",
            Defaults.SURFACE_NAME2.DEFAULT,
            doc_key="ui.schema.fields.surface_name2.help.select_or_type_a_surface_set",
            choices=Defaults.SURFACE_NAME2.CHOICES,
        ),
        FieldSpec(
            "penalty_threshold_h",
            "ui.schema.fields.penalty_threshold_h.label.penalty_threshold_h",
            "float",
            Defaults.PENALTY_THRESHOLD_H.DEFAULT,
            doc_key="ui.schema.fields.penalty_threshold_h.help.text",
        ),
    )


class ContactSelfNode(FEAComponentNode):
    """UI definition of SelfContact."""

    type_name: ClassVar[str] = "ContactSelf"
    backend_class: ClassVar[str] = "SelfContact"
    label_key: ClassVar[str] = "ui.schema.catalog.component.contactself.label"
    name_hint: ClassVar[str] = "contact_self_"
    num_values: ClassVar[int] = 0
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.FEA_COMPONENTS.CONTACTSELF
    instance_name: str
    surface_name: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "instance_name",
            "ui.schema.fields.instance_name.label.instance",
            "combo",
            Defaults.INSTANCE_NAME.DEFAULT,
            doc_key="ui.schema.fields.instance_name.help.torchfea_instance",
            choices=Defaults.INSTANCE_NAME.CHOICES,
        ),
        FieldSpec(
            "surface_name",
            "ui.schema.fields.surface_name.label.surface",
            "combo",
            Defaults.SURFACE_NAME.DEFAULT,
            doc_key="ui.schema.fields.surface_name.help.select_or_type_a_surface_set",
            choices=Defaults.SURFACE_NAME.CHOICES,
        ),
    )
