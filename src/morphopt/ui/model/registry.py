"""Explicit node-class registries for persistence, menus and field lookup."""
from __future__ import annotations

from collections.abc import Iterable

from ..i18n import localized_message
from .base_nodes import (
    CADOperationNode,
    FEAComponentNode,
    MaterialNode,
    Node,
    ObjectiveTermNode,
    PartNode,
    PenaltyTermNode,
    SurfaceConstraintNode,
    SurfaceNode,
)
from .node_types import (
    BasePartNode,
    BodyForceNode,
    BoundaryConditionNode,
    BoundaryConditionRPNode,
    BoundaryPartNode,
    BoxOperationNode,
    BoxPartNode,
    BspCylinderSurfaceNode,
    BspMirrorConstraintNode,
    BspRelationConstraintNode,
    CADPartNode,
    CPGEOCylinderSurfaceNode,
    CPGEOMirrorConstraintNode,
    CPGEORelationConstraintNode,
    CPGEORotationConstraintNode,
    CPGEOSphereSurfaceNode,
    ConcentratedForceNode,
    ConcentratedMomentNode,
    ConeOperationNode,
    ContactNode,
    ContactSelfNode,
    CoupleNode,
    CustomClassNode,
    CustomFunctionNode,
    CustomSurfaceConstraintNode,
    CutOperationNode,
    CylinderOperationNode,
    CylinderPenaltyNode,
    DensityFieldMinimizeObjectiveNode,
    DilateOperationNode,
    DistancePenaltyNode,
    FairnessPenaltyNode,
    MeshSurfaceNode,
    BREPSurfaceNode,
    FragmentOperationNode,
    FuseOperationNode,
    GeometryNode,
    HelperFunctionNode,
    HelperVariableNode,
    HomogeneousMaterialNode,
    INPPartNode,
    InstanceNode,
    IntersectOperationNode,
    InwardCurvatureRadiusPenaltyNode,
    LoadsNode,
    MaterialsNode,
    MaxValuePenaltyNode,
    MethodOverrideNode,
    MinRadiusPenaltyNode,
    MinValuePenaltyNode,
    MirrorOperationNode,
    ObjectiveNode,
    OffsetBoundaryPartNode,
    OffsetSurfaceMinThicknessPenaltyNode,
    PenaltyDoFNode,
    PressureNode,
    ProblemNode,
    ReferencePointNode,
    RotateOperationNode,
    SIMPFieldMaterialNode,
    SensitivityObjectiveNode,
    ShapeDerivativeObjectiveNode,
    SolverNode,
    SphereOperationNode,
    SpringBetweenRPsNode,
    SpringToGroundNode,
    StepImportOperationNode,
    StepsNode,
    TorusOperationNode,
    TranslateOperationNode,
    UpdaterNode,
    VolFracPenaltyNode,
    VolumeMaximizationPenaltyNode,
    WedgeOperationNode,
)

CAD_OPERATION_TYPES: dict[str, type[CADOperationNode]] = {
    node.type_name: node for node in (
        BoxOperationNode,
        WedgeOperationNode,
        CylinderOperationNode,
        SphereOperationNode,
        ConeOperationNode,
        TorusOperationNode,
        StepImportOperationNode,
        FuseOperationNode,
        CutOperationNode,
        IntersectOperationNode,
        FragmentOperationNode,
        TranslateOperationNode,
        RotateOperationNode,
        DilateOperationNode,
        MirrorOperationNode,
    )
}

SURFACE_TYPES: dict[str, type[SurfaceNode]] = {
    node.type_name: node for node in (
        BspCylinderSurfaceNode,
        CPGEOCylinderSurfaceNode,
        CPGEOSphereSurfaceNode,
        MeshSurfaceNode,
        BREPSurfaceNode,
    )
}

LOAD_TYPES: dict[str, type[FEAComponentNode]] = {
    node.type_name: node for node in (
        PressureNode,
        ConcentratedForceNode,
        ConcentratedMomentNode,
        BodyForceNode,
        SpringToGroundNode,
        SpringBetweenRPsNode,
        PenaltyDoFNode,
        BoundaryConditionNode,
        BoundaryConditionRPNode,
        CoupleNode,
        ReferencePointNode,
        ContactNode,
        ContactSelfNode,
    )
}

MATERIAL_TYPES: dict[str, type[MaterialNode]] = {
    node.type_name: node for node in (
        HomogeneousMaterialNode,
        SIMPFieldMaterialNode,
    )
}

