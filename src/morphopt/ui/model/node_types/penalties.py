"""Explicit penalties node types and their editable fields."""
from __future__ import annotations

from typing import ClassVar

from ....constants import CONSTANT
from ..fields import FieldSpec
from ..base_nodes import PenaltyTermNode



class FairnessPenaltyNode(PenaltyTermNode):
    """UI definition of Fairness."""

    type_name: ClassVar[str] = 'Fairness'
    backend_class: ClassVar[str] = 'Fairness'
    label_key: ClassVar[str] = 'ui.schema.catalog.updater_constraint.fairness.label'
    group: ClassVar[str] = 'geometry'
    gen: ClassVar[str] = 'self.objectivefuncs.Fairness()'
    fields: ClassVar[tuple[FieldSpec, ...]] = (
    )


class DistancePenaltyNode(PenaltyTermNode):
    """UI definition of Distance."""

    type_name: ClassVar[str] = 'Distance'
    backend_class: ClassVar[str] = 'Distance'
    label_key: ClassVar[str] = 'ui.schema.catalog.updater_constraint.distance.label'
    group: ClassVar[str] = 'geometry'
    gen: ClassVar[str] = 'self.objectivefuncs.Distance(min_distance={min_distance})'
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.UPDATER_CONSTRAINTS.DISTANCE
    min_distance: list[list[float | str]] | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            'min_distance',
            'ui.schema.fields.min_distance.label.min_distance_i_j',
            'mat',
            Defaults.MIN_DISTANCE.DEFAULT,
            doc_key='ui.schema.fields.min_distance.help.text',
        ),
    )


class CylinderPenaltyNode(PenaltyTermNode):
    """UI definition of Cylinder."""

    type_name: ClassVar[str] = 'Cylinder'
    backend_class: ClassVar[str] = 'Cylinder'
    label_key: ClassVar[str] = 'ui.schema.catalog.updater_constraint.cylinder.label'
    group: ClassVar[str] = 'geometry'
    gen: ClassVar[str] = 'self.objectivefuncs.boundarys.Cylinder(radius={radius}, height={height}, bottom={bottom})'
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.UPDATER_CONSTRAINTS.CYLINDER
    radius: float | str
    height: float | str
    bottom: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            'radius',
            'ui.schema.fields.radius.label.radius',
            'float',
            Defaults.RADIUS.DEFAULT,
            doc_key='ui.schema.fields.radius.help.text',
        ),
        FieldSpec(
            'height',
            'ui.schema.fields.height.label.height',
            'float',
            Defaults.HEIGHT.DEFAULT,
            doc_key='ui.schema.fields.height.help.envelope_top_z',
        ),
        FieldSpec(
            'bottom',
            'ui.schema.fields.bottom.label.bottom',
            'float',
            Defaults.BOTTOM.DEFAULT,
            doc_key='ui.schema.fields.bottom.help.text',
        ),
    )


class MinRadiusPenaltyNode(PenaltyTermNode):
    """UI definition of MinRadius."""

    type_name: ClassVar[str] = 'MinRadius'
    backend_class: ClassVar[str] = 'MinRadius'
    label_key: ClassVar[str] = 'ui.schema.catalog.updater_constraint.minradius.label'
    group: ClassVar[str] = 'geometry'
    gen: ClassVar[str] = 'self.objectivefuncs.boundarys.MinRadius(radius={radius})'
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.UPDATER_CONSTRAINTS.MINRADIUS
    radius: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            'radius',
            'ui.schema.fields.radius.label.radius',
            'float',
            Defaults.RADIUS.DEFAULT,
            doc_key='ui.schema.fields.radius.help.text',
        ),
    )


