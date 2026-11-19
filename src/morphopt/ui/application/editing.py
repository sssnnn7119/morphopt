"""Definition construction and editing policies shared by all UI entry points."""

from __future__ import annotations

from ..i18n import localized_message
from ..model.node_types.parts import BoundaryPartNode, CADPartNode, INPPartNode
from ..model.problem import (
    CADOperationNode,
    CustomClassNode,
    CustomFunctionNode,
    FEAComponentNode,
    HelperFunctionNode,
    HelperVariableNode,
    LoadCaseNode,
    MaterialNode,
    MethodOverrideNode,
    Node,
    PartNode,
    ProblemDefinition,
    SolverNode,
    StepsNode,
    SurfaceNode,
)
from ..model.registry import (
    LOAD_TYPES,
    PART_TYPES,
)
from .part_sets import PartSetCatalog
from .updaters import symmetry_item, updater_item


class DefinitionCommands:
    """Construct nodes with registered defaults; domain objects own links.

    This service contains no dialogs or selection/rendering behavior. It can be
    used from a script as well as from the Qt action controller.
    """

    def __init__(self, problem: ProblemDefinition):
        """Initialize DefinitionCommands and its configuration state.

        Args:
            problem (ProblemDefinition): Editable problem definition shared by the UI application
                services.
        """
        self.problem = problem

    def add_helper(self, kind: str) -> Node:
        """Add helper.

        Args:
            kind (str): Registered category or provider identifier used to dispatch the operation.

        Returns:
            Node: Add helper.
        """
        types = {
            "helper_variable": (HelperVariableNode, "constant", {"value": "None"}),
            "helper_function": (
                HelperFunctionNode,
                "helper",
                {"parameters": "", "body": "pass"},
            ),
        }
        node_type, base, params = types[kind]
        taken = {
            item.name
            for item in self.problem.helper_variables + self.problem.helper_functions
        }
        index = 1
        while f"{base}_{index}" in taken:
            index += 1
        node = node_type(name=f"{base}_{index}", params=params)
        entries = (
            self.problem.helper_variables
            if kind == "helper_variable"
            else self.problem.helper_functions
        )
        entries.append(node)
        return node

    def remove_helper(self, node: Node) -> str:
        """Remove helper.

        Args:
            node (Node): Definition node being inspected or edited.

        Returns:
            str: Remove helper.
        """
        entries = (
            self.problem.helper_variables
            if node.kind == "helper_variable"
            else self.problem.helper_functions
        )
        entries.remove(node)
        return (
            "helper_variables_group"
            if node.kind == "helper_variable"
            else "helper_functions_group"
        )

    def move_helper(self, node: Node, delta: int) -> bool:
        """Move helper.

        Args:
            node (Node): Definition node being inspected or edited.
            delta (int): Signed collection displacement; -1 moves up and +1 moves down.

        Returns:
            bool: Move helper.
        """
        entries = (
            self.problem.helper_variables
            if node.kind == "helper_variable"
            else self.problem.helper_functions
        )
        index = entries.index(node)
        target = index + delta
        if not 0 <= target < len(entries):
            return False
        entries.insert(target, entries.pop(index))
        return True

    def add_part(self, part_type: str, custom_class: str = "") -> PartNode:
        """Add part.

        Args:
            part_type (str): Registered Part implementation type.
            custom_class (str): Name of the compatible custom class selected for this interface.

        Returns:
            PartNode: Add part.
        """
        name = self.problem.suggest_part_name()
        if PART_TYPES[part_type].custom_only and not custom_class:
            raise ValueError(
                localized_message(
                    "ui.errors.editing.value_requires_a_custom_class",
                    value_0=part_type,
                )
            )
        node = PartNode.create(part_type, name=name)
        node.custom_class = custom_class
        self.problem.add_part(node)
        return node

    def add_surface(
        self,
        surface_type: str,
        owner: BoundaryPartNode,
        custom_class: str = "",
    ) -> SurfaceNode:
        """Add surface.

        Args:
            surface_type (str): Registered boundary-surface implementation type.
            owner (BoundaryPartNode): Owning definition node or collection.
            custom_class (str): Name of the compatible custom class selected for this interface.

        Returns:
            SurfaceNode: Add surface.
        """
        node = SurfaceNode.create(surface_type)
        node.custom_class = custom_class
        self.problem.add_surface(node, part=owner)
        return node

    def add_component(
        self, component_type: str, custom_class: str = ""
    ) -> FEAComponentNode:
        """Add component.

        Args:
            component_type (str): Registered load or boundary-condition interface type.
            custom_class (str): Name of the compatible custom class selected for this interface.

        Returns:
            FEAComponentNode: Add component.
        """
        reference_fields = {
            "instance_name", "instance_name1", "instance_name2",
            "surface_name", "surface_name1", "surface_name2", "set_nodes_name",
        }
        node = FEAComponentNode.create(component_type, **{
            field.key: "" for field in LOAD_TYPES[component_type].fields
            if field.key in reference_fields
        })
        node.custom_class = custom_class
        node.name = self.problem.suggest_component_name(node.name_hint)
        self.problem.add_component(node)
        return node

    def add_material(self, material_type: str, custom_class: str = "") -> MaterialNode:
        """Add material.

        Args:
            material_type (str): Registered material-interface implementation type.
            custom_class (str): Name of the compatible custom class selected for this interface.

        Returns:
            MaterialNode: Add material.
        """
        node = MaterialNode.create(material_type)
        names = {material.name for material in self.problem.material_nodes()}
        index = 1
        while f"material_{index}" in names:
            index += 1
        node.name = f"material_{index}"
        node.custom_class = custom_class
        self.problem.add_material(node)
        parts = self.problem.parts()
        if len(parts) == 1:
            set_node_field(node, "part_name", parts[0], self.problem)
        return node

    def next_operation_id(self, owner: CADPartNode, operation_type: str) -> str:
        """Return next operation id.

        Args:
            owner (CADPartNode): Owning definition node or collection.
            operation_type (str): Registered CAD feature type used to create the operation.

        Returns:
            str: Next operation id.
        """
        used = {item.operation_id for item in owner.operations}
        index = 1
        while f"{operation_type}-{index}" in used:
            index += 1
        return f"{operation_type}-{index}"

    def add_cad_operation(
        self,
        owner: CADPartNode,
        operation_type: str,
        operation_id: str,
        **values,
    ) -> CADOperationNode:
        """Add cad operation.

        Args:
            owner (CADPartNode): Owning definition node or collection.
            operation_type (str): Registered CAD feature type used to create the operation.
            operation_id (str): Stable identifier of the CAD history operation.
            **values: Additional keyword arguments accepted by the shared interface.

        Returns:
            CADOperationNode: Add cad operation.
        """
        node = CADOperationNode.create(operation_type, operation_id, **values)
        self.problem.add_cad_operation(owner, node)
        return node

    def available_optimizer_targets(self) -> list[PartNode | MaterialNode]:
        """Actual components that can receive a new updater, in model order.

        Returns:
            list[PartNode | MaterialNode]: Actual components that can receive a new updater, in
                model order.
        """
        if self.problem.updater is None:
            return []
        candidates = [
            node
            for node in self.problem.parts() + self.problem.material_nodes()
            if node.is_updatable
        ]
        taken = {
            *(
                self.problem.config_part_node(config)
                for config in self.problem.updater.geometry
            ),
            *(
                self.problem.config_material_node(config)
                for config in self.problem.updater.materials
            ),
        }
        return [node for node in candidates if node not in taken]

    @staticmethod
    def add_updater_item(config: dict, item_type: str, category: str) -> None:
        """Add updater item.

        Args:
            config (dict): Configuration dictionary for the selected model or updater interface.
            item_type (str): Registered interface type used to create a new collection item.
            category (str): Interface or asset category used to select compatible editors or
                renderers.
        """
        key = "objective_functions" if category == "objectives" else "constraints"
        config.setdefault(key, []).append(updater_item(item_type, category))

    def add_symmetry_constraint(self, config: dict, item_type: str) -> bool:
        """Add symmetry constraint.

        Args:
            config (dict): Configuration dictionary for the selected model or updater interface.
            item_type (str): Registered interface type used to create a new collection item.

        Returns:
            bool: Add symmetry constraint.
        """
        target = self.problem.config_part_node(config)
        surfaces = target.surfaces if target is not None else []
        item = symmetry_item(item_type, surfaces)
        if item is None:
            return False
        config.setdefault("symmetry_constraints", []).append(item)
        return True


