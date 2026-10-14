"""Problem aggregate: cross-node references, invariants and editing operations.

Concrete nodes live in ``nodes`` and are re-exported here as the model API.
"""
from __future__ import annotations
from collections.abc import Iterator
from .nodes import (
    Node,
    ProblemNode,
    GeometryNode,
    CADOperationNode,
    PartInterfaceNode,
    InstanceNode,
    SurfaceNode,
    LoadsNode,
    InterfaceNode,
    StepsNode,
    MaterialsNode,
    MaterialNode,
    ObjectiveNode,
    SolverNode,
    UpdaterNode,
    MethodOverrideNode,
    CustomClassNode,
    HelperVariableNode,
    HelperFunctionNode,
    KIND_PROBLEM,
    KIND_GEOMETRY,
    KIND_PART_INTERFACE,
    KIND_CAD_OPERATION,
    KIND_INSTANCE,
    KIND_SURFACE,
    KIND_LOADS,
    KIND_INTERFACE,
    KIND_STEPS,
    KIND_MATERIAL,
    KIND_MATERIALS,
    KIND_OBJECTIVE,
    KIND_SOLVER,
    KIND_UPDATER,
    INSTANCE_REFERENCE_FIELDS,
    REFERENCE_POINT_FIELDS,
    TEMPLATE_MODEL_DIRECTORY,
    SECTION_ORDER,
    NODE_TYPES,
    resolve_model_directory,
    find_node,
    list_node_paths,
)


