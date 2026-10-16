"""Problem aggregate: cross-node references, invariants and editing operations.

Shared node bases live in :mod:`base_nodes`; concrete types live in
:mod:`node_types`. This module owns cross-node rules and editing operations.
"""

from __future__ import annotations

from collections.abc import Iterator

from ...constants import CONSTANT
from ..i18n import localized_message
from .base_nodes import (
    INSTANCE_REFERENCE_FIELDS,
    KIND_CAD_OPERATION,
    KIND_GEOMETRY,
    KIND_INSTANCE,
    KIND_FEA_COMPONENT,
    KIND_LOADS,
    KIND_MATERIAL,
    KIND_MATERIALS,
    KIND_OBJECTIVE,
    KIND_PART,
    KIND_PROBLEM,
    KIND_SOLVER,
    KIND_STEPS,
    KIND_SURFACE,
    KIND_UPDATER,
    REFERENCE_POINT_FIELDS,
    SECTION_ORDER,
    TEMPLATE_MODEL_DIRECTORY,
    CADOperationNode,
    FEAComponentNode,
    MaterialNode,
    Node,
    PartNode,
    SurfaceNode,
    find_node,
    list_node_paths,
    resolve_model_directory,
)
from .node_types import (
    BodyForceNode,
    BoundaryPartNode,
    CADPartNode,
    CustomClassNode,
    CustomFunctionNode,
    GeometryNode,
    HelperFunctionNode,
    HelperVariableNode,
    InstanceNode,
    LoadsNode,
    MaterialsNode,
    MethodOverrideNode,
    ObjectiveNode,
    ProblemNode,
    SolverNode,
    StepsNode,
    TorchFEAPartNode,
    UpdaterNode,
)
from .registry import NODE_TYPES

__all__ = [
    "INSTANCE_REFERENCE_FIELDS",
    "KIND_CAD_OPERATION",
    "KIND_GEOMETRY",
    "KIND_INSTANCE",
    "KIND_FEA_COMPONENT",
    "KIND_LOADS",
    "KIND_MATERIAL",
    "KIND_MATERIALS",
    "KIND_OBJECTIVE",
    "KIND_PART",
    "KIND_PROBLEM",
    "KIND_SOLVER",
    "KIND_STEPS",
    "KIND_SURFACE",
    "KIND_UPDATER",
    "NODE_TYPES",
    "REFERENCE_POINT_FIELDS",
    "SECTION_ORDER",
    "TEMPLATE_MODEL_DIRECTORY",
    "CADOperationNode",
    "CustomClassNode",
    "CustomFunctionNode",
    "FEAComponentNode",
    "GeometryNode",
    "HelperFunctionNode",
    "HelperVariableNode",
    "InstanceNode",
    "LoadsNode",
    "MaterialNode",
    "MaterialsNode",
    "MethodOverrideNode",
    "Node",
    "ObjectiveNode",
    "PartNode",
    "ProblemDefinition",
    "ProblemNode",
    "SolverNode",
    "StepsNode",
    "SurfaceNode",
    "UpdaterNode",
    "find_node",
    "list_node_paths",
    "resolve_model_directory",
]