def set_node_field(
    node: Node, key: str, value, problem: ProblemDefinition | None = None
) -> bool:
    """Apply fields through aggregate reference/rename rules, never through widgets.

    Args:
        node (Node): Definition node being inspected or edited.
        key (str): Lookup key identifying the requested field or registered item.
        value: Value assigned to or evaluated for the selected field.
        problem (ProblemDefinition | None): Editable problem definition shared by the UI
            application services.

    Returns:
        bool: Apply fields through aggregate reference/rename rules, never through widgets.
    """
    from ..model.problem import INSTANCE_REFERENCE_FIELDS, REFERENCE_POINT_FIELDS

    if problem is not None:
        if isinstance(node, LoadCaseNode):
            load, field = node.parameters()[key]
            return LoadCaseSession(node.steps, problem).set_parameter(node.name, load, field.key, value)
        if isinstance(node, FEAComponentNode) and node.type == "PenaltyDoF" and key in {"node_index", "direction"}:
            try:
                node.set_field(key, value)
            except ValueError:
                return False
            return True
        if isinstance(node, FEAComponentNode) and node.type == "PenaltyDoF" and key in {"obj_type", "obj_name"}:
            from .fields import penalty_targets

            previous = node.obj_name
            node.set_field(key, value)
            if node.obj_name not in penalty_targets(problem, node):
                node.obj_name = ""
            if node.obj_name != previous:
                node.s = 0
            return True
        if isinstance(node, FEAComponentNode) and key in {
            *INSTANCE_REFERENCE_FIELDS,
            *REFERENCE_POINT_FIELDS,
        }:
            return problem.set_component_reference(node, key, value)
        if key == "part_name" and isinstance(node, MaterialNode):
            previous_part = node.part
            if not problem.set_material_part(node, value):
                return False
            if node.is_updatable and node.part is not previous_part:
                from ..visualization.geometry import PreviewGeometry
                from ..visualization.scene import MessageItem

                scene = PreviewGeometry().build(problem, "part", node.part)
                bounds = (
                    None
                    if any(isinstance(item, MessageItem) for item in scene.items)
                    else scene.bounds
                )
                node.bounding_box = list(bounds) if bounds is not None else [0.0] * 6
            return True
    node.set_field(key, value)
    if isinstance(node, INPPartNode) and key in {"mesh_file", "inp_part_name"}:
        parts = PartSetCatalog.inp_parts(node.mesh_file)
        if node.inp_part_name not in parts:
            node.inp_part_name = next(iter(parts)) if len(parts) == 1 else ""
        if node.exterior_surface not in PartSetCatalog.inp(node).surfaces:
            node.exterior_surface = ""
    return True