class VolumeMaximizationPenaltyNode(PenaltyTermNode):
    """UI definition of VolumeMaximization."""

    type_name: ClassVar[str] = 'VolumeMaximization'
    backend_class: ClassVar[str] = 'VolumeMaximization'
    label_key: ClassVar[str] = 'ui.schema.catalog.updater_constraint.volumemaximization.label'
    group: ClassVar[str] = 'geometry'
    gen: ClassVar[str] = 'self.objectivefuncs.VolumeMaximization(surf_idx={surf_idx}, weight={weight})'
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.UPDATER_CONSTRAINTS.VOLUMEMAXIMIZATION
    surf_idx: int | str
    weight: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            'surf_idx',
            'ui.schema.fields.surf_idx.label.surf_idx',
            'int',
            Defaults.SURF_IDX.DEFAULT,
            doc_key='ui.schema.fields.surf_idx.help.text',
            minimum=Defaults.SURF_IDX.MIN,
        ),
        FieldSpec(
            'weight',
            'ui.schema.fields.weight.label.weight',
            'float',
            Defaults.WEIGHT.DEFAULT,
            doc_key='ui.schema.fields.weight.help.text',
        ),
    )


class InwardCurvatureRadiusPenaltyNode(PenaltyTermNode):
    """UI definition of InwardCurvatureRadius."""

    type_name: ClassVar[str] = 'InwardCurvatureRadius'
    backend_class: ClassVar[str] = 'InwardCurvatureRadius'
    label_key: ClassVar[str] = 'ui.schema.catalog.updater_constraint.inwardcurvatureradius.label'
    group: ClassVar[str] = 'geometry'
    gen: ClassVar[str] = 'morphopt.codesign.InwardCurvatureRadius(margin={margin}, margin_ratio={margin_ratio}, p={p}, penalty_scale={penalty_scale})'
    hidden: ClassVar[bool] = True
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.UPDATER_CONSTRAINTS.INWARDCURVATURERADIUS
    margin: float | str
    margin_ratio: float | str
    p: int | str
    penalty_scale: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            'margin',
            'ui.schema.fields.margin.label.margin',
            'float',
            Defaults.MARGIN.DEFAULT,
            doc_key='ui.schema.fields.margin.help.text',
        ),
        FieldSpec(
            'margin_ratio',
            'ui.schema.fields.margin_ratio.label.margin_ratio',
            'float',
            Defaults.MARGIN_RATIO.DEFAULT,
            doc_key='ui.schema.fields.margin_ratio.help.text',
        ),
        FieldSpec(
            'p',
            'ui.schema.fields.p.label.p',
            'int',
            Defaults.P.DEFAULT,
            doc_key='ui.schema.fields.p.help.text',
            minimum=Defaults.P.MIN,
        ),
        FieldSpec(
            'penalty_scale',
            'ui.schema.fields.penalty_scale.label.penalty_scale',
            'float',
            Defaults.PENALTY_SCALE.DEFAULT,
            doc_key='ui.schema.fields.penalty_scale.help.text',
        ),
    )


class OffsetSurfaceMinThicknessPenaltyNode(PenaltyTermNode):
    """UI definition of OffsetSurfaceMinThickness."""

    type_name: ClassVar[str] = 'OffsetSurfaceMinThickness'
    backend_class: ClassVar[str] = 'OffsetSurfaceMinThickness'
    label_key: ClassVar[str] = 'ui.schema.catalog.updater_constraint.offsetsurfaceminthickness.label'
    group: ClassVar[str] = 'geometry'
    gen: ClassVar[str] = 'morphopt.codesign.OffsetSurfaceMinThickness(min_distance={min_distance})'
    hidden: ClassVar[bool] = True
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.UPDATER_CONSTRAINTS.OFFSETSURFACEMINTHICKNESS
    min_distance: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            'min_distance',
            'ui.schema.fields.min_distance.label.min_distance',
            'float',
            Defaults.MIN_DISTANCE.DEFAULT,
            doc_key='ui.schema.fields.min_distance.help.text',
        ),
    )