class ProblemDefinition:
    """Top-level description of one optimization problem.

    Attributes mirror the handful of top-level arguments a generated
    ``ThisController`` needs plus the whole editable parameter tree.
    """

    def __init__(
        self,
        scheme: str = "shapeopt",
        label: str = "Untitled",
        result_folder: str = ".results/",
        device: str = "cpu",
        updater_device: str | None = None,
        restart_per_iteration: int = 10,
        root: ProblemNode | None = None,
        custom_classes: list[CustomClassNode] | None = None,
        class_bindings: dict[str, str] | None = None,
        helper_code: str = "",
        helper_variables: list[HelperVariableNode] | None = None,
        helper_functions: list[HelperFunctionNode] | None = None,
    ) -> None:
        scheme = str(scheme or "").strip()
        if not scheme:
            raise ValueError(
                localized_message(
                    "ui.errors.problem.problem_template_id_cannot_be_empty"
                )
            )
        self.scheme = scheme
        self.label = label
        self.result_folder = result_folder
        self.device = device
        # device for the Updater only; None -> follow ``device``
        self.updater_device = updater_device
        self.restart_per_iteration = restart_per_iteration
        if root is not None and not isinstance(root, ProblemNode):
            raise TypeError(localized_message("ui.errors.nodes.expected_problem_root"))
        self.root: ProblemNode = root if root is not None else ProblemNode(name=label)
        self.custom_classes = list(custom_classes or [])
        self.class_bindings: dict[str, str] = dict(class_bindings or {})
        self.helper_code = str(helper_code)
        self.helper_variables = list(helper_variables or [])
        self.helper_functions = list(helper_functions or [])

    # ------------------------------------------------------------ accessors
    def node(self, kind: str) -> Node | None:
        """First node anywhere in the tree with the given kind."""
        return self.root.find(lambda n: n.kind == kind)

    def nodes(self, kind: str) -> list[Node]:
        return [n for n in self.root.iter_nodes() if n.kind == kind]

    def surfaces(self) -> list[SurfaceNode]:
        """All geometry surfaces in their canonical tree order."""
        geometry = self.geometry
        return geometry.surfaces() if geometry is not None else []

    def parts(self) -> list[PartNode]:
        """All geometry Part definitions in their canonical tree order."""
        geometry = self.geometry
        return geometry.parts if geometry is not None else []

    def boundary_part_nodes(self) -> list[BoundaryPartNode]:
        """Parts that own design boundary surfaces."""
        return [
            part
            for part in self.parts()
            if isinstance(part, BoundaryPartNode)
        ]

    def design_material_names(self) -> list[str]:
        """Material definitions that carry design variables (SIMP density fields).

        A material optimizer owns one of these; a homogeneous material has no
        variables, so it cannot be a target.
        """
        return [
            material.name for material in self.material_nodes() if material.is_updatable
        ]

    def owner_of_surface(self, surface: SurfaceNode) -> BoundaryPartNode | None:
        """Part holding ``surface``."""
        geometry = self.geometry
        return geometry.owner(surface) if geometry is not None else None

    def owner_of_instance(self, instance: InstanceNode) -> PartNode | None:
        """Part holding ``instance``."""
        return next(
            (
                part
                for part in self.parts()
                if instance in part.instances
            ),
            None,
        )

    def owner_of_cad_operation(self, operation: CADOperationNode) -> CADPartNode | None:
        """CAD Part holding ``operation``."""
        return next(
            (
                part
                for part in self.parts()
                if isinstance(part, CADPartNode)
                and operation in part.operations
            ),
            None,
        )

    def imported_model_part_node(self) -> TorchFEAPartNode | None:
        """First Part definition that links an exported TorchFEA model."""
        return next(
            (
                part
                for part in self.parts()
                if isinstance(part, TorchFEAPartNode)
            ),
            None,
        )

    def sync_imported_parts(self) -> bool:
        """Align the TorchFEA Part definitions with the linked archive.

        One definition per Part keeps a multi-Part export a multi-Part model:
        Parts and their stored Instance names are registered under their own
        names, and definitions whose Part disappeared from the archive are
        dropped.  Returns whether the tree changed.
        """
        summary = self.imported_model_summary()
        geometry = self.geometry
        if summary is None or geometry is None:
            return False

        linked = [
            part
            for part in self.parts()
            if isinstance(part, TorchFEAPartNode)
        ]
        if not linked:
            return False

        directory = linked[0].model_directory
        filename = linked[0].model_filename or ""
        managed = [part for part in linked if part.model_directory == directory]
        archive_parts = {part.name: part for part in summary.parts}
        changed = False

        for part in managed:
            if part.model_part_name:
                continue
            if len(archive_parts) == 1:
                part.model_part_name = next(iter(archive_parts))
                changed = True

        covered = {
            part.model_part_name
            for part in managed
            if part.model_part_name
        }
        for part in summary.parts:
            if part.name in covered:
                continue
            geometry.add_part(
                PartNode.create(
                    "TorchFEAPart",
                    name=part.name,
                    model_directory=directory,
                    model_filename=filename,
                    model_part_name=part.name,
                    exterior_surface=linked[0].exterior_surface or "",
                )
            )
            covered.add(part.name)
            changed = True

        for part in list(managed):
            name = part.model_part_name
            if not name or name in archive_parts:
                continue
            if len(geometry.parts) <= 1:
                continue
            geometry.remove_child(part)
            changed = True

        for part in summary.parts:
            owner = next(
                (
                    candidate
                    for candidate in self.parts()
                    if isinstance(candidate, TorchFEAPartNode)
                    and candidate.model_part_name == part.name
                ),
                None,
            )
            if owner is None:
                continue
            if owner.assembly_name != part.name:
                owner.part_name = part.name
                changed = True

            # Import the archive's actual placements once, replacing the
            # model's synthetic identity Instance.  Subsequent edits are
            # respected: a user-edited Instance is no longer mistaken for a
            # fresh imported default.
            archive_instances = [
                item for item in summary.instances if item.part_name == part.name
            ]
            current_instances = owner.instances
            is_synthetic = (
                len(current_instances) == 1
                and current_instances[0].name
                in {
                    owner.assembly_name,
                    f"{owner.assembly_name}-1",
                }
                and not isinstance(current_instances[0].translation, str)
                and not isinstance(current_instances[0].rotation, str)
                and current_instances[0].pose == [0.0] * 6
            )
            if archive_instances and is_synthetic:
                owner.remove_child(current_instances[0])
                for item in archive_instances:
                    owner.add_instance(
                        InstanceNode(
                            name=item.name,
                            params={
                                "translation": list(item.translation),
                                "rotation": list(item.rotation),
                            },
                        )
                    )
                changed = True
        return changed

    def fea_components(self) -> list[FEAComponentNode]:
        """All loads, constraints, reference points and contacts in tree order."""
        loads = self.loads
        return loads.components if loads is not None else []

    def amplitude_components(self) -> list[FEAComponentNode]:
        """Amplitude-bearing components represented in the load-step matrix.

        A component is amplitude-bearing when its schema declares one or more
        ``num_values``. Boundary conditions and reference points are
        therefore excluded, while pressure, forces and moments are included.
        """

        return [
            component
            for component in self.fea_components()
            if (component.name and component.num_values)
        ]

    def instance_names(self) -> list[str]:
        """Known FEA instance names, in first-use order.

        Part definitions contribute their persisted Instance children;
        imported TorchFEA models contribute any archive names not yet linked
        to a UI Part definition.
        """
        names: list[str] = []
        for part in self.parts():
            names.extend(part.instance_names)
        summary = self.imported_model_summary()
        if summary is not None:
            names.extend(item.name for item in summary.instances)
        return list(dict.fromkeys(names))

    def part_for_instance(
        self, instance: InstanceNode | str | None
    ) -> PartNode | None:
        """Return the geometry Part that owns one Instance."""
        if isinstance(instance, InstanceNode):
            return self.owner_of_instance(instance)
        name = str(instance or "").strip()
        if not name:
            return None
        return next(
            (
                part
                for part in self.parts()
                if name in part.instance_names
            ),
            None,
        )

    def part_names(self) -> list[str]:
        """Known Part names: defined Parts first, then imported Parts."""
        names = [part.assembly_name for part in self.parts()]
        summary = self.imported_model_summary()
        if summary is not None:
            names.extend(part.name for part in summary.parts)
        return list(dict.fromkeys(name for name in names if name))

    def material_nodes(self) -> list[MaterialNode]:
        """All material assignment nodes in their stable tree order."""
        section = self.section(KIND_MATERIALS)
        return section.assignments if isinstance(section, MaterialsNode) else []

    def imported_model_summary(self):
        """Inspect the linked TorchFEA model, returning ``None`` if unset."""
        geometry = self.imported_model_part_node()
        if geometry is None or not geometry.model_directory:
            return None
        try:
            from .modelinfo import inspect_model

            return inspect_model(
                resolve_model_directory(geometry.model_directory),
                geometry.model_filename or "",
            )
        except Exception:
            return None

    def _part_summary(self, instance_name: str = "", part_name: str = ""):
        summary = self.imported_model_summary()
        if summary is None:
            return None
        if instance_name:
            return summary.part_for_instance(instance_name)
        if part_name:
            return next(
                (item for item in summary.parts if item.name == part_name), None
            )
        return summary.parts[0] if len(summary.parts) == 1 else None

    def node_set_names(self, instance_name: str = "") -> list[str]:
        part = self._part_summary(instance_name=instance_name)
        return list(part.node_sets) if part is not None else []

    def surface_set_names(self, instance_name: str = "") -> list[str]:
        part = self._part_summary(instance_name=instance_name)
        return list(part.surface_sets) if part is not None else []

    def element_set_names(self, instance_name: str = "") -> list[str]:
        part = self._part_summary(instance_name=instance_name)
        return list(part.element_sets) if part is not None else []

    def reference_point_names(self) -> list[str]:
        """Names of reference points declared by the FEA component tree."""
        return [
            component.name
            for component in self.fea_components()
            if component.type == "ReferencePoint" and component.name
        ]

    def element_names(self, part_name: str = "") -> list[str]:
        """Material and load element-family names, in stable unique order."""
        names: list[str] = []
        part = self._part_summary(part_name=part_name)
        if part is not None:
            names.extend(part.element_types)
        for material in self.material_nodes():
            for field in ("elementname",):
                value = getattr(material, field, None)
                if isinstance(value, str) and value.strip():
                    names.append(value.strip())
        for component in self.fea_components():
            if isinstance(component, BodyForceNode) and component.element_name.strip():
                names.append(component.element_name.strip())
        return list(dict.fromkeys(names))

    # typed top-level section accessors (return None when the scheme lacks it)
    def section(self, kind: str) -> Node | None:
        return self.root.section(kind)

    @property
    def geometry(self) -> GeometryNode | None:
        return self.root.geometry

    @property
    def loads(self) -> LoadsNode | None:
        return self.root.loads

    @property
    def steps(self) -> StepsNode | None:
        return self.root.steps

    @property
    def materials(self) -> MaterialsNode | None:
        return self.root.materials

    @property
    def objective(self) -> ObjectiveNode | None:
        return self.root.objective

    @property
    def solver(self) -> SolverNode | None:
        return self.root.solver

    @property
    def updater(self) -> UpdaterNode | None:
        return self.root.updater

    # ---------------------------------------------------------- references
    def resolve_references(self) -> None:
        """Bind every cross-node relation to its target object.

        A loaded ``.morph`` only contains names.  They are consumed here once
        and replaced by direct object links; UI widgets and code generation
        subsequently follow those links, so renaming a node never requires a
        string-replacement pass.
        """
        instances = {
            instance.name: instance
            for part in self.parts()
            for instance in part.instances
            if instance.name
        }
        parts: dict[str, PartNode] = {}
        for part in self.parts():
            if part.name:
                parts[part.name] = part
            if part.assembly_name:
                parts[part.assembly_name] = part
        components = {component.name: component for component in self.fea_components()}
        reference_points = {
            component.name: component
            for component in self.fea_components()
            if component.type == "ReferencePoint" and component.name
        }

        for component in self.fea_components():
            for field, attr in INSTANCE_REFERENCE_FIELDS.items():
                current = getattr(component, attr)
                if current not in instances.values():
                    component.set_reference(
                        field,
                        instances.get(
                            current.name
                            if isinstance(current, InstanceNode)
                            else component.pending_reference_name(field)
                        ),
                    )
            for field, attr in REFERENCE_POINT_FIELDS.items():
                current = getattr(component, attr)
                if current not in reference_points.values():
                    component.set_reference(
                        field,
                        reference_points.get(
                            current.name
                            if isinstance(current, FEAComponentNode)
                            else component.pending_reference_name(field)
                        ),
                    )

        for material in self.material_nodes():
            if material.part not in self.parts():
                target = parts.get(
                    material.part.assembly_name
                    if isinstance(material.part, PartNode)
                    else material.pending_part_name
                )
                if target is not None:
                    material.set_part(target)
                else:
                    material._part_name = ""

        steps = self.steps
        if steps is not None:
            steps.step_values = [
                {
                    target: list(values)
                    for key, values in step.items()
                    if (
                        target := key
                        if isinstance(key, FEAComponentNode)
                        and key in components.values()
                        else components.get(
                            key.name if isinstance(key, FEAComponentNode) else str(key)
                        )
                    )
                    is not None
                }
                for step in steps.step_values
            ]

        objective = self.objective
        if objective is not None:
            objective.jacobian_needed = [
                target
                for item in objective.jacobian_needed
                if (
                    target := item
                    if isinstance(item, FEAComponentNode)
                    and item in components.values()
                    else components.get(
                        item.name if isinstance(item, FEAComponentNode) else str(item)
                    )
                )
                is not None
            ]

        updater = self.updater
        if updater is not None:
            boundary = self.boundary_part_nodes()
            design_materials = [
                material
                for material in self.material_nodes()
                if material.name in self.design_material_names()
            ]
            for config in updater.geometry:
                current = config.get("target")
                if current not in self.parts():
                    name = str(config.pop("part_name", "") or "").strip()
                    target = parts.get(
                        current.name if isinstance(current, PartNode) else name
                    )
                    if target is None and not name and len(boundary) == 1:
                        target = boundary[0]
                    if target is not None:
                        config["target"] = target
                    else:
                        config.pop("target", None)
            for config in updater.materials:
                current = config.get("target")
                if current not in self.material_nodes():
                    name = str(config.pop("material_name", "") or "").strip()
                    target = next(
                        (
                            material
                            for material in design_materials
                            if material.name
                            == (
                                current.name
                                if isinstance(current, MaterialNode)
                                else name
                            )
                        ),
                        None,
                    )
                    if target is None and not name and len(design_materials) == 1:
                        target = design_materials[0]
                    if target is not None:
                        config["target"] = target
                    else:
                        config.pop("target", None)

    def set_component_reference(
        self, component: FEAComponentNode, field: str, value: Node | str | None
    ) -> bool:
        """Set one load-to-Instance or load-to-reference-point link."""
        if component not in self.fea_components():
            return False
        if field in INSTANCE_REFERENCE_FIELDS:
            candidates = {
                instance.name: instance
                for part in self.parts()
                for instance in part.instances
            }
            expected = InstanceNode
        elif field in REFERENCE_POINT_FIELDS:
            candidates = {
                item.name: item
                for item in self.fea_components()
                if item.type == "ReferencePoint"
            }
            expected = FEAComponentNode
        else:
            return False

        if value in (None, ""):
            component.set_reference(field, None)
            return True
        target = value if isinstance(value, expected) else candidates.get(str(value))
        if target is None:
            return False
        if field in INSTANCE_REFERENCE_FIELDS and not isinstance(target, InstanceNode):
            return False
        if field in REFERENCE_POINT_FIELDS and (
            not isinstance(target, FEAComponentNode)
            or target.type != "ReferencePoint"
        ):
            return False
        component.set_reference(field, target)
        return True

    def set_material_part(
        self, material: MaterialNode, value: PartNode | str | None
    ) -> bool:
        """Bind one material definition to a geometry Part."""
        if material not in self.material_nodes():
            return False
        if isinstance(value, PartNode):
            target = value
        else:
            name = str(value or "").strip()
            if not name:
                material.part_name = ""
                return True
            target = next(
                (
                    part
                    for part in self.parts()
                    if name in {part.name, part.assembly_name}
                ),
                None,
            )
        if target is None:
            return False
        material.set_part(target)
        return True

    def set_geometry_updater_target(
        self, config: dict, value: PartNode | str | None
    ) -> bool:
        """Bind a geometry optimizer config to one boundary Part object."""
        if self.updater is None or config not in self.updater.geometry:
            return False
        target = (
            value
            if isinstance(value, PartNode)
            else self.part_node(str(value or "").strip())
        )
        if target is None or target not in self.boundary_part_nodes():
            return False
        if self.config_part_node(config) is not target:
            config["symmetry_constraints"] = []
        config["target"] = target
        config.pop("part_name", None)
        return True

    def set_material_updater_target(
        self, config: dict, value: MaterialNode | str | None
    ) -> bool:
        """Bind a material optimizer config to one design-material object."""
        if self.updater is None or config not in self.updater.materials:
            return False
        target = (
            value
            if isinstance(value, MaterialNode)
            else next(
                (
                    material
                    for material in self.material_nodes()
                    if material.name == str(value or "")
                ),
                None,
            )
        )
        if target is None or target.name not in self.design_material_names():
            return False
        config["target"] = target
        config.pop("material_name", None)
        return True

    def add_geometry_updater(self, target: PartNode) -> dict:
        """Create a geometry optimizer bound directly to one boundary Part."""
        if self.updater is None or target not in self.boundary_part_nodes():
            raise ValueError(
                localized_message(
                    "ui.errors.problem.a_geometry_updater_requires_a_boundary_part_target"
                )
            )
        config = self.updater.add_geometry_config()
        config.pop("part_name", None)
        config["target"] = target
        self.align_surface_dependent_state()
        return config

    def add_material_updater(self, target: MaterialNode) -> dict:
        """Create a material optimizer bound directly to one design material."""
        if self.updater is None or target.name not in self.design_material_names():
            raise ValueError(
                localized_message(
                    "ui.errors.problem.a_material_updater_requires_a_design_material_target"
                )
            )
        config = self.updater.add_materials_config()
        config.pop("material_name", None)
        config["target"] = target
        return config

    def set_jacobian_components(self, values: list[FEAComponentNode | str]) -> None:
        """Bind the objective's Jacobian list to amplitude-load objects."""
        if self.objective is None:
            return
        available = {item.name: item for item in self.amplitude_components()}
        self.objective.jacobian_needed = [
            item if isinstance(item, FEAComponentNode) else available[str(item)]
            for item in values
            if isinstance(item, FEAComponentNode) or str(item) in available
        ]

    # ------------------------------------------------------ tree mutations
    # These operations are deliberately owned by the aggregate root rather
    # than Qt widgets.  A surface's position affects both its ``flip`` flag
    # and the geometry updater's per-surface state, while an FEA component name
    # is referenced by load steps and objective Jacobians.  Keeping the
    # invariants here means every UI entry point behaves identically.
    def align_surface_dependent_state(self) -> None:
        """Normalise updater state whose shape follows ``surfaces()``.

        Existing values are retained in their current order; missing
        ``if_update`` entries default to ``True`` and a stored Distance matrix
        grows with the catalogue default of ``2.5``.  This is safe to call
        after loading a problem definition.
        """
        updater = self.updater
        if updater is None:
            return
        for config in updater.geometry:
            node = self.config_part_node(config)
            if node is None:
                # a config without a resolvable Part covers every surface
                count = len(self.surfaces())
            else:
                count = len(node.surfaces)
            states = self._bool_list(config.get("if_update"))
            config["if_update"] = (states[:count] + [True] * count)[:count]

            for parameters in self._distance_constraint_parameters(config):
                matrix = self._square_matrix(parameters.get("min_distance"))
                if matrix is None:
                    continue
                parameters["min_distance"] = self._resize_matrix(matrix, count)

    def add_surface(
        self,
        surface: SurfaceNode,
        index: int | None = None,
        part: BoundaryPartNode | None = None,
    ) -> SurfaceNode:
        """Insert ``surface`` and synchronise all surface-indexed state.

        ``part`` selects the owning Part; by default the last surface-carrying
        Part is used.
        """
        geometry = self._require_geometry()
        owner = part or self.default_surface_part_node()
        if owner is None:
            raise ValueError(
                localized_message("ui.errors.problem.no_part_can_hold_surfaces")
            )
        if owner not in geometry.parts:
            raise ValueError(
                localized_message("ui.errors.problem.target_part_is_not_in_the_tree")
            )

        surfaces = owner.surfaces
        target_index = len(surfaces) if index is None else index
        if not 0 <= target_index <= len(surfaces):
            raise IndexError(
                localized_message(
                    "ui.errors.problem.surface_insertion_index_out_of_range_value",
                    value_0=target_index,
                )
            )

        owner.add_surface(surface, index=target_index)
        self._insert_surface_state(owner, target_index)
        self.align_surface_dependent_state()
        self._refresh_surface_flags()
        return surface

    def default_surface_part_node(self) -> BoundaryPartNode | None:
        """Last Part able to hold boundary surfaces."""
        candidates = self.boundary_part_nodes()
        return candidates[-1] if candidates else None

    def clone_surface(self, surface: SurfaceNode) -> SurfaceNode:
        """Duplicate ``surface`` directly below itself and return the copy."""
        geometry = self._require_geometry()
        owner = geometry.owner(surface)
        if owner is None:
            raise ValueError(
                localized_message(
                    "ui.errors.problem.the_surface_is_not_part_of_this_problem"
                )
            )
        position = owner.surfaces.index(surface)
        clone = surface.clone()
        if not isinstance(clone, SurfaceNode):  # defensive for custom nodes
            raise TypeError(
                localized_message(
                    "ui.errors.problem.a_surface_clone_must_remain_a_surfacenode"
                )
            )
        return self.add_surface(clone, position + 1, part=owner)

    def remove_surface(self, surface: SurfaceNode) -> None:
        """Remove one surface while preserving the remaining updater mapping."""
        geometry = self._require_geometry()
        owner = geometry.owner(surface)
        if owner is None:
            raise ValueError(
                localized_message(
                    "ui.errors.problem.the_surface_is_not_part_of_this_problem"
                )
            )
        position = owner.surfaces.index(surface)
        self._remove_surface_state(owner, position)
        owner.remove_child(surface)
        self.align_surface_dependent_state()
        self._refresh_surface_flags()

    def move_surface(self, surface: SurfaceNode, offset: int) -> bool:
        """Move a surface by ``offset`` positions inside its owning Part."""
        geometry = self._require_geometry()
        owner = geometry.owner(surface)
        if owner is None:
            return False
        surfaces = owner.surfaces
        source = surfaces.index(surface)
        target = source + offset
        if not 0 <= target < len(surfaces):
            return False
        surfaces[source], surfaces[target] = surfaces[target], surfaces[source]
        self._swap_surface_state(owner, source, target)
        self._refresh_surface_flags()
        return True

    def suggest_component_name(self, prefix: str) -> str:
        """Return the first unused ``<prefix><number>`` component name."""
        names = {component.name for component in self.fea_components()}
        index = 1
        while f"{prefix}{index}" in names:
            index += 1
        return f"{prefix}{index}"

    def suggest_part_name(self, prefix: str = "part") -> str:
        """First unused Part definition name."""
        names = {part.name for part in self.parts()}
        index = 1
        while f"{prefix}{index}" in names:
            index += 1
        return f"{prefix}{index}"

    def suggest_instance_name(
        self, part: PartNode, prefix: str | None = None
    ) -> str:
        """Return the first unused Instance name in the Assembly."""
        base = (prefix or part.assembly_name or "instance").strip()
        names = {
            instance.name
            for part in self.parts()
            for instance in part.instances
        }
        index = 1
        candidate = f"{base}-{index}"
        while candidate in names:
            index += 1
            candidate = f"{base}-{index}"
        return candidate

    def add_instance(self, part: PartNode, instance: InstanceNode) -> InstanceNode:
        """Add one uniquely named Instance to a geometry Part."""
        if part not in self.parts():
            raise ValueError(
                localized_message(
                    "ui.errors.problem.the_target_part_is_not_in_the_tree"
                )
            )
        name = instance.name.strip()
        if not name:
            raise ValueError(
                localized_message("ui.errors.problem.instance_name_cannot_be_empty")
            )
        if any(
            declared.name == name
            for part in self.parts()
            for declared in part.instances
        ):
            raise ValueError(
                localized_message(
                    "ui.errors.problem.instance_value_already_exists_in_the_assembly",
                    value_0=name,
                )
            )
        instance.name = name
        added = part.add_instance(instance)
        self.resolve_references()
        return added

    def remove_instance(self, instance: InstanceNode) -> None:
        """Remove one Instance, keeping a Part's first identity Instance."""
        owner = self.owner_of_instance(instance)
        if owner is None:
            raise ValueError(
                localized_message(
                    "ui.errors.problem.the_instance_is_not_part_of_this_problem"
                )
            )
        if len(owner.instances) <= 1:
            raise ValueError(
                localized_message(
                    "ui.errors.problem.a_part_must_keep_at_least_one_instance"
                )
            )
        owner.remove_child(instance)
        for component in self.fea_components():
            for field, attr in INSTANCE_REFERENCE_FIELDS.items():
                if getattr(component, attr) is instance:
                    component.set_reference(field, None)

    def move_instance(self, instance: InstanceNode, offset: int) -> bool:
        """Move an Instance in its Part's declaration order."""
        owner = self.owner_of_instance(instance)
        if owner is None:
            return False
        instances = owner.instances
        source = instances.index(instance)
        target = source + offset
        if not 0 <= target < len(instances):
            return False
        instances[source], instances[target] = instances[target], instances[source]
        return True

    def add_cad_operation(
        self, part: PartNode, operation: CADOperationNode
    ) -> CADOperationNode:
        """Append one CAD operation to a CAD Part's feature history."""
        if part not in self.parts():
            raise ValueError(
                localized_message(
                    "ui.errors.problem.the_target_part_is_not_in_the_tree"
                )
            )
        if not isinstance(part, CADPartNode):
            raise TypeError(
                localized_message(
                    "ui.errors.problem.cad_operations_can_only_belong_to_a_cadpart"
                )
            )
        return part.add_cad_operation(operation)

    def remove_cad_operation(self, operation: CADOperationNode) -> None:
        """Remove one CAD feature from its owning Part."""
        owner = self.owner_of_cad_operation(operation)
        if owner is None:
            raise ValueError(
                localized_message(
                    "ui.errors.problem.the_cad_operation_is_not_part_of_this_problem"
                )
            )
        dependents = [
            item
            for item in owner.operations
            if item is not operation
            and operation.operation_id in (item.object_id, item.tool_id, item.input_id)
        ]
        if dependents:
            names = ", ".join(item.operation_id for item in dependents)
            raise ValueError(
                localized_message(
                    "ui.errors.problem.cannot_remove_value_it_is_used_by_value",
                    value_0=operation.operation_id,
                    value_1=names,
                )
            )
        owner.remove_child(operation)

    def move_cad_operation(self, operation: CADOperationNode, offset: int) -> bool:
        """Move one CAD feature without disturbing other Part children."""
        owner = self.owner_of_cad_operation(operation)
        if owner is None:
            return False
        source = owner.operations.index(operation)
        target = source + offset
        if not 0 <= target < len(owner.operations):
            return False
        owner.operations[source], owner.operations[target] = (
            owner.operations[target],
            owner.operations[source],
        )
        return True

    def rename_instance(self, instance: InstanceNode, new_name: str) -> bool:
        """Rename an Instance without disturbing loads that reference it."""
        owner = self.owner_of_instance(instance)
        if owner is None:
            return False
        old_name = instance.name
        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return False
        if any(
            declared is not instance and declared.name == new_name
            for part in self.parts()
            for declared in part.instances
        ):
            return False
        instance.name = new_name
        return True

    def add_part(self, part: PartNode, index: int | None = None) -> PartNode:
        """Insert one Part and its Instances into the geometry tree."""
        geometry = self._require_geometry()
        unnamed = not part.name
        if not part.name:
            part.name = self.suggest_part_name()
            instances = part.instances
            if (
                not part.part_name
                and len(instances) == 1
                and instances[0].name in {"part-1", "part"}
            ):
                instances[0].name = f"{part.name}-1"
        if any(item.name == part.name for item in geometry.parts):
            raise ValueError(
                localized_message(
                    "ui.errors.problem.part_name_value_already_exists",
                    value_0=part.name,
                )
            )

        used_instances = {
            instance.name for item in geometry.parts for instance in item.instances
        }
        for instance_index, instance in enumerate(part.instances, start=1):
            if instance.name not in used_instances:
                used_instances.add(instance.name)
                continue
            if not unnamed:
                raise ValueError(
                    localized_message(
                        "ui.errors.problem.instance_value_already_exists",
                        value_0=instance.name,
                    )
                )
            base = part.assembly_name or part.name or "part"
            candidate = f"{base}-{instance_index}"
            suffix = instance_index
            while candidate in used_instances:
                suffix += 1
                candidate = f"{base}-{suffix}"
            instance.name = candidate
            used_instances.add(candidate)
        geometry.add_part(part, index=index)
        self.resolve_references()
        self.align_surface_dependent_state()
        return part

    def clone_part(self, part: PartNode) -> PartNode:
        """Duplicate a Part definition, including its surfaces."""
        geometry = self._require_geometry()
        if part not in geometry.parts:
            raise ValueError(
                localized_message("ui.errors.problem.the_part_is_not_in_this_problem")
            )
        position = geometry.parts.index(part)
        clone = part.clone()
        if not isinstance(clone, PartNode):
            raise TypeError(
                localized_message(
                    "ui.errors.problem.a_part_clone_must_remain_a_partnode"
                )
            )
        clone.name = ""
        return self.add_part(clone, index=position + 1)

    def remove_part(self, part: PartNode) -> None:
        """Remove a Part definition and its surfaces."""
        geometry = self._require_geometry()
        if part not in geometry.parts:
            raise ValueError(
                localized_message("ui.errors.problem.the_part_is_not_in_this_problem")
            )
        if len(geometry.parts) <= 1:
            raise ValueError(
                localized_message(
                    "ui.errors.problem.a_problem_must_keep_at_least_one_part"
                )
            )
        surfaces = part.surfaces if isinstance(part, BoundaryPartNode) else ()
        for _ in surfaces:
            self._remove_surface_state(part, 0)
        for material in self.material_nodes():
            if material.part is part:
                material.part = None
                material._part_name = ""
        if self.updater is not None:
            for config in self.updater.geometry:
                if config.get("target") is part:
                    config.pop("target", None)
        for instance in part.instances:
            for load in self.fea_components():
                for field, attr in INSTANCE_REFERENCE_FIELDS.items():
                    if getattr(load, attr) is instance:
                        load.set_reference(field, None)
        geometry.remove_child(part)
        self.align_surface_dependent_state()
        self._refresh_surface_flags()

    def move_part(self, part: PartNode, offset: int) -> bool:
        """Move a Part definition by ``offset`` positions."""
        geometry = self._require_geometry()
        source = geometry.parts.index(part)
        target = source + offset
        if not 0 <= target < len(geometry.parts):
            return False
        geometry.parts[source], geometry.parts[target] = (
            geometry.parts[target],
            geometry.parts[source],
        )
        return True

    def add_component(
        self, component: FEAComponentNode, index: int | None = None
    ) -> FEAComponentNode:
        """Insert an FEA component into the load section."""
        self._require_loads().add_component(component, index=index)
        self.resolve_references()
        return component

    def add_material(
        self, material: MaterialNode, index: int | None = None
    ) -> MaterialNode:
        """Insert one material assignment into the Materials section."""
        section = self.materials
        if section is None:
            section = MaterialsNode(name="Materials")
            self.root.add_section(section)
        section.add_material(material, index=index)
        self.resolve_references()
        return material

    def clone_material(self, material: MaterialNode) -> MaterialNode:
        section = self.materials
        if section is None or material not in section.assignments:
            raise ValueError(
                localized_message(
                    "ui.errors.problem.material_is_not_part_of_this_problem"
                )
            )
        clone = material.clone()
        if not isinstance(clone, MaterialNode):
            raise TypeError(
                localized_message(
                    "ui.errors.problem.a_material_clone_must_remain_a_materialnode"
                )
            )
        clone.name = f"{material.name}_copy" if material.name else ""
        names = {item.name for item in self.material_nodes()}
        base = clone.name or "material"
        index = 1
        while clone.name in names:
            clone.name = f"{base}_{index}"
            index += 1
        return self.add_material(clone, section.assignments.index(material) + 1)

    def remove_material(self, material: MaterialNode) -> None:
        section = self.materials
        if section is None or material not in section.assignments:
            raise ValueError(
                localized_message(
                    "ui.errors.problem.material_is_not_part_of_this_problem"
                )
            )
        if len(section.assignments) <= 1:
            raise ValueError(
                localized_message(
                    "ui.errors.problem.a_problem_must_keep_at_least_one_material"
                )
            )
        section.remove_child(material)
        if self.updater is not None:
            for config in self.updater.materials:
                if config.get("target") is material:
                    config.pop("target", None)

    def move_material(self, material: MaterialNode, offset: int) -> bool:
        section = self.materials
        if section is None or material not in section.assignments:
            return False
        source = section.assignments.index(material)
        target = source + offset
        if not 0 <= target < len(section.assignments):
            return False
        section.assignments[source], section.assignments[target] = (
            section.assignments[target],
            section.assignments[source],
        )
        return True

    def clone_component(
        self, component: FEAComponentNode, name_prefix: str
    ) -> FEAComponentNode:
        """Duplicate a component below itself with a fresh reference name."""
        loads = self._require_loads()
        clone = component.clone()
        if not isinstance(clone, FEAComponentNode):  # defensive for custom nodes
            raise TypeError(
                localized_message(
                    "ui.errors.problem.a_component_clone_must_remain_a_fea_component_node"
                )
            )
        clone.name = self.suggest_component_name(name_prefix)
        return self.add_component(clone, loads.components.index(component) + 1)

    def move_component(self, component: FEAComponentNode, offset: int) -> bool:
        """Move a component without changing its name."""
        loads = self._require_loads()
        source = loads.components.index(component)
        target = source + offset
        if not 0 <= target < len(loads.components):
            return False
        loads.components[source], loads.components[target] = (
            loads.components[target],
            loads.components[source],
        )
        return True

    def remove_component(self, component: FEAComponentNode) -> None:
        """Remove a component and every reference to it."""
        self._require_loads().remove_child(component)
        if self.steps is not None:
            for values in self.steps.step_values:
                values.pop(component, None)
        if self.objective is not None:
            self.objective.jacobian_needed = [
                item for item in self.objective.jacobian_needed if item is not component
            ]
        for load in self.fea_components():
            for field, attr in REFERENCE_POINT_FIELDS.items():
                if getattr(load, attr) is component:
                    load.set_reference(field, None)

    def rename_definition(
        self,
        definition: FEAComponentNode | PartNode | MaterialNode,
        new_name: str,
    ) -> bool:
        """Rename a Part, material or FEA component and retain references.

        Parts, materials and FEA components share this entry point. Their names
        belong to separate collections, but each
        may be referenced elsewhere in the problem definition.  Keeping the
        dispatch here prevents Qt editors from having to know those links.
        Existing object references follow their target automatically; only the
        persisted/UI name projection changes.
        """
        if isinstance(definition, PartNode):
            return self._rename_part_node(definition, new_name)
        if isinstance(definition, MaterialNode):
            return self._rename_material(definition, new_name)
        if isinstance(definition, FEAComponentNode):
            return self._rename_component(definition, new_name)
        return False

    def rename_part(self, part: PartNode, part_name: str) -> bool:
        """Rename a generated Assembly Part and its identity Instance.

        ``part_name`` may be empty, in which case the Assembly Part name falls
        back to the Part definition name. Only the conventional identity instance
        (``<part>-1``) follows this change;
        explicitly named instances retain both their names and their poses.
        """
        if part not in self.parts():
            return False
        if isinstance(part, TorchFEAPartNode):
            # The archive owns the physical Part name. The UI Part definition
            # may still be renamed through ``rename_definition`` above.
            return False

        old_part_name = part.assembly_name
        part_name = part_name.strip()
        new_part_name = part_name or part.name.strip()
        if not new_part_name:
            return False
        if part_name == part.part_name:
            return False
        if any(
            item is not part and item.assembly_name == new_part_name
            for item in self.parts()
        ):
            return False
        if not self._can_rename_default_instance(
            part, old_part_name, new_part_name
        ):
            return False

        part.part_name = part_name
        self._rename_default_instance(part, old_part_name, new_part_name)
        return True

    def _rename_component(
        self, component: FEAComponentNode, new_name: str
    ) -> bool:
        """Rename an FEA component; object references follow automatically."""
        if component not in self.fea_components():
            return False
        new_name = new_name.strip()
        old_name = component.name
        if not new_name or new_name == old_name:
            return False
        if any(
            item is not component and item.name == new_name
            for item in self.fea_components()
        ):
            return False

        component.name = new_name
        return True

    def _rename_part_node(self, part: PartNode, new_name: str) -> bool:
        """Rename a Part definition while dependants retain the object."""
        if part not in self.parts():
            return False
        new_name = new_name.strip()
        old_name = part.name
        if not new_name or new_name == old_name:
            return False
        if any(
            item is not part and item.name == new_name
            for item in self.parts()
        ):
            return False

        old_part_name = part.assembly_name
        # A TorchFEA Part-definition name is only MorphOpt's registration key. Its
        # actual Part and Instance names are owned by the imported archive;
        # treating it as a physical-Part rename would make load references
        # disagree with the archive on the next synchronization.
        imported_part = part.type == "TorchFEAPart"
        new_part_name = (
            old_part_name
            if imported_part
            else (part.part_name or new_name).strip()
        )
        if not self._can_rename_default_instance(
            part, old_part_name, new_part_name
        ):
            return False

        part.name = new_name
        if imported_part:
            # Persist the archive Part explicitly before the registration
            # name changes, otherwise ``assembly_name`` would fall back to the
            # newly edited Part-definition name.
            part.part_name = old_part_name
        self._rename_default_instance(part, old_part_name, new_part_name)
        return True

    def _rename_material(
        self, material: MaterialNode, new_name: str
    ) -> bool:
        """Rename a material definition while its updater retains the object."""
        if material not in self.material_nodes():
            return False
        new_name = new_name.strip()
        old_name = material.name
        if not new_name or new_name == old_name:
            return False
        if any(
            item is not material and item.name == new_name
            for item in self.material_nodes()
        ):
            return False

        material.name = new_name
        return True

    def _can_rename_default_instance(
        self,
        part: PartNode,
        old_part_name: str,
        new_part_name: str,
    ) -> bool:
        """Whether following the identity Instance would keep names unique."""
        default = self._default_instance(part, old_part_name)
        if default is None or old_part_name == new_part_name:
            return True
        target_name = f"{new_part_name}-1"
        return not any(
            instance is not default and instance.name == target_name
            for part in self.parts()
            for instance in part.instances
        )

    @staticmethod
    def _default_instance(part: PartNode, part_name: str) -> InstanceNode | None:
        """Return the conventional identity Instance, if it still exists."""
        conventional = f"{part_name}-1"
        return next(
            (
                instance
                for instance in part.instances
                if instance.name == conventional
            ),
            None,
        )

    def _rename_default_instance(
        self,
        part: PartNode,
        old_part_name: str,
        new_part_name: str,
    ) -> None:
        """Rename only the conventional identity Instance of a Part."""
        if old_part_name == new_part_name:
            return
        default = self._default_instance(part, old_part_name)
        if default is not None:
            default.name = f"{new_part_name}-1"

    # ---------------------------------------------------- mutation helpers
    def _require_geometry(self) -> GeometryNode:
        if self.geometry is None:
            raise ValueError(
                localized_message(
                    "ui.errors.problem.this_problem_has_no_geometry_section"
                )
            )
        return self.geometry

    def _require_loads(self) -> LoadsNode:
        if self.loads is None:
            raise ValueError(
                localized_message("ui.errors.problem.this_problem_has_no_loads_section")
            )
        return self.loads

    @staticmethod
    def _bool_list(value: object) -> list[bool]:
        if value is None:
            return []
        if isinstance(value, bool):
            return [value]
        if not isinstance(value, (list, tuple)):
            return [bool(value)]
        return [bool(item) for item in value]

    @staticmethod
    def _square_matrix(value: object) -> list[list[float | str]] | None:
        if not isinstance(value, (list, tuple)) or not value:
            return None
        rows: list[list[float | str]] = []
        for row in value:
            if isinstance(row, (list, tuple)):
                rows.append(
                    [item if isinstance(item, str) else float(item) for item in row]
                )
            elif isinstance(row, (int, float)):
                rows.append([float(row)])
            else:
                return None
        size = max(len(rows), max((len(row) for row in rows), default=0))
        return [
            [
                rows[row_index][column_index]
                if row_index < len(rows) and column_index < len(rows[row_index])
                else CONSTANT.UI.UPDATER_EDITOR.DEFAULT_INTER_SURFACE_DISTANCE
                for column_index in range(size)
            ]
            for row_index in range(size)
        ]

    @staticmethod
    def _resize_matrix(
        matrix: list[list[float | str]], size: int
    ) -> list[list[float | str]]:
        return [
            [
                matrix[row_index][column_index]
                if row_index < len(matrix) and column_index < len(matrix[row_index])
                else CONSTANT.UI.UPDATER_EDITOR.DEFAULT_INTER_SURFACE_DISTANCE
                for column_index in range(size)
            ]
            for row_index in range(size)
        ]

    @staticmethod
    def _distance_constraint_parameters(config: dict) -> Iterator[dict]:
        for constraint in config.get("constraints", []) or []:
            if (
                isinstance(constraint, dict)
                and constraint.get("type") == "Distance"
                and isinstance(constraint.get("params"), dict)
            ):
                yield constraint["params"]

    def part_node(self, name: str) -> PartNode | None:
        """Boundary Part node by name (``None`` when unknown)."""
        if not name:
            return None
        return next(
            (node for node in self.parts() if node.name == name), None
        )

    def config_part_node(self, config: dict) -> BoundaryPartNode | None:
        """Boundary Part object bound to a geometry sub-optimizer config."""
        target = config.get("target") if config is not None else None
        return target if isinstance(target, BoundaryPartNode) else None

    def config_material_node(self, config: dict) -> MaterialNode | None:
        """Design-material object bound to a material sub-optimizer config."""
        target = config.get("target") if config is not None else None
        return target if isinstance(target, MaterialNode) else None

    def _geometry_config_for_part(self, part: PartNode) -> dict | None:
        """Return the geometry updater config targeting ``part``."""
        updater = self.updater
        if updater is None:
            return None
        for config in updater.geometry:
            if self.config_part_node(config) is part:
                return config
        return None

    def _insert_surface_state(self, part: PartNode, index: int) -> None:
        config = self._geometry_config_for_part(part)
        if config is None:
            return
        states = self._bool_list(config.get("if_update"))
        states.insert(index, True)
        config["if_update"] = states
        for constraint in config.get("symmetry_constraints", []) or []:
            if not isinstance(constraint, dict) or constraint.get("type") == "Custom":
                continue
            for key in ("surface_index", "related_surface_index"):
                surface_index = constraint.get(key)
                if isinstance(surface_index, int) and surface_index >= index:
                    constraint[key] = surface_index + 1
        for parameters in self._distance_constraint_parameters(config):
            matrix = self._square_matrix(parameters.get("min_distance"))
            if matrix is None:
                continue
            matrix = self._resize_matrix(matrix, len(matrix))
            matrix.insert(
                index,
                [CONSTANT.UI.UPDATER_EDITOR.DEFAULT_INTER_SURFACE_DISTANCE]
                * (len(matrix) + 1),
            )
            for row_index, row in enumerate(matrix):
                if row_index != index:
                    row.insert(
                        index,
                        CONSTANT.UI.UPDATER_EDITOR.DEFAULT_INTER_SURFACE_DISTANCE,
                    )
            parameters["min_distance"] = matrix

    def _remove_surface_state(self, part: PartNode, index: int) -> None:
        config = self._geometry_config_for_part(part)
        if config is None:
            return
        states = self._bool_list(config.get("if_update"))
        if index < len(states):
            del states[index]
        config["if_update"] = states
        constraints = []
        for constraint in config.get("symmetry_constraints", []) or []:
            if not isinstance(constraint, dict) or constraint.get("type") == "Custom":
                constraints.append(constraint)
                continue
            indices = [
                constraint.get(key)
                for key in ("surface_index", "related_surface_index")
                if constraint.get(key) is not None
            ]
            if index in indices:
                continue
            for key in ("surface_index", "related_surface_index"):
                surface_index = constraint.get(key)
                if isinstance(surface_index, int) and surface_index > index:
                    constraint[key] = surface_index - 1
            constraints.append(constraint)
        config["symmetry_constraints"] = constraints
        for parameters in self._distance_constraint_parameters(config):
            matrix = self._square_matrix(parameters.get("min_distance"))
            if matrix is None or index >= len(matrix):
                continue
            del matrix[index]
            for row in matrix:
                if index < len(row):
                    del row[index]
            parameters["min_distance"] = matrix

    def _swap_surface_state(self, part: PartNode, first: int, second: int) -> None:
        config = self._geometry_config_for_part(part)
        if config is None:
            return
        states = self._bool_list(config.get("if_update"))
        if first < len(states) and second < len(states):
            states[first], states[second] = states[second], states[first]
        config["if_update"] = states
        for constraint in config.get("symmetry_constraints", []) or []:
            if not isinstance(constraint, dict) or constraint.get("type") == "Custom":
                continue
            for key in ("surface_index", "related_surface_index"):
                surface_index = constraint.get(key)
                if surface_index == first:
                    constraint[key] = second
                elif surface_index == second:
                    constraint[key] = first
        for parameters in self._distance_constraint_parameters(config):
            matrix = self._square_matrix(parameters.get("min_distance"))
            if matrix is None or max(first, second) >= len(matrix):
                continue
            matrix[first], matrix[second] = matrix[second], matrix[first]
            for row in matrix:
                row[first], row[second] = row[second], row[first]
            parameters["min_distance"] = matrix

    def _refresh_surface_flags(self) -> None:
        for part in self.boundary_part_nodes():
            for index, surface in enumerate(part.surfaces):
                surface.flip = index > 0

    # ----------------------------------------------------------- persistence
    def to_dict(self) -> dict:
        self.resolve_references()
        return {
            "version": 3,
            "scheme": self.scheme,
            "label": self.label,
            "result_folder": self.result_folder,
            "device": self.device,
            "updater_device": self.updater_device,
            "restart_per_iteration": self.restart_per_iteration,
            "root": self.root.to_dict(),
            "custom_classes": [node.to_dict() for node in self.custom_classes],
            "class_bindings": dict(self.class_bindings),
            "helper_code": self.helper_code,
            "helper_variables": [node.to_dict() for node in self.helper_variables],
            "helper_functions": [node.to_dict() for node in self.helper_functions],
        }

    @classmethod
    def from_dict(cls, data: dict) -> ProblemDefinition:
        if data.get("version") != 3:
            raise ValueError(
                localized_message(
                    "ui.errors.problem.unsupported_morph_version_value",
                    value_0=data.get("version"),
                )
            )
        root = ProblemNode.from_dict(data["root"])
        problem = cls(
            scheme=data["scheme"],
            label=data.get("label", "Untitled"),
            result_folder=data.get("result_folder", ".results/"),
            device=data.get("device", "cpu"),
            updater_device=data.get("updater_device"),
            restart_per_iteration=data.get("restart_per_iteration", 10),
            root=root,
            custom_classes=[
                CustomClassNode.from_dict(node)
                for node in data.get("custom_classes", [])
            ],
            class_bindings=data.get("class_bindings", {}),
            helper_code=data["helper_code"],
            helper_variables=[
                HelperVariableNode.from_dict(node) for node in data["helper_variables"]
            ],
            helper_functions=[
                HelperFunctionNode.from_dict(node) for node in data["helper_functions"]
            ],
        )
        problem.resolve_references()
        return problem