def rename_node(
    node: Node, name: str, problem: ProblemDefinition | None = None
) -> bool:
    """Return rename node.

    Args:
        node (Node): Definition node being inspected or edited.
        name (str): Name identifying the item in its owning collection.
        problem (ProblemDefinition | None): Editable problem definition shared by the UI
            application services.

    Returns:
        bool: Rename node.
    """
    name = name.strip()
    if not name or name == node.name:
        return False
    if problem is not None:
        if isinstance(node, LoadCaseNode):
            try:
                LoadCaseSession(node.steps, problem).rename(node.name, name)
            except ValueError:
                return False
            return True
        if node.kind == "instance":
            return problem.rename_instance(node, name)
        return problem.rename_definition(node, name)
    node.name = name
    return True


class HelperCodeSession:
    """Bind and validate an editable helper definition without UI state."""

    def __init__(self, problem: ProblemDefinition, node: Node | None):
        """Initialize HelperCodeSession and its configuration state.

        Args:
            problem (ProblemDefinition): Editable problem definition shared by the UI application
                services.
            node (Node | None): Definition node being inspected or edited.
        """
        self.problem, self.node = problem, node

    def save(self, name: str, value: str, parameters: str, body: str) -> None:
        """Save the HelperCodeSession state.

        Args:
            name (str): Name identifying the item in its owning collection.
            value (str): Value assigned to or evaluated for the selected field.
            parameters (str): Parameter values in the order required by the selected interface.
            body (str): Source-code body or geometry body processed by the operation.
        """
        node = self.node
        if node is None:
            return
        if node.kind == "helper_code_block":
            self.problem.helper_code = body
        elif node.kind in {"helper_variable", "helper_function"}:
            if name.strip():
                node.name = name.strip()
            if node.kind == "helper_variable":
                node.value = value
            else:
                node.parameters, node.body = parameters, body

    def validate(self) -> None:
        """Validate the HelperCodeSession state."""
        import ast
        import keyword
        from textwrap import indent

        node = self.node
        if node is None:
            return
        if node.kind == "helper_code_block":
            compile(self.problem.helper_code, "<helper code>", "exec")
        elif node.kind in {"helper_variable", "helper_function"}:
            if not node.name.isidentifier() or keyword.iskeyword(node.name):
                raise ValueError(
                    localized_message(
                        "ui.errors.editing.helper_names_must_be_valid_python_identifiers"
                    )
                )
            if node.kind == "helper_variable":
                ast.parse(node.value, mode="eval")
            else:
                compile(
                    f"def {node.name}({node.parameters}):\n{indent(node.body or 'pass', '    ')}",
                    "<helper function>",
                    "exec",
                )