PART_TYPES: dict[str, type[PartNode]] = {
    node.type_name: node for node in (
        BoundaryPartNode,
        INPPartNode,
        BasePartNode,
        BoxPartNode,
        CADPartNode,
        OffsetBoundaryPartNode,
    )
}

UPDATER_OBJECTIVES: dict[str, type[ObjectiveTermNode]] = {
    node.type_name: node for node in (
        ShapeDerivativeObjectiveNode,
        SensitivityObjectiveNode,
        DensityFieldMinimizeObjectiveNode,
    )
}

SURFACE_SYMMETRY_CONSTRAINTS: dict[str, type[SurfaceConstraintNode]] = {
    node.type_name: node for node in (
        BspMirrorConstraintNode,
        CPGEOMirrorConstraintNode,
        CPGEORotationConstraintNode,
        BspRelationConstraintNode,
        CPGEORelationConstraintNode,
        CustomSurfaceConstraintNode,
    )
}

UPDATER_CONSTRAINTS: dict[str, type[PenaltyTermNode]] = {
    node.type_name: node for node in (
        FairnessPenaltyNode,
        DistancePenaltyNode,
        CylinderPenaltyNode,
        MinRadiusPenaltyNode,
        VolumeMaximizationPenaltyNode,
        InwardCurvatureRadiusPenaltyNode,
        OffsetSurfaceMinThicknessPenaltyNode,
        VolFracPenaltyNode,
        MinValuePenaltyNode,
        MaxValuePenaltyNode,
    )
}

UPDATER_CATALOG = {
    "objectives": UPDATER_OBJECTIVES,
    "constraints": UPDATER_CONSTRAINTS,
}

NODE_TYPES: dict[str, type[Node]] = {
    node.kind: node
    for node in (
        # Concrete kinds with their own persistence type.
        ProblemNode,
        GeometryNode,
        InstanceNode,
        LoadsNode,
        StepsNode,
        MaterialsNode,
        ObjectiveNode,
        SolverNode,
        UpdaterNode,
        CustomClassNode,
        CustomFunctionNode,
        HelperFunctionNode,
        HelperVariableNode,
        MethodOverrideNode,
        # Polymorphic families resolve through NODE_FAMILIES below.
        PartNode,
        CADOperationNode,
        SurfaceNode,
        FEAComponentNode,
        MaterialNode,
        ObjectiveTermNode,
        PenaltyTermNode,
        SurfaceConstraintNode,
    )
}

NODE_FAMILIES = {
    CADOperationNode.kind: CAD_OPERATION_TYPES,
    PartNode.kind: PART_TYPES,
    SurfaceNode.kind: SURFACE_TYPES,
    FEAComponentNode.kind: LOAD_TYPES,
    MaterialNode.kind: MATERIAL_TYPES,
    ObjectiveTermNode.kind: UPDATER_OBJECTIVES,
    PenaltyTermNode.kind: UPDATER_CONSTRAINTS,
    SurfaceConstraintNode.kind: SURFACE_SYMMETRY_CONSTRAINTS,
}


def resolve_node_type(kind: str, params: dict) -> type[Node]:
    """Resolve a persisted kind and, for polymorphic nodes, its concrete type."""
    if kind not in NODE_TYPES:
        raise ValueError(
            localized_message(
                "ui.errors.nodes.unknown_model_node_kind_value", value_0=kind
            )
        )
    base = NODE_TYPES[kind]
    if kind not in NODE_FAMILIES:
        return base
    type_name = params.get(base.type_field, "")
    if type_name not in NODE_FAMILIES[kind]:
        raise ValueError(
            localized_message(
                "ui.errors.nodes.unknown_node_type",
                kind=kind,
                type_name=type_name,
            )
        )
    return NODE_FAMILIES[kind][type_name]


def surface_factory_for_type(surface_type: str) -> str | None:
    factory = SURFACE_TYPES[surface_type].factory
    return factory.split(".", 1)[0] if factory else None


def available_surface_symmetry_types(
    surface_types: Iterable[str],
) -> tuple[str, ...]:
    counts: dict[str, int] = {}
    for surface_type in surface_types:
        factory = surface_factory_for_type(surface_type)
        if factory:
            counts[factory] = counts.get(factory, 0) + 1
    return tuple(
        name
        for name, node in SURFACE_SYMMETRY_CONSTRAINTS.items()
        if counts.get(node.factory, 0) >= (2 if node.related_surface else 1)
    )