class VolFracPenaltyNode(PenaltyTermNode):
    """UI definition of VolFrac."""

    type_name: ClassVar[str] = 'VolFrac'
    backend_class: ClassVar[str] = 'VolFrac'
    label_key: ClassVar[str] = 'ui.schema.catalog.updater_constraint.volfrac.label'
    group: ClassVar[str] = 'materials'
    gen: ClassVar[str] = 'self.objectivefuncs.VolFrac(volfrac_min={volfrac_min}, volfrac_max={volfrac_max}, penalty={penalty}, elementname={elementname})'
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.UPDATER_CONSTRAINTS.VOLFRAC
    volfrac_min: float | str
    volfrac_max: float | str
    penalty: float | str
    elementname: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            'volfrac_min',
            'ui.schema.fields.volfrac_min.label.volfrac_min',
            'float',
            Defaults.VOLFRAC_MIN.DEFAULT,
            doc_key='ui.schema.fields.volfrac_min.help.text',
        ),
        FieldSpec(
            'volfrac_max',
            'ui.schema.fields.volfrac_max.label.volfrac_max',
            'float',
            Defaults.VOLFRAC_MAX.DEFAULT,
            doc_key='ui.schema.fields.volfrac_max.help.text',
        ),
        FieldSpec(
            'penalty',
            'ui.schema.fields.penalty.label.penalty',
            'float',
            Defaults.PENALTY.DEFAULT,
            doc_key='ui.schema.fields.penalty.help.text',
        ),
        FieldSpec(
            'elementname',
            'ui.schema.fields.elementname.label.elems_name',
            'combo',
            Defaults.ELEMENTNAME.DEFAULT,
            doc_key='ui.schema.fields.elementname.help.part_elems',
            choices=Defaults.ELEMENTNAME.CHOICES,
        ),
    )


class MinValuePenaltyNode(PenaltyTermNode):
    """UI definition of MinValue."""

    type_name: ClassVar[str] = 'MinValue'
    backend_class: ClassVar[str] = 'MinValue'
    label_key: ClassVar[str] = 'ui.schema.catalog.updater_constraint.minvalue.label'
    group: ClassVar[str] = 'materials'
    gen: ClassVar[str] = 'self.objectivefuncs.boundarys.MinValue(xmin={xmin}, threshold={threshold}, p={p})'
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.UPDATER_CONSTRAINTS.MINVALUE
    xmin: float | str
    threshold: float | str
    p: int | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            'xmin',
            'ui.schema.fields.xmin.label.xmin',
            'float',
            Defaults.XMIN.DEFAULT,
            doc_key='ui.schema.fields.xmin.help.text',
        ),
        FieldSpec(
            'threshold',
            'ui.schema.fields.threshold.label.threshold',
            'float',
            Defaults.THRESHOLD.DEFAULT,
            doc_key='ui.schema.fields.threshold.help.text',
        ),
        FieldSpec(
            'p',
            'ui.schema.fields.p.label.p',
            'int',
            Defaults.P.DEFAULT,
            doc_key='ui.schema.fields.p.help.text',
            minimum=Defaults.P.MIN,
        ),
    )


class MaxValuePenaltyNode(PenaltyTermNode):
    """UI definition of MaxValue."""

    type_name: ClassVar[str] = 'MaxValue'
    backend_class: ClassVar[str] = 'MaxValue'
    label_key: ClassVar[str] = 'ui.schema.catalog.updater_constraint.maxvalue.label'
    group: ClassVar[str] = 'materials'
    gen: ClassVar[str] = 'self.objectivefuncs.boundarys.MaxValue(xmax={xmax}, threshold={threshold}, p={p})'
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.UPDATER_CONSTRAINTS.MAXVALUE
    xmax: float | str
    threshold: float | str
    p: int | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            'xmax',
            'ui.schema.fields.xmax.label.xmax',
            'float',
            Defaults.XMAX.DEFAULT,
            doc_key='ui.schema.fields.xmax.help.text',
        ),
        FieldSpec(
            'threshold',
            'ui.schema.fields.threshold.label.threshold',
            'float',
            Defaults.THRESHOLD.DEFAULT,
            doc_key='ui.schema.fields.threshold.help.text',
        ),
        FieldSpec(
            'p',
            'ui.schema.fields.p.label.p',
            'int',
            Defaults.P.DEFAULT,
            doc_key='ui.schema.fields.p.help.text',
            minimum=Defaults.P.MIN,
        ),
    )