class CustomClassSession:
    """Edit reusable classes and update every use through one reference policy."""

    def __init__(self, problem: ProblemDefinition):
        """Initialize CustomClassSession and its configuration state.

        Args:
            problem (ProblemDefinition): Editable problem definition shared by the UI application
                services.
        """
        self.problem = problem

    def catalog(self):
        """Handle catalog for CustomClassSession."""
        from ..codegen.custom_classes import framework_class_catalog

        return framework_class_catalog(self.problem)

    def validate_name(self, name: str, current: CustomClassNode | None = None) -> None:
        """Validate name.

        Args:
            name (str): Name identifying the item in its owning collection.
            current (CustomClassNode | None): Currently selected value retained while choices are
                rebuilt.
        """
        from ..codegen.custom_classes import validate_custom_name

        validate_custom_name(name, self.catalog())
        if any(
            node is not current and node.name == name
            for node in self.problem.custom_classes
        ):
            raise ValueError(
                localized_message(
                    "ui.errors.editing.class_name_already_exists_value", value_0=name
                )
            )

    def add_class(
        self, name: str, base: str = "", class_type: str = "override"
    ) -> CustomClassNode:
        """Add class.

        Args:
            name (str): Name identifying the item in its owning collection.
            base (str): Base class or root configuration from which the selected declaration is
                constructed.
            class_type (str): Framework or custom class selected for this declaration.

        Returns:
            CustomClassNode: Add class.
        """
        from ..model.problem import CustomClassNode

        if class_type not in {"new", "override"}:
            raise ValueError(f"Unsupported custom class type: {class_type}")
        self.validate_name(name)
        node = CustomClassNode(
            name=name,
            params={"base_class": base, "class_type": class_type},
        )
        self.problem.custom_classes.append(node)
        return node

    def _replace_uses(self, old: str, new: str) -> None:
        problem = self.problem
        problem.class_bindings = {
            path: new if name == old else name
            for path, name in problem.class_bindings.items()
            if new or name != old
        }
        for node in problem.root.iter_nodes():
            if node.custom_class == old:
                node.custom_class = new
        if problem.updater is not None:
            for config in problem.updater.geometry + problem.updater.materials:
                if config.get("custom_class") == old:
                    if new:
                        config["custom_class"] = new
                    else:
                        config.pop("custom_class", None)
                for key in ("objective_functions", "constraints"):
                    for item in config.get(key, []):
                        if item.get("custom_class") == old:
                            if new:
                                item["custom_class"] = new
                            else:
                                item.pop("custom_class", None)

    def rename(self, node: CustomClassNode, name: str) -> bool:
        """Return rename.

        Args:
            node (CustomClassNode): Definition node being inspected or edited.
            name (str): Name identifying the item in its owning collection.

        Returns:
            bool: Rename.
        """
        self.validate_name(name, current=node)
        if name == node.name:
            return False
        old, node.name = node.name, name
        self._replace_uses(old, name)
        return True

    def dependent_classes(self, node: CustomClassNode) -> list[CustomClassNode]:
        """Classes whose inheritance chain includes the selected custom class.

        Args:
            node (CustomClassNode): Definition node being inspected or edited.

        Returns:
            list[CustomClassNode]: Classes whose inheritance chain includes the selected custom
                class.
        """
        names = {node.name}
        while True:
            children = {
                custom.name
                for custom in self.problem.custom_classes
                if custom.base_class in names
            }
            if children <= names:
                break
            names.update(children)
        return [
            custom
            for custom in self.problem.custom_classes
            if custom is not node and custom.name in names
        ]

    def remove(
        self, node: CustomClassNode | MethodOverrideNode | CustomFunctionNode
    ) -> CustomClassNode | None:
        """Remove the CustomClassSession state.

        Args:
            node (CustomClassNode | MethodOverrideNode | CustomFunctionNode): Definition node being
                inspected or edited.

        Returns:
            CustomClassNode | None: Remove the CustomClassSession state.
        """
        from ..model.problem import CustomClassNode

        if isinstance(node, CustomClassNode):
            for custom in [node, *self.dependent_classes(node)]:
                self.problem.custom_classes.remove(custom)
                self._replace_uses(custom.name, "")
            return None
        owner = next(
            custom for custom in self.problem.custom_classes if node in custom.members
        )
        owner.remove_child(node)
        return owner

    @staticmethod
    def add_override(custom: CustomClassNode, spec) -> MethodOverrideNode:
        """Add override.

        Args:
            custom (CustomClassNode): Custom-class declaration selected for this framework
                interface.
            spec: Field or interface schema describing valid values and available controls.

        Returns:
            MethodOverrideNode: Add override.
        """
        from ..model.problem import MethodOverrideNode

        override = MethodOverrideNode(name=spec.name, params={"body": spec.body})
        custom.add_child(override)
        return override

    @staticmethod
    def add_function(
        custom: CustomClassNode, name: str, parameters: str = "self"
    ) -> CustomFunctionNode:
        """Add function.

        Args:
            custom (CustomClassNode): Custom-class declaration selected for this framework
                interface.
            name (str): Name identifying the item in its owning collection.
            parameters (str): Parameter values in the order required by the selected interface.

        Returns:
            CustomFunctionNode: Add function.
        """
        function = CustomFunctionNode(
            name=name,
            params={"parameters": parameters, "body": "pass"},
        )
        custom.add_child(function)
        return function

    @staticmethod
    def move_member(custom: CustomClassNode, node: Node, delta: int) -> bool:
        """Move member.

        Args:
            custom (CustomClassNode): Custom-class declaration selected for this framework
                interface.
            node (Node): Definition node being inspected or edited.
            delta (int): Signed collection displacement; -1 moves up and +1 moves down.

        Returns:
            bool: Move member.
        """
        index = custom.members.index(node)
        target = index + delta
        if not 0 <= target < len(custom.members):
            return False
        custom.members.insert(target, custom.members.pop(index))
        return True

    @staticmethod
    def validate_body(override: MethodOverrideNode, spec) -> None:
        """Validate body.

        Args:
            override (MethodOverrideNode): Framework method selected for a custom implementation.
            spec: Field or interface schema describing valid values and available controls.
        """
        from textwrap import indent

        compile(
            spec.header
            + "\n"
            + indent(override.body if override.body.strip() else "pass", "    "),
            "<method body>",
            "exec",
        )

    @staticmethod
    def validate_function(function: CustomFunctionNode) -> None:
        """Validate function.

        Args:
            function (CustomFunctionNode): Callable registered or evaluated by this operation.
        """
        import keyword
        from textwrap import indent

        if not function.name.isidentifier() or keyword.iskeyword(function.name):
            raise ValueError(
                localized_message(
                    "ui.errors.custom_classes.invalid_custom_function_name"
                )
            )
        compile(
            f"def {function.name}({function.parameters}):\n"
            + indent(function.body if function.body.strip() else "pass", "    "),
            "<custom class function>",
            "exec",
        )