__all__ = [
    'ProblemDefinition',
    'Node',
    'ProblemNode',
    'GeometryNode',
    'CADOperationNode',
    'PartInterfaceNode',
    'InstanceNode',
    'SurfaceNode',
    'LoadsNode',
    'InterfaceNode',
    'StepsNode',
    'MaterialsNode',
    'MaterialNode',
    'ObjectiveNode',
    'SolverNode',
    'UpdaterNode',
    'MethodOverrideNode',
    'CustomClassNode',
    'HelperVariableNode',
    'HelperFunctionNode',
    'KIND_PROBLEM',
    'KIND_GEOMETRY',
    'KIND_PART_INTERFACE',
    'KIND_CAD_OPERATION',
    'KIND_INSTANCE',
    'KIND_SURFACE',
    'KIND_LOADS',
    'KIND_INTERFACE',
    'KIND_STEPS',
    'KIND_MATERIAL',
    'KIND_MATERIALS',
    'KIND_OBJECTIVE',
    'KIND_SOLVER',
    'KIND_UPDATER',
    'INSTANCE_REFERENCE_FIELDS',
    'REFERENCE_POINT_FIELDS',
    'TEMPLATE_MODEL_DIRECTORY',
    'SECTION_ORDER',
    'NODE_TYPES',
    'resolve_model_directory',
    'find_node',
    'list_node_paths',
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
        root: Node | None = None,
        custom_classes: list[CustomClassNode] | None = None,
        class_bindings: dict[str, str] | None = None,
        helper_code: str = "",
        helper_variables: list[HelperVariableNode] | None = None,
        helper_functions: list[HelperFunctionNode] | None = None,
    ) -> None:
        scheme = str(scheme or "").strip()
        if not scheme:
            raise ValueError("Problem template id cannot be empty")
        self.scheme = scheme
        self.label = label
        self.result_folder = result_folder
        self.device = device
        # device for the Updater only; None -> follow ``device``
        self.updater_device = updater_device
        self.restart_per_iteration = restart_per_iteration
        self.root = root if root is not None else ProblemNode(name=label)
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

    def part_interfaces(self) -> list[PartInterfaceNode]:
        """All geometry interfaces (Parts) in their canonical tree order."""
        geometry = self.geometry
        return geometry.interfaces() if geometry is not None else []

    def boundary_part_nodes(self) -> list[PartInterfaceNode]:
        """Geometry interfaces that own boundary surfaces."""
        return [
            interface for interface in self.part_interfaces() if interface.has_surfaces
        ]

    def design_material_names(self) -> list[str]:
        """Material interfaces that carry design variables (SIMP density fields).

        A material optimizer owns one of these; a homogeneous material has no
        variables, so it cannot be a target.
        """
        from .schemas import MATERIAL_TYPES

        return [
            material.name
            for material in self.material_nodes()
            if MATERIAL_TYPES.get(material.material_type, {}).get("design")
        ]

    def owner_of_surface(self, surface: SurfaceNode) -> PartInterfaceNode | None:
        """Geometry interface holding ``surface``."""
        geometry = self.geometry
        return geometry.owner(surface) if geometry is not None else None

    def owner_of_instance(self, instance: InstanceNode) -> PartInterfaceNode | None:
        """Geometry interface holding ``instance``."""
        return next(
            (
                interface
                for interface in self.part_interfaces()
                if instance in interface.instances()
            ),
            None,
        )

    def owner_of_cad_operation(
        self, operation: CADOperationNode
    ) -> PartInterfaceNode | None:
        """CAD Part holding ``operation``."""
        return next(
            (
                interface
                for interface in self.part_interfaces()
                if operation in interface.cad_operations()
            ),
            None,
        )

    def imported_model_part_node(self) -> PartInterfaceNode | None:
        """First geometry interface that links an exported TorchFEA model."""
        return next(
            (
                interface
                for interface in self.part_interfaces()
                if interface.interface_type == "TorchFEAPartInterface"
            ),
            None,
        )

    def sync_imported_part_interfaces(self) -> bool:
        """Align the TorchFEA geometry interfaces with the linked archive.

        One interface per Part keeps a multi-Part export a multi-Part model:
        Parts and their stored Instance names are registered under their own
        names, and interfaces whose Part disappeared from the archive are
        dropped.  Returns whether the tree changed.
        """
        summary = self.imported_model_summary()
        geometry = self.geometry
        if summary is None or geometry is None:
            return False

        linked = [
            interface
            for interface in self.part_interfaces()
            if interface.interface_type == "TorchFEAPartInterface"
        ]
        if not linked:
            return False

        directory = linked[0].model_directory
        filename = linked[0].model_filename or ""
        managed = [
            interface for interface in linked if interface.model_directory == directory
        ]
        archive_parts = {part.name: part for part in summary.parts}
        changed = False

        for interface in managed:
            if interface.model_part_name:
                continue
            if len(archive_parts) == 1:
                interface.model_part_name = next(iter(archive_parts))
                changed = True

        covered = {
            interface.model_part_name
            for interface in managed
            if interface.model_part_name
        }
        for part in summary.parts:
            if part.name in covered:
                continue
            geometry.add_interface(
                PartInterfaceNode.create(
                    "TorchFEAPartInterface",
                    name=part.name,
                    model_directory=directory,
                    model_filename=filename,
                    model_part_name=part.name,
                    exterior_surface=linked[0].exterior_surface or "",
                )
            )
            covered.add(part.name)
            changed = True

        for interface in list(managed):
            name = interface.model_part_name
            if not name or name in archive_parts:
                continue
            if len(geometry.interfaces()) <= 1:
                continue
            geometry.remove_child(interface)
            changed = True

        for part in summary.parts:
            owner = next(
                (
                    interface
                    for interface in self.part_interfaces()
                    if interface.model_part_name == part.name
                ),
                None,
            )
            if owner is None:
                continue
            if owner.resolved_part_name() != part.name:
                owner.part_name = part.name
                changed = True

            # Import the archive's actual placements once, replacing the
            # model's synthetic identity Instance.  Subsequent edits are
            # respected: a user-edited Instance is no longer mistaken for a
            # fresh imported default.
            archive_instances = [
                item for item in summary.instances if item.part_name == part.name
            ]
            current_instances = owner.instances()
            is_synthetic = (
                len(current_instances) == 1
                and current_instances[0].name
                in {
                    owner.resolved_part_name(),
                    f"{owner.resolved_part_name()}-1",
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

    def interfaces(self) -> list[InterfaceNode]:
        """All FEA interfaces in their canonical tree order."""
        loads = self.loads
        return loads.interfaces() if loads is not None else []

    def amplitude_interfaces(self) -> list[InterfaceNode]:
        """Interfaces represented by columns in the load-step matrix.

        An interface is an amplitude-bearing load when its schema declares one
        or more ``num_values``.  Boundary conditions and reference points are
        therefore excluded, while pressure, forces and moments are included.
        """
        from .schemas import INTERFACE_TYPES

        return [
            interface
            for interface in self.interfaces()
            if (
                interface.name
                and INTERFACE_TYPES.get(interface.interface_type, {}).get(
                    "num_values", 0
                )
            )
        ]

    def instance_names(self) -> list[str]:
        """Known FEA instance names, in first-use order.

        Geometry interfaces contribute their persisted Instance children;
        imported TorchFEA models contribute any archive names not yet linked
        to a UI Part interface.
        """
        names: list[str] = []
        for interface in self.part_interfaces():
            names.extend(interface.resolved_instance_names())
        summary = self.imported_model_summary()
        if summary is not None:
            names.extend(item.name for item in summary.instances)
        return list(dict.fromkeys(names))

    def part_interface_for_instance(
        self, instance: InstanceNode | str | None
    ) -> PartInterfaceNode | None:
        """Return the geometry Part interface that owns one Instance."""
        if isinstance(instance, InstanceNode):
            return self.owner_of_instance(instance)
        name = str(instance or "").strip()
        if not name:
            return None
        return next(
            (
                interface
                for interface in self.part_interfaces()
                if name in interface.resolved_instance_names()
            ),
            None,
        )

    def part_names(self) -> list[str]:
        """Known Part names: geometry interfaces first, then imported Parts."""
        names = [interface.resolved_part_name() for interface in self.part_interfaces()]
        summary = self.imported_model_summary()
        if summary is not None:
            names.extend(part.name for part in summary.parts)
        return list(dict.fromkeys(name for name in names if name))

    def material_nodes(self) -> list[MaterialNode]:
        """All material assignment nodes in their stable tree order."""
        section = self.section(KIND_MATERIALS)
        return section.materials() if isinstance(section, MaterialsNode) else []

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
        """Names of reference points declared by the load-interface tree."""
        return [
            interface.name
            for interface in self.interfaces()
            if interface.interface_type == "ReferencePoint" and interface.name
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
        for interface in self.interfaces():
            if (
                isinstance(interface.element_name, str)
                and interface.element_name.strip()
            ):
                names.append(interface.element_name.strip())
        return list(dict.fromkeys(names))

    # typed top-level section accessors (return None when the scheme lacks it)
    def section(self, kind: str) -> Node | None:
        return (
            self.root.section(kind)
            if isinstance(self.root, ProblemNode)
            else self.root.child(kind)
        )

    @property
    def geometry(self) -> GeometryNode | None:
        return self.section(KIND_GEOMETRY)

    @property
    def loads(self) -> LoadsNode | None:
        return self.section(KIND_LOADS)

    @property
    def steps(self) -> StepsNode | None:
        return self.section(KIND_STEPS)

    @property
    def materials(self) -> MaterialsNode | None:
        section = self.section(KIND_MATERIALS)
        if isinstance(section, MaterialsNode):
            return section
        return None

    @property
    def objective(self) -> ObjectiveNode | None:
        return self.section(KIND_OBJECTIVE)

    @property
    def solver(self) -> SolverNode | None:
        return self.section(KIND_SOLVER)

    @property
    def updater(self) -> UpdaterNode | None:
        return self.section(KIND_UPDATER)

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
            for part in self.part_interfaces()
            for instance in part.instances()
            if instance.name
        }
        parts: dict[str, PartInterfaceNode] = {}
        for part in self.part_interfaces():
            if part.name:
                parts[part.name] = part
            if part.resolved_part_name():
                parts[part.resolved_part_name()] = part
        interfaces = {interface.name: interface for interface in self.interfaces()}
        reference_points = {
            interface.name: interface
            for interface in self.interfaces()
            if interface.interface_type == "ReferencePoint" and interface.name
        }

        for interface in self.interfaces():
            for field, attr in INSTANCE_REFERENCE_FIELDS.items():
                current = getattr(interface, attr)
                if current not in instances.values():
                    interface.set_reference(
                        field,
                        instances.get(
                            current.name
                            if isinstance(current, InstanceNode)
                            else interface.pending_reference_name(field)
                        ),
                    )
            for field, attr in REFERENCE_POINT_FIELDS.items():
                current = getattr(interface, attr)
                if current not in reference_points.values():
                    interface.set_reference(
                        field,
                        reference_points.get(
                            current.name
                            if isinstance(current, InterfaceNode)
                            else interface.pending_reference_name(field)
                        ),
                    )

        for material in self.material_nodes():
            if material.part not in self.part_interfaces():
                target = parts.get(
                    material.part.resolved_part_name()
                    if isinstance(material.part, PartInterfaceNode)
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
                        if isinstance(key, InterfaceNode) and key in interfaces.values()
                        else interfaces.get(key.name if isinstance(key, InterfaceNode) else str(key))
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
                    if isinstance(item, InterfaceNode) and item in interfaces.values()
                    else interfaces.get(item.name if isinstance(item, InterfaceNode) else str(item))
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
                if current not in self.part_interfaces():
                    name = str(config.pop("part_name", "") or "").strip()
                    target = parts.get(current.name if isinstance(current, PartInterfaceNode) else name)
                    if target is None and not name and len(boundary) == 1:
                        target = boundary[0]
                    if target is not None:
                        config["target"] = target
                    else:
                        config.pop("target", None)
            for config in updater.materials:
                current = config.get("target")
                if current not in self.material_nodes():
                    name = str(config.pop("interface_name", "") or "").strip()
                    target = next(
                        (
                            material
                            for material in design_materials
                            if material.name
                            == (current.name if isinstance(current, MaterialNode) else name)
                        ),
                        None,
                    )
                    if target is None and not name and len(design_materials) == 1:
                        target = design_materials[0]
                    if target is not None:
                        config["target"] = target
                    else:
                        config.pop("target", None)

    def set_interface_reference(
        self, interface: InterfaceNode, field: str, value: Node | str | None
    ) -> bool:
        """Set one load-to-Instance or load-to-reference-point link."""
        if interface not in self.interfaces():
            return False
        if field in INSTANCE_REFERENCE_FIELDS:
            candidates = {
                instance.name: instance
                for part in self.part_interfaces()
                for instance in part.instances()
            }
            expected = InstanceNode
        elif field in REFERENCE_POINT_FIELDS:
            candidates = {
                item.name: item
                for item in self.interfaces()
                if item.interface_type == "ReferencePoint"
            }
            expected = InterfaceNode
        else:
            return False

        if value in (None, ""):
            interface.set_reference(field, None)
            return True
        target = value if isinstance(value, expected) else candidates.get(str(value))
        if target is None:
            return False
        if field in INSTANCE_REFERENCE_FIELDS and not isinstance(target, InstanceNode):
            return False
        if field in REFERENCE_POINT_FIELDS and (
            not isinstance(target, InterfaceNode)
            or target.interface_type != "ReferencePoint"
        ):
            return False
        interface.set_reference(field, target)
        return True

    def set_material_part(
        self, material: MaterialNode, value: PartInterfaceNode | str | None
    ) -> bool:
        """Bind one material interface to a geometry Part object."""
        if material not in self.material_nodes():
            return False
        if isinstance(value, PartInterfaceNode):
            target = value
        else:
            name = str(value or "").strip()
            target = next(
                (
                    part
                    for part in self.part_interfaces()
                    if name in {part.name, part.resolved_part_name()}
                ),
                None,
            )
        if target is None:
            return False
        material.set_part(target)
        return True

    def set_geometry_updater_target(
        self, config: dict, value: PartInterfaceNode | str | None
    ) -> bool:
        """Bind a geometry optimizer config to one boundary Part object."""
        if self.updater is None or config not in self.updater.geometry:
            return False
        target = value if isinstance(value, PartInterfaceNode) else self.part_interface_node(
            str(value or "").strip()
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
        target = value if isinstance(value, MaterialNode) else next(
            (material for material in self.material_nodes() if material.name == str(value or "")),
            None,
        )
        if target is None or target.name not in self.design_material_names():
            return False
        config["target"] = target
        config.pop("interface_name", None)
        return True

    def add_geometry_updater(self, target: PartInterfaceNode) -> dict:
        """Create a geometry optimizer bound directly to one boundary Part."""
        if self.updater is None or target not in self.boundary_part_nodes():
            raise ValueError("A geometry updater requires a boundary Part target")
        config = self.updater.add_geometry_config()
        config.pop("part_name", None)
        config["target"] = target
        return config

    def add_material_updater(self, target: MaterialNode) -> dict:
        """Create a material optimizer bound directly to one design material."""
        if self.updater is None or target.name not in self.design_material_names():
            raise ValueError("A material updater requires a design material target")
        config = self.updater.add_materials_config()
        config.pop("interface_name", None)
        config["target"] = target
        return config

    def set_jacobian_interfaces(
        self, values: list[InterfaceNode | str]
    ) -> None:
        """Bind the objective's Jacobian list to amplitude-load objects."""
        if self.objective is None:
            return
        available = {item.name: item for item in self.amplitude_interfaces()}
        self.objective.jacobian_needed = [
            item if isinstance(item, InterfaceNode) else available[str(item)]
            for item in values
            if isinstance(item, InterfaceNode) or str(item) in available
        ]

    # ------------------------------------------------------ tree mutations
    # These operations are deliberately owned by the aggregate root rather
    # than Qt widgets.  A surface's position affects both its ``flip`` flag
    # and the geometry updater's per-surface state, while an interface name
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
                count = len(node.surfaces())
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
        interface: PartInterfaceNode | None = None,
    ) -> SurfaceNode:
        """Insert ``surface`` and synchronise all surface-indexed state.

        ``interface`` selects the owning geometry interface; by default the
        last surface-carrying interface is used.
        """
        geometry = self._require_geometry()
        owner = interface or self.default_surface_part_node()
        if owner is None:
            raise ValueError(
                "This problem has no geometry interface that holds surfaces"
            )
        if owner not in geometry.interfaces():
            raise ValueError("The target geometry interface is not in the tree")

        surfaces = owner.surfaces()
        target_index = len(surfaces) if index is None else index
        if not 0 <= target_index <= len(surfaces):
            raise IndexError(f"Surface insertion index out of range: {target_index}")

        owner.add_surface(surface, index=target_index)
        self._insert_surface_state(owner, target_index)
        self.align_surface_dependent_state()
        self._refresh_surface_flags()
        return surface

    def default_surface_part_node(self) -> PartInterfaceNode | None:
        """Last geometry interface able to hold boundary surfaces."""
        candidates = self.boundary_part_nodes()
        return candidates[-1] if candidates else None

    def clone_surface(self, surface: SurfaceNode) -> SurfaceNode:
        """Duplicate ``surface`` directly below itself and return the copy."""
        geometry = self._require_geometry()
        owner = geometry.owner(surface)
        if owner is None:
            raise ValueError("The surface is not part of this problem")
        position = owner.surfaces().index(surface)
        clone = surface.clone()
        if not isinstance(clone, SurfaceNode):  # defensive for custom nodes
            raise TypeError("A surface clone must remain a SurfaceNode")
        return self.add_surface(clone, position + 1, interface=owner)

    def remove_surface(self, surface: SurfaceNode) -> None:
        """Remove one surface while preserving the remaining updater mapping."""
        geometry = self._require_geometry()
        owner = geometry.owner(surface)
        if owner is None:
            raise ValueError("The surface is not part of this problem")
        if len(geometry.surfaces()) <= 1:
            raise ValueError("A problem must keep at least one surface")
        position = owner.surfaces().index(surface)
        self._remove_surface_state(owner, position)
        owner.remove_child(surface)
        self.align_surface_dependent_state()
        self._refresh_surface_flags()

    def move_surface(self, surface: SurfaceNode, offset: int) -> bool:
        """Move a surface by ``offset`` positions inside its own interface."""
        geometry = self._require_geometry()
        owner = geometry.owner(surface)
        if owner is None:
            return False
        surfaces = owner.surfaces()
        source = surfaces.index(surface)
        target = source + offset
        if not 0 <= target < len(surfaces):
            return False
        left = owner.children.index(surface)
        right = owner.children.index(surfaces[target])
        owner.children[left], owner.children[right] = (
            owner.children[right],
            owner.children[left],
        )
        self._swap_surface_state(owner, source, target)
        self._refresh_surface_flags()
        return True

    def suggest_interface_name(self, prefix: str) -> str:
        """Return the first unused ``<prefix><number>`` interface name."""
        names = {interface.name for interface in self.interfaces()}
        index = 1
        while f"{prefix}{index}" in names:
            index += 1
        return f"{prefix}{index}"

    def suggest_part_interface_name(self, prefix: str = "part") -> str:
        """First unused geometry-interface (Part) name."""
        names = {interface.name for interface in self.part_interfaces()}
        index = 1
        while f"{prefix}{index}" in names:
            index += 1
        return f"{prefix}{index}"

    def suggest_instance_name(
        self, interface: PartInterfaceNode, prefix: str | None = None
    ) -> str:
        """Return the first unused Instance name in the Assembly."""
        base = (prefix or interface.resolved_part_name() or "instance").strip()
        names = {
            instance.name
            for part in self.part_interfaces()
            for instance in part.instances()
        }
        index = 1
        candidate = f"{base}-{index}"
        while candidate in names:
            index += 1
            candidate = f"{base}-{index}"
        return candidate

    def add_instance(
        self, interface: PartInterfaceNode, instance: InstanceNode
    ) -> InstanceNode:
        """Add one uniquely named Instance to a geometry Part."""
        if interface not in self.part_interfaces():
            raise ValueError("The target Part interface is not in the tree")
        name = instance.name.strip()
        if not name:
            raise ValueError("Instance name cannot be empty")
        if any(
            declared.name == name
            for part in self.part_interfaces()
            for declared in part.instances()
        ):
            raise ValueError(f"Instance {name!r} already exists in the Assembly")
        instance.name = name
        added = interface.add_instance(instance)
        self.resolve_references()
        return added

    def remove_instance(self, instance: InstanceNode) -> None:
        """Remove one Instance, keeping a Part's first identity Instance."""
        owner = self.owner_of_instance(instance)
        if owner is None:
            raise ValueError("The Instance is not part of this problem")
        if len(owner.instances()) <= 1:
            raise ValueError("A Part must keep at least one Instance")
        owner.remove_child(instance)
        for interface in self.interfaces():
            for field, attr in INSTANCE_REFERENCE_FIELDS.items():
                if getattr(interface, attr) is instance:
                    interface.set_reference(field, None)

    def move_instance(self, instance: InstanceNode, offset: int) -> bool:
        """Move an Instance in its Part's declaration order."""
        owner = self.owner_of_instance(instance)
        if owner is None:
            return False
        instances = owner.instances()
        source = instances.index(instance)
        target = source + offset
        if not 0 <= target < len(instances):
            return False
        positions = [
            index
            for index, child in enumerate(owner.children)
            if isinstance(child, InstanceNode)
        ]
        source_position, target_position = positions[source], positions[target]
        owner.children[source_position], owner.children[target_position] = (
            owner.children[target_position],
            owner.children[source_position],
        )
        return True

    def add_cad_operation(
        self, interface: PartInterfaceNode, operation: CADOperationNode
    ) -> CADOperationNode:
        """Append one CAD operation to a CAD Part's feature history."""
        if interface not in self.part_interfaces():
            raise ValueError("The target Part interface is not in the tree")
        if interface.interface_type != "CADPartInterface":
            raise TypeError("CAD operations can only belong to a CADPartInterface.")
        return interface.add_cad_operation(operation)

    def remove_cad_operation(self, operation: CADOperationNode) -> None:
        """Remove one CAD feature from its owning Part."""
        owner = self.owner_of_cad_operation(operation)
        if owner is None:
            raise ValueError("The CAD operation is not part of this problem")
        dependents = [
            item
            for item in owner.cad_operations()
            if item is not operation
            and operation.operation_id
            in (item.object_id, item.tool_id, item.input_id)
        ]
        if dependents:
            names = ", ".join(item.operation_id for item in dependents)
            raise ValueError(
                f"Cannot remove {operation.operation_id!r}; it is used by {names}."
            )
        owner.remove_child(operation)

    def move_cad_operation(self, operation: CADOperationNode, offset: int) -> bool:
        """Move one CAD feature without disturbing other Part children."""
        owner = self.owner_of_cad_operation(operation)
        if owner is None:
            return False
        feature_positions = [
            index
            for index, child in enumerate(owner.children)
            if isinstance(child, CADOperationNode)
        ]
        source_index = next(
            (index for index, child in enumerate(owner.cad_operations()) if child is operation),
            None,
        )
        if source_index is None:
            return False
        target_index = source_index + offset
        if not 0 <= target_index < len(feature_positions):
            return False
        source_position = feature_positions[source_index]
        target_position = feature_positions[target_index]
        owner.children[source_position], owner.children[target_position] = (
            owner.children[target_position],
            owner.children[source_position],
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
            for part in self.part_interfaces()
            for declared in part.instances()
        ):
            return False
        instance.name = new_name
        return True

    def add_part_interface(
        self, interface: PartInterfaceNode, index: int | None = None
    ) -> PartInterfaceNode:
        """Insert one geometry interface (Part + Instances) into the tree."""
        geometry = self._require_geometry()
        unnamed = not interface.name
        if not interface.name:
            interface.name = self.suggest_part_interface_name()
            instances = interface.instances()
            if (
                not interface.part_name
                and len(instances) == 1
                and instances[0].name in {"part-1", "part"}
            ):
                instances[0].name = f"{interface.name}-1"
        if any(item.name == interface.name for item in geometry.interfaces()):
            raise ValueError(f"Geometry interface {interface.name!r} already exists")

        used_instances = {
            instance.name
            for item in geometry.interfaces()
            for instance in item.instances()
        }
        for instance_index, instance in enumerate(interface.instances(), start=1):
            if instance.name not in used_instances:
                used_instances.add(instance.name)
                continue
            if not unnamed:
                raise ValueError(f"Instance {instance.name!r} already exists")
            base = interface.resolved_part_name() or interface.name or "part"
            candidate = f"{base}-{instance_index}"
            suffix = instance_index
            while candidate in used_instances:
                suffix += 1
                candidate = f"{base}-{suffix}"
            instance.name = candidate
            used_instances.add(candidate)
        geometry.add_interface(interface, index=index)
        self.resolve_references()
        self.align_surface_dependent_state()
        return interface

    def clone_part_interface(self, interface: PartInterfaceNode) -> PartInterfaceNode:
        """Duplicate a geometry interface (and its surfaces) below itself."""
        geometry = self._require_geometry()
        if interface not in geometry.children:
            raise ValueError("The geometry interface is not part of this problem")
        position = geometry.children.index(interface)
        clone = interface.clone()
        if not isinstance(clone, PartInterfaceNode):
            raise TypeError("A geometry clone must remain a PartInterfaceNode")
        clone.name = ""
        return self.add_part_interface(clone, index=position + 1)

    def remove_part_interface(self, interface: PartInterfaceNode) -> None:
        """Remove a geometry interface together with its surfaces."""
        geometry = self._require_geometry()
        if interface not in geometry.children:
            raise ValueError("The geometry interface is not part of this problem")
        if len(geometry.interfaces()) <= 1:
            raise ValueError("A problem must keep at least one geometry interface")
        surfaces = interface.surfaces()
        for _ in surfaces:
            self._remove_surface_state(interface, 0)
        for material in self.material_nodes():
            if material.part is interface:
                material.part = None
                material._part_name = ""
        if self.updater is not None:
            for config in self.updater.geometry:
                if config.get("target") is interface:
                    config.pop("target", None)
        for instance in interface.instances():
            for load in self.interfaces():
                for field, attr in INSTANCE_REFERENCE_FIELDS.items():
                    if getattr(load, attr) is instance:
                        load.set_reference(field, None)
        geometry.remove_child(interface)
        self.align_surface_dependent_state()
        self._refresh_surface_flags()

    def move_part_interface(self, interface: PartInterfaceNode, offset: int) -> bool:
        """Move a geometry interface by ``offset`` positions."""
        geometry = self._require_geometry()
        source = geometry.children.index(interface)
        target = source + offset
        if not 0 <= target < len(geometry.children):
            return False
        geometry.children[source], geometry.children[target] = (
            geometry.children[target],
            geometry.children[source],
        )
        return True

    def add_interface(
        self, interface: InterfaceNode, index: int | None = None
    ) -> InterfaceNode:
        """Insert an interface into the load section."""
        self._require_loads().add_interface(interface, index=index)
        self.resolve_references()
        return interface

    def add_material(
        self, material: MaterialNode, index: int | None = None
    ) -> MaterialNode:
        """Insert one material assignment into the Materials section."""
        section = self.materials
        if section is None:
            section = MaterialsNode(name="Materials")
            root = self.root
            insert_at = next(
                (
                    i
                    for i, child in enumerate(root.children)
                    if child.kind in {KIND_OBJECTIVE, KIND_SOLVER, KIND_UPDATER}
                ),
                len(root.children),
            )
            root.add_section(section, index=insert_at)
        section.add_material(material, index=index)
        if material.part is None and len(self.part_interfaces()) == 1:
            material.set_part(self.part_interfaces()[0])
        self.resolve_references()
        return material

    def clone_material(self, material: MaterialNode) -> MaterialNode:
        section = self.materials
        if section is None or material not in section.materials():
            raise ValueError("Material is not part of this problem.")
        clone = material.clone()
        if not isinstance(clone, MaterialNode):
            raise TypeError("A material clone must remain a MaterialNode")
        clone.name = f"{material.name}_copy" if material.name else ""
        names = {item.name for item in self.material_nodes()}
        base = clone.name or "material"
        index = 1
        while clone.name in names:
            clone.name = f"{base}_{index}"
            index += 1
        return self.add_material(clone, section.children.index(material) + 1)

    def remove_material(self, material: MaterialNode) -> None:
        section = self.materials
        if section is None or material not in section.materials():
            raise ValueError("Material is not part of this problem.")
        if len(section.materials()) <= 1:
            raise ValueError("A problem must keep at least one material interface")
        section.remove_child(material)
        if self.updater is not None:
            for config in self.updater.materials:
                if config.get("target") is material:
                    config.pop("target", None)

    def move_material(self, material: MaterialNode, offset: int) -> bool:
        section = self.materials
        if section is None or material not in section.materials():
            return False
        source = section.children.index(material)
        target = source + offset
        if not 0 <= target < len(section.children):
            return False
        section.children[source], section.children[target] = (
            section.children[target],
            section.children[source],
        )
        return True

    def clone_interface(
        self, interface: InterfaceNode, name_prefix: str
    ) -> InterfaceNode:
        """Duplicate an interface below itself under a fresh reference name."""
        loads = self._require_loads()
        clone = interface.clone()
        if not isinstance(clone, InterfaceNode):  # defensive for custom nodes
            raise TypeError("An interface clone must remain an InterfaceNode")
        clone.name = self.suggest_interface_name(name_prefix)
        return self.add_interface(clone, loads.children.index(interface) + 1)

    def move_interface(self, interface: InterfaceNode, offset: int) -> bool:
        """Move an interface by ``offset`` positions without changing its name."""
        loads = self._require_loads()
        source = loads.children.index(interface)
        target = source + offset
        if not 0 <= target < len(loads.children):
            return False
        loads.children[source], loads.children[target] = (
            loads.children[target],
            loads.children[source],
        )
        return True

    def remove_interface(self, interface: InterfaceNode) -> None:
        """Remove an interface and every reference to its name."""
        self._require_loads().remove_child(interface)
        if self.steps is not None:
            for values in self.steps.step_values:
                values.pop(interface, None)
        if self.objective is not None:
            self.objective.jacobian_needed = [
                item for item in self.objective.jacobian_needed if item is not interface
            ]
        for load in self.interfaces():
            for field, attr in REFERENCE_POINT_FIELDS.items():
                if getattr(load, attr) is interface:
                    load.set_reference(field, None)

    def rename_interface(
        self,
        interface: InterfaceNode | PartInterfaceNode | MaterialNode,
        new_name: str,
    ) -> bool:
        """Rename one named model interface and cascade its references.

        Geometry, material, and load interfaces deliberately share this
        entry point.  Their names belong to separate collections, but each
        may be referenced elsewhere in the problem definition.  Keeping the
        dispatch here prevents Qt editors from having to know those links.
        Existing object references follow their target automatically; only the
        persisted/UI name projection changes.
        """
        if isinstance(interface, PartInterfaceNode):
            return self._rename_part_interface(interface, new_name)
        if isinstance(interface, MaterialNode):
            return self._rename_material_interface(interface, new_name)
        if isinstance(interface, InterfaceNode):
            return self._rename_load_interface(interface, new_name)
        return False

    def rename_part(self, interface: PartInterfaceNode, part_name: str) -> bool:
        """Rename a generated Assembly Part and its identity Instance.

        ``part_name`` may be empty, in which case the Part again follows the
        geometry-interface name.  Only the conventional identity instance
        (``<part>-1``) follows this change;
        explicitly named instances retain both their names and their poses.
        """
        if interface not in self.part_interfaces():
            return False
        if interface.interface_type == "TorchFEAPartInterface":
            # The archive owns the physical Part name.  Its UI interface may
            # still be renamed through ``rename_interface`` above.
            return False

        old_part_name = interface.resolved_part_name()
        part_name = part_name.strip()
        new_part_name = part_name or interface.name.strip()
        if not new_part_name:
            return False
        if part_name == interface.part_name:
            return False
        if any(
            item is not interface and item.resolved_part_name() == new_part_name
            for item in self.part_interfaces()
        ):
            return False
        if not self._can_rename_default_instance(
            interface, old_part_name, new_part_name
        ):
            return False

        interface.part_name = part_name
        self._rename_default_instance(interface, old_part_name, new_part_name)
        return True

    def _rename_load_interface(
        self, interface: InterfaceNode, new_name: str
    ) -> bool:
        """Rename one load interface; object references follow automatically."""
        if interface not in self.interfaces():
            return False
        new_name = new_name.strip()
        old_name = interface.name
        if not new_name or new_name == old_name:
            return False
        if any(
            item is not interface and item.name == new_name
            for item in self.interfaces()
        ):
            return False

        interface.name = new_name
        return True

    def _rename_part_interface(
        self, interface: PartInterfaceNode, new_name: str
    ) -> bool:
        """Rename a geometry interface while its dependants retain the object."""
        if interface not in self.part_interfaces():
            return False
        new_name = new_name.strip()
        old_name = interface.name
        if not new_name or new_name == old_name:
            return False
        if any(
            item is not interface and item.name == new_name
            for item in self.part_interfaces()
        ):
            return False

        old_part_name = interface.resolved_part_name()
        # A TorchFEA-interface name is only MorphOpt's registration key.  Its
        # actual Part and Instance names are owned by the imported archive;
        # treating it as a physical-Part rename would make load references
        # disagree with the archive on the next synchronization.
        imported_part = interface.interface_type == "TorchFEAPartInterface"
        new_part_name = (
            old_part_name
            if imported_part
            else (interface.part_name or new_name).strip()
        )
        if not self._can_rename_default_instance(
            interface, old_part_name, new_part_name
        ):
            return False

        interface.name = new_name
        if imported_part:
            # Persist the archive Part explicitly before the registration
            # name changes, otherwise ``resolved_part_name()`` would fall
            # back to the newly edited interface name.
            interface.part_name = old_part_name
        self._rename_default_instance(interface, old_part_name, new_part_name)
        return True

    def _rename_material_interface(
        self, interface: MaterialNode, new_name: str
    ) -> bool:
        """Rename a material interface while its updater retains the object."""
        if interface not in self.material_nodes():
            return False
        new_name = new_name.strip()
        old_name = interface.name
        if not new_name or new_name == old_name:
            return False
        if any(
            item is not interface and item.name == new_name
            for item in self.material_nodes()
        ):
            return False

        interface.name = new_name
        return True

    def _can_rename_default_instance(
        self,
        interface: PartInterfaceNode,
        old_part_name: str,
        new_part_name: str,
    ) -> bool:
        """Whether following the identity Instance would keep names unique."""
        default = self._default_instance(interface, old_part_name)
        if default is None or old_part_name == new_part_name:
            return True
        target_name = f"{new_part_name}-1"
        return not any(
            instance is not default and instance.name == target_name
            for part in self.part_interfaces()
            for instance in part.instances()
        )

    @staticmethod
    def _default_instance(
        interface: PartInterfaceNode, part_name: str
    ) -> InstanceNode | None:
        """Return the conventional identity Instance, if it still exists."""
        conventional = f"{part_name}-1"
        return next(
            (instance for instance in interface.instances() if instance.name == conventional),
            None,
        )

    def _rename_default_instance(
        self,
        interface: PartInterfaceNode,
        old_part_name: str,
        new_part_name: str,
    ) -> None:
        """Rename only the conventional identity Instance of a Part."""
        if old_part_name == new_part_name:
            return
        default = self._default_instance(interface, old_part_name)
        if default is not None:
            default.name = f"{new_part_name}-1"

    # ---------------------------------------------------- mutation helpers
    def _require_geometry(self) -> GeometryNode:
        if self.geometry is None:
            raise ValueError("This problem has no geometry section")
        return self.geometry

    def _require_loads(self) -> LoadsNode:
        if self.loads is None:
            raise ValueError("This problem has no loads section")
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
                rows.append([item if isinstance(item, str) else float(item) for item in row])
            elif isinstance(row, (int, float)):
                rows.append([float(row)])
            else:
                return None
        size = max(len(rows), max((len(row) for row in rows), default=0))
        return [
            [
                rows[row_index][column_index]
                if row_index < len(rows) and column_index < len(rows[row_index])
                else 2.5
                for column_index in range(size)
            ]
            for row_index in range(size)
        ]

    @staticmethod
    def _resize_matrix(matrix: list[list[float | str]], size: int) -> list[list[float | str]]:
        return [
            [
                matrix[row_index][column_index]
                if row_index < len(matrix) and column_index < len(matrix[row_index])
                else 2.5
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

    def part_interface_node(self, name: str) -> PartInterfaceNode | None:
        """Boundary part-interface node by name (``None`` when unknown)."""
        if not name:
            return None
        return next(
            (node for node in self.part_interfaces() if node.name == name), None
        )

    def config_part_node(self, config: dict) -> PartInterfaceNode | None:
        """Boundary Part object bound to a geometry sub-optimizer config."""
        target = config.get("target") if config is not None else None
        return target if isinstance(target, PartInterfaceNode) else None

    def config_material_node(self, config: dict) -> MaterialNode | None:
        """Design-material object bound to a material sub-optimizer config."""
        target = config.get("target") if config is not None else None
        return target if isinstance(target, MaterialNode) else None

    def _geometry_config_for_part(self, part: PartInterfaceNode) -> dict | None:
        """Return the geometry updater config targeting ``part``."""
        updater = self.updater
        if updater is None:
            return None
        for config in updater.geometry:
            if self.config_part_node(config) is part:
                return config
        return None

    def _insert_surface_state(self, part: PartInterfaceNode, index: int) -> None:
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
            matrix.insert(index, [2.5] * (len(matrix) + 1))
            for row_index, row in enumerate(matrix):
                if row_index != index:
                    row.insert(index, 2.5)
            parameters["min_distance"] = matrix

    def _remove_surface_state(self, part: PartInterfaceNode, index: int) -> None:
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

    def _swap_surface_state(
        self, part: PartInterfaceNode, first: int, second: int
    ) -> None:
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
            for index, surface in enumerate(part.surfaces()):
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
            raise ValueError(f"Unsupported .morph version: {data.get('version')}")
        root = Node.from_dict(data["root"])
        problem = cls(
            scheme=data["scheme"],
            label=data.get("label", "Untitled"),
            result_folder=data.get("result_folder", ".results/"),
            device=data.get("device", "cpu"),
            updater_device=data.get("updater_device"),
            restart_per_iteration=data.get("restart_per_iteration", 10),
            root=root,
            custom_classes=[Node.from_dict(node) for node in data.get("custom_classes", [])],
            class_bindings=data.get("class_bindings", {}),
            helper_code=data["helper_code"],
            helper_variables=[Node.from_dict(node) for node in data["helper_variables"]],
            helper_functions=[Node.from_dict(node) for node in data["helper_functions"]],
        )
        problem.resolve_references()
        return problem
