"""Definition construction and editing policies shared by all UI entry points."""
from __future__ import annotations
from ..i18n import localized_message

from ..model.problem import (
    CADOperationNode, HelperFunctionNode, HelperVariableNode, FEAComponentNode,
    MaterialNode, Node, PartNode, ProblemDefinition, SurfaceNode,
)
from ..model.node_types.parts import BoundaryPartNode, CADPartNode
from ..model.registry import (
    LOAD_TYPES,
    PART_TYPES,
)
from ..model.problem import (
    CustomClassNode, CustomFunctionNode, MethodOverrideNode, StepsNode, SolverNode,
)
from ..schemes.base import get_template
from .updaters import symmetry_item, updater_item


class DefinitionCommands:
    """Construct nodes with current scheme defaults; domain objects own links.

    This service contains no dialogs or selection/rendering behavior. It can be
    used from a script as well as from the Qt action controller.
    """

    def __init__(self, problem: ProblemDefinition):
        self.problem = problem

    def add_helper(self, kind: str) -> Node:
        types = {
            "helper_variable": (HelperVariableNode, "variable", {"value": "None"}),
            "helper_function": (HelperFunctionNode, "helper", {"parameters": "", "body": "pass"}),
        }
        node_type, base, params = types[kind]
        taken = {item.name for item in self.problem.helper_variables + self.problem.helper_functions}
        index = 1
        while f"{base}_{index}" in taken:
            index += 1
        node = node_type(name=f"{base}_{index}", params=params)
        entries = self.problem.helper_variables if kind == "helper_variable" else self.problem.helper_functions
        entries.append(node)
        return node

    def remove_helper(self, node: Node) -> str:
        entries = self.problem.helper_variables if node.kind == "helper_variable" else self.problem.helper_functions
        entries.remove(node)
        return "helper_variables_group" if node.kind == "helper_variable" else "helper_functions_group"

    def move_helper(self, node: Node, delta: int) -> bool:
        entries = self.problem.helper_variables if node.kind == "helper_variable" else self.problem.helper_functions
        index = entries.index(node)
        target = index + delta
        if not 0 <= target < len(entries):
            return False
        entries.insert(target, entries.pop(index))
        return True

    def add_part(self, part_type: str, custom_class: str = "") -> PartNode:
        name = self.problem.suggest_part_name()
        if PART_TYPES[part_type].custom_only:
            if not custom_class:
                raise ValueError(localized_message("ui.errors.editing.value_requires_a_custom_class", value_0=part_type))
            node = PartNode.create(part_type, name=name)
        else:
            node = get_template(self.problem.scheme).make_part(part_type, name=name)
        node.custom_class = custom_class
        self.problem.add_part(node)
        return node

    def add_surface(
        self,
        surface_type: str,
        owner: BoundaryPartNode,
        custom_class: str = "",
    ) -> SurfaceNode:
        node = get_template(self.problem.scheme).make_surface(surface_type, len(owner.surfaces))
        node.custom_class = custom_class
        self.problem.add_surface(node, part=owner)
        return node

    def add_component(self, component_type: str, custom_class: str = "") -> FEAComponentNode:
        node = get_template(self.problem.scheme).make_component(component_type)
        node.custom_class = custom_class
        node.name = self.problem.suggest_component_name(node.name_hint)
        self.problem.add_component(node)
        return node

    def add_material(self, material_type: str, custom_class: str = "") -> MaterialNode:
        node = get_template(self.problem.scheme).make_material(material_type=material_type)
        names = {material.name for material in self.problem.material_nodes()}
        index = 1
        while f"material_{index}" in names:
            index += 1
        node.name = f"material_{index}"
        node.custom_class = custom_class
        self.problem.add_material(node)
        return node

    def next_operation_id(self, owner: CADPartNode, operation_type: str) -> str:
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
        node = CADOperationNode.create(operation_type, operation_id, **values)
        self.problem.add_cad_operation(owner, node)
        return node

    def available_optimizer_targets(self) -> list[PartNode | MaterialNode]:
        """Actual components that can receive a new updater, in model order."""
        if self.problem.updater is None:
            return []
        candidates = [
            node for node in self.problem.parts() + self.problem.material_nodes()
            if node.is_updatable
        ]
        taken = {
            *(self.problem.config_part_node(config) for config in self.problem.updater.geometry),
            *(self.problem.config_material_node(config) for config in self.problem.updater.materials),
        }
        return [node for node in candidates if node not in taken]

    @staticmethod
    def add_updater_item(config: dict, item_type: str, category: str) -> None:
        key = "objective_functions" if category == "objectives" else "constraints"
        config.setdefault(key, []).append(updater_item(item_type, category))

    def add_symmetry_constraint(self, config: dict, item_type: str) -> bool:
        target = self.problem.config_part_node(config)
        surfaces = target.surfaces if target is not None else []
        item = symmetry_item(item_type, surfaces)
        if item is None:
            return False
        config.setdefault("symmetry_constraints", []).append(item)
        return True