class LoadCaseSession:
    """Named case operations and amplitude editing, independent of widgets."""

    def __init__(self, steps: StepsNode, problem: ProblemDefinition) -> None:
        """Initialize LoadCaseSession and its configuration state.

        Args:
            steps (StepsNode): Named load-case definitions in registration order.
            problem (ProblemDefinition): Editable problem definition shared by the UI application
                services.
        """
        self.steps, self.problem = steps, problem

    def add(self) -> str:
        """Add the LoadCaseSession state.

        Returns:
            str: Add the LoadCaseSession state.
        """
        index = 1
        while f"load_case_{index}" in self.steps.step_values:
            index += 1
        name = f"load_case_{index}"
        self.steps.step_values[name] = {}
        return name

    def rename(self, name: str, new_name: str) -> None:
        """Return rename.

        Args:
            name (str): Name identifying the item in its owning collection.
            new_name (str): Replacement name for the selected registered item.
        """
        from .load_cases import rename_case

        rename_case(self.problem, name, new_name)

    def move(self, name: str, delta: int) -> bool:
        """Move the LoadCaseSession state.

        Args:
            name (str): Name identifying the item in its owning collection.
            delta (int): Signed collection displacement; -1 moves up and +1 moves down.

        Returns:
            bool: Move the LoadCaseSession state.
        """
        names = list(self.steps.step_values)
        index = names.index(name)
        target = index + delta
        if not 0 <= target < len(names):
            return False
        names[index], names[target] = names[target], names[index]
        self.steps.step_values = {key: self.steps.step_values[key] for key in names}
        return True

    def remove(
        self, name: str, *, remove_objectives: bool, remove_unused: bool
    ) -> None:
        """Remove the LoadCaseSession state.

        Args:
            name (str): Name identifying the item in its owning collection.
            remove_objectives (bool): Delete objectives referencing the removed load case when True;
                otherwise clear their case selection.
            remove_unused (bool): Remove generated load cases that have no remaining references when
                True.
        """
        from .load_cases import remove_case

        remove_case(self.problem, name, remove_objectives, remove_unused)

    def value(self, name: str, component: FEAComponentNode, key: str) -> float | str:
        """Return value.

        Args:
            name (str): Name identifying the item in its owning collection.
            component (FEAComponentNode): Model, result, or interface component processed by the
                operation.
            key (str): Lookup key identifying the requested field or registered item.

        Returns:
            float | str: Value.
        """
        index = next(i for i, field in enumerate(component.value_fields) if field.key == key)
        values = self.steps.step_values[name].get(component, [])
        return values[index] if index < len(values) else component.value_fields[index].new_default()

    def set_parameter(
        self, name: str, component: FEAComponentNode, key: str, value: float | str,
    ) -> bool:
        """Change one named scalar without rewriting the load's other values.

        Args:
            name (str): Name identifying the item in its owning collection.
            component (FEAComponentNode): Model, result, or interface component processed by the
                operation.
            key (str): Lookup key identifying the requested field or registered item.
            value (float | str): Value assigned to or evaluated for the selected field.

        Returns:
            bool: Change one named scalar without rewriting the load's other values.
        """
        if name not in self.steps.step_values:
            return False
        constants = {constant.name for constant in self.problem.helper_variables}
        if isinstance(value, str) and value not in constants:
            return False
        fields = component.value_fields
        values = [self.value(name, component, field.key) for field in fields]
        index = next(i for i, field in enumerate(fields) if field.key == key)
        values[index] = value
        self.steps.step_values[name][component] = values
        return True


class SolverTasks:
    """Read and write ordered load-case sequences for each process group."""

    def __init__(self, solver: SolverNode, problem: ProblemDefinition):
        """Initialize SolverTasks and its configuration state.

        Args:
            solver (SolverNode): Solver configuration whose devices and ordered task groups are
                edited.
            problem (ProblemDefinition): Editable problem definition shared by the UI application
                services.
        """
        self.solver, self.problem = solver, problem

    def groups(self) -> list[list[str]]:
        """Return each group's ordered cases; an empty definition means one per case.

        Returns:
            list[list[str]]: Each group's ordered cases; an empty definition means one per case.
        """
        names = (
            list(self.problem.steps.step_values)
            if self.problem.steps is not None
            else []
        )
        registered = set(names)
        included: set[str] = set()
        groups: list[list[str]] = []
        for steps in self.solver.task_step_list:
            group = []
            for name in steps:
                if name in registered and name not in included:
                    group.append(name)
                    included.add(name)
            if group:
                groups.append(group)
        if not self.solver.task_step_list:
            return [[name] for name in names]
        for name in names:
            if name not in included:
                groups.append([name])
        return groups

    def assign_groups(self, groups: list[list[str]]) -> None:
        """Store groups in display order and cases in their solve order.

        Args:
            groups (list[list[str]]): Ordered load-case groups processed as independent solver
                tasks.
        """
        names = (
            list(self.problem.steps.step_values)
            if self.problem.steps is not None
            else []
        )
        registered = set(names)
        included: set[str] = set()
        ordered: list[list[str]] = []
        for source in groups:
            group = []
            for name in source:
                if name in registered and name not in included:
                    group.append(name)
                    included.add(name)
            if group:
                ordered.append(group)
        ordered.extend([[name] for name in names if name not in included])
        self.solver.task_step_list = ordered