def set_node_field(node: Node, key: str, value, problem: ProblemDefinition | None = None) -> bool:
    """Apply fields through aggregate reference/rename rules, never through widgets."""
    from ..model.problem import INSTANCE_REFERENCE_FIELDS, REFERENCE_POINT_FIELDS
    if problem is not None:
        if isinstance(node, FEAComponentNode) and key in {*INSTANCE_REFERENCE_FIELDS, *REFERENCE_POINT_FIELDS}:
            return problem.set_component_reference(node, key, value)
        if key == "part_name" and isinstance(node, MaterialNode):
            return problem.set_material_part(node, value)
    node.set_field(key, value)
    return True


def rename_node(node: Node, name: str, problem: ProblemDefinition | None = None) -> bool:
    name = name.strip()
    if not name or name == node.name:
        return False
    if problem is not None:
        if node.kind == "instance":
            return problem.rename_instance(node, name)
        return problem.rename_definition(node, name)
    node.name = name
    return True


class HelperCodeSession:
    """Bind and validate an editable helper definition without UI state."""
    def __init__(self, problem: ProblemDefinition, node: Node | None):
        self.problem, self.node = problem, node

    def save(self, name: str, value: str, parameters: str, body: str) -> None:
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
                raise ValueError(localized_message("ui.errors.editing.helper_names_must_be_valid_python_identifiers"))
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
        self.problem = problem

    def catalog(self):
        from ..codegen.custom_classes import framework_class_catalog
        return framework_class_catalog(self.problem)

    def validate_name(self, name: str, current: CustomClassNode | None = None) -> None:
        from ..codegen.custom_classes import validate_custom_name
        validate_custom_name(name, self.catalog())
        if any(node is not current and node.name == name for node in self.problem.custom_classes):
            raise ValueError(localized_message("ui.errors.editing.class_name_already_exists_value", value_0=name))

    def add_class(self, name: str, base: str = "", class_type: str = "override") -> CustomClassNode:
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
        problem.class_bindings = {path: new if name == old else name for path, name in problem.class_bindings.items() if new or name != old}
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
        self.validate_name(name, current=node)
        if name == node.name:
            return False
        old, node.name = node.name, name
        self._replace_uses(old, name)
        return True

    def remove(
        self, node: CustomClassNode | MethodOverrideNode | CustomFunctionNode
    ) -> CustomClassNode | None:
        from ..model.problem import CustomClassNode
        if isinstance(node, CustomClassNode):
            self.problem.custom_classes.remove(node)
            self._replace_uses(node.name, "")
            return None
        owner = next(custom for custom in self.problem.custom_classes if node in custom.members)
        owner.remove_child(node)
        return owner

    @staticmethod
    def add_override(custom: CustomClassNode, spec) -> MethodOverrideNode:
        from ..model.problem import MethodOverrideNode
        override = MethodOverrideNode(name=spec.name, params={"body": spec.body})
        custom.add_child(override)
        return override

    @staticmethod
    def add_function(
        custom: CustomClassNode, name: str, parameters: str = "self"
    ) -> CustomFunctionNode:
        function = CustomFunctionNode(
            name=name,
            params={"parameters": parameters, "body": "pass"},
        )
        custom.add_child(function)
        return function

    @staticmethod
    def move_member(custom: CustomClassNode, node: Node, delta: int) -> bool:
        index = custom.members.index(node)
        target = index + delta
        if not 0 <= target < len(custom.members):
            return False
        custom.members.insert(target, custom.members.pop(index))
        return True

    @staticmethod
    def validate_body(override: MethodOverrideNode, spec) -> None:
        from textwrap import indent
        compile(
            spec.header + "\n" + indent(override.body if override.body.strip() else "pass", "    "),
            "<method body>",
            "exec",
        )

    @staticmethod
    def validate_function(function: CustomFunctionNode) -> None:
        from textwrap import indent
        import keyword
        if not function.name.isidentifier() or keyword.iskeyword(function.name):
            raise ValueError(
                localized_message("ui.errors.custom_classes.invalid_custom_function_name")
            )
        compile(
            f"def {function.name}({function.parameters}):\n"
            + indent(function.body if function.body.strip() else "pass", "    "),
            "<custom class function>",
            "exec",
        )


class LoadCaseSession:
    """Load cases and their object-keyed amplitudes, independent of a table widget."""
    def __init__(self, steps: StepsNode, problem: ProblemDefinition):
        self.steps, self.problem = steps, problem

    def columns(self) -> list[tuple[FEAComponentNode, int, str]]:
        columns = []
        for component in self.problem.amplitude_components():
            count = component.num_values
            columns.extend((component, index, component.name if count == 1 else f"{component.name}.{index}") for index in range(count))
        return columns

    def value(
        self, row: int, component: FEAComponentNode, component_index: int
    ):
        amplitudes = self.steps.step_values[row].get(component, []) if row < len(self.steps.step_values) else []
        return amplitudes[component_index] if component_index < len(amplitudes) else 0.

    def resize(self, count: int) -> None:
        if count < 1:
            raise ValueError(localized_message("ui.errors.editing.keep_at_least_one_load_case"))
        rows = self.steps.step_values[:count]
        rows.extend({} for _ in range(count - len(rows)))
        self.steps.num_steps, self.steps.step_values = count, rows

    def copy(self, row: int) -> int:
        self.resize(self.steps.num_steps)
        self.steps.step_values.insert(
            row + 1,
            {component: list(values) for component, values in self.steps.step_values[row].items()},
        )
        self.steps.num_steps += 1
        return row + 1

    def remove(self, row: int) -> int:
        if self.steps.num_steps <= 1:
            raise ValueError(localized_message("ui.errors.editing.keep_at_least_one_load_case"))
        self.resize(self.steps.num_steps)
        self.steps.step_values.pop(row)
        self.steps.num_steps -= 1
        return min(row, self.steps.num_steps - 1)

    def set_value(self, row: int, column: int, text: str) -> bool:
        try:
            value = float(text)
        except ValueError:
            value = text.strip()
            if value not in {node.name for node in self.problem.helper_variables}:
                return False
        component, component_index, _caption = self.columns()[column]
        self.resize(self.steps.num_steps)
        values = self.steps.step_values[row].setdefault(component, [])
        values.extend(0. for _ in range(component_index + 1 - len(values)))
        values[component_index] = value
        return True


class SolverTasks:
    """Translate solver task groups into row assignments and back."""
    def __init__(self, solver: SolverNode, problem: ProblemDefinition):
        self.solver, self.problem = solver, problem

    def assignments(self) -> list[int]:
        count = self.problem.steps.num_steps if self.problem.steps is not None else 1
        assigned = {step: group for group, steps in enumerate(self.solver.task_index_list) for step in steps}
        return [assigned.get(step, step) for step in range(count)]

    def assign(self, assignments: list[int]) -> None:
        groups: dict[int, list[int]] = {}
        for step, group in enumerate(assignments):
            groups.setdefault(max(0, group), []).append(step)
        self.solver.task_index_list = [groups[index] for index in sorted(groups)]
