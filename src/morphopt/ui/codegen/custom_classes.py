"""Discover existing classes without executing user code and emit subclasses.

Custom classes are independent module-level subclasses of framework classes.
Model nodes explicitly select a compatible class; generated configuration
classes inherit that selection and pass the UI constructor parameters to it.
"""

from __future__ import annotations

import ast
import inspect
import keyword
import re
from dataclasses import dataclass, field

import morphopt

from ..model.problem import CustomClassNode, MethodOverrideNode, ProblemDefinition
from ..model.schemas import PART_INTERFACE_TYPES, SURFACE_TYPES, UPDATER_CATALOG


@dataclass(frozen=True)
class MethodSpec:
    name: str
    signature: str
    body: str
    decorator: str = ""
    asynchronous: bool = False
    documentation: str = ""

    @property
    def header(self) -> str:
        return f"{'async ' if self.asynchronous else ''}def {self.name}{self.signature}:"


@dataclass
class ClassSpec:
    path: str
    base_expression: str
    definition: ast.ClassDef
    backend: type
    inherited: bool = False
    methods: dict[str, MethodSpec] = field(default_factory=dict)


def _resolve(expression: str) -> type:
    value = morphopt
    parts = expression.split(".")
    if parts[0] != "morphopt":
        raise ValueError(f"Unsupported base class: {expression}")
    for name in parts[1:]:
        value = getattr(value, name)
    return value


def _method_spec(name, arguments, decorator="", asynchronous=False, documentation=""):
    # Method bodies are edited separately; argument names/defaults stay intact.
    arguments = ast.parse(f"def f{arguments}: pass").body[0].args
    for arg in arguments.posonlyargs + arguments.args + arguments.kwonlyargs:
        arg.annotation = None
    if arguments.vararg:
        arguments.vararg.annotation = None
    if arguments.kwarg:
        arguments.kwarg.annotation = None
    signature = f"({ast.unparse(arguments)})"
    positional = arguments.posonlyargs + arguments.args
    if decorator != "staticmethod":
        positional = positional[1:]
    calls = [arg.arg for arg in positional]
    if arguments.vararg:
        calls.append(f"*{arguments.vararg.arg}")
    calls += [f"{arg.arg}={arg.arg}" for arg in arguments.kwonlyargs]
    if arguments.kwarg:
        calls.append(f"**{arguments.kwarg.arg}")
    body = f"return {'await ' if asynchronous else ''}super().{name}({', '.join(calls)})"
    return MethodSpec(name, signature, body, decorator, asynchronous, documentation)


def _backend_methods(backend: type, expression: str) -> dict[str, MethodSpec]:
    methods = {}
    for name in dir(backend):
        if name.startswith("__") and name not in {"__init__", "__call__"}:
            continue
        member = inspect.getattr_static(backend, name)
        decorator = ""
        if isinstance(member, (staticmethod, classmethod)):
            decorator = type(member).__name__
            member = member.__func__
        if not inspect.isfunction(member):
            continue
        signature = inspect.signature(member)
        params = [parameter.replace(annotation=inspect.Parameter.empty)
                  for parameter in signature.parameters.values()]
        # Do not emit reprs of objects as Python default expressions.
        try:
            for parameter in params:
                if parameter.default is not inspect.Parameter.empty:
                    ast.literal_eval(repr(parameter.default))
            signature = str(signature.replace(parameters=params, return_annotation=inspect.Signature.empty))
            spec = _method_spec(name, signature, decorator,
                                inspect.iscoroutinefunction(member), inspect.getdoc(member) or "")
        except (SyntaxError, ValueError, TypeError):
            continue
        if decorator == "staticmethod":
            spec = MethodSpec(spec.name, spec.signature,
                              spec.body.replace("super()", expression),
                              decorator, spec.asynchronous, spec.documentation)
        methods[name] = spec
    return methods


def class_catalog(problem: ProblemDefinition, source: str | None = None) -> dict[str, ClassSpec]:
    if source is None:
        from .generator import generate_base_source

        source = generate_base_source(problem)
    catalog = {}

    def visit(body, prefix=""):
        for node in body:
            if not isinstance(node, ast.ClassDef):
                continue
            path = f"{prefix}.{node.name}" if prefix else node.name
            expression = ast.unparse(node.bases[0])
            backend = _resolve(expression)
            spec = ClassSpec(path, expression, node, backend)
            spec.methods = _backend_methods(backend, expression)
            for method in node.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    spec.methods[method.name] = _method_spec(
                        method.name, f"({ast.unparse(method.args)})",
                        asynchronous=isinstance(method, ast.AsyncFunctionDef),
                        documentation=ast.get_docstring(method) or "")
            catalog[path] = spec
            visit(node.body, path)
            # Include inherited interface/factory classes exposed by this class.
            for name in dir(backend):
                nested = inspect.getattr_static(backend, name)
                nested_path = f"{path}.{name}"
                if (not isinstance(nested, type) or not nested.__module__.startswith("morphopt")
                        or nested_path in catalog or name.startswith("_")):
                    continue
                nested_expression = f"{expression}.{name}"
                nested_spec = ClassSpec(nested_path, nested_expression, node, nested, True)
                nested_spec.methods = _backend_methods(nested, nested_expression)
                catalog[nested_path] = nested_spec

    visit(ast.parse(source).body)
    # Material constructors currently refer to the public module classes.
    parent = catalog["ThisController.Params.MaterialsParams"]
    for name in ("HomogeneousMaterial", "SIMP_BSPFieldMaterials"):
        path = f"{parent.path}.{name}"
        expression = f"morphopt.{name}"
        spec = ClassSpec(path, expression, parent.definition, _resolve(expression), True)
        spec.methods = _backend_methods(spec.backend, expression)
        catalog[path] = spec
    return catalog


def validate_class_name(name: str) -> None:
    if not name.isidentifier() or keyword.iskeyword(name) or name.startswith("__"):
        raise ValueError("自定义类名必须是有效的 Python 标识符 / Invalid Python class name")


def framework_class_catalog(problem: ProblemDefinition, targets=None) -> dict[str, ClassSpec]:
    """Framework parents for reusable top-level custom classes."""
    parents = {}
    for target in (targets if targets is not None else class_catalog(problem)).values():
        expression = target.base_expression
        if expression.startswith("morphopt.GeometryParams."):
            expression = "morphopt." + expression.rsplit(".", 1)[-1]
        if expression not in parents:
            spec = ClassSpec(expression, expression, target.definition, target.backend)
            spec.methods = _backend_methods(spec.backend, expression)
            parents[expression] = spec
    definition = next(iter(parents.values())).definition
    for interface_type in PART_INTERFACE_TYPES:
        expression = f"morphopt.{interface_type}"
        if expression not in parents:
            backend = _resolve(expression)
            spec = ClassSpec(expression, expression, definition, backend)
            spec.methods = _backend_methods(backend, expression)
            parents[expression] = spec
    for group in ("geometry", "materials"):
        for category in ("objectives", "constraints"):
            expression = updater_item_base("Custom", category, group)
            backend = _resolve(expression)
            spec = ClassSpec(expression, expression, definition, backend)
            spec.methods = _backend_methods(backend, expression)
            parents[expression] = spec
    for category, items in UPDATER_CATALOG.items():
        for item_type, item in items.items():
            expression = updater_item_base(item_type, category)
            if expression and expression not in parents:
                backend = _resolve(expression)
                spec = ClassSpec(expression, expression, definition, backend)
                spec.methods = _backend_methods(backend, expression)
                parents[expression] = spec
    return parents


def updater_item_base(item_type, category, group=None):
    if item_type == "Custom" and group is not None:
        updater = "morphopt.UpdaterBoundaryPart" if group == "geometry" else "morphopt.UpdaterSIMPMaterial"
        return updater + ".objectivefuncs." + ("BaseObjective" if category == "objectives" else "BaseConstraints")
    spec = UPDATER_CATALOG.get(category, {}).get(item_type, {})
    match = re.match(r"([\w.]+)\(", spec.get("gen", ""))
    if not match:
        return None
    expression = match[1]
    if expression.startswith("self."):
        updater = "morphopt.UpdaterBoundaryPart" if spec["group"] == "geometry" else "morphopt.UpdaterSIMPMaterial"
        expression = updater + expression[4:]
    return expression


def custom_options(problem, candidates):
    """(Schema type, custom class) choices for an Add menu."""
    parents = framework_class_catalog(problem)
    choices = []
    for item_type, expression in candidates.items():
        backend = _resolve(expression)
        for custom in problem.custom_classes:
            base = parents.get(custom.base_class)
            if base is not None and issubclass(base.backend, backend):
                choices.append((item_type, custom))
    return choices


def validate_custom_name(name: str, catalog: dict[str, ClassSpec]) -> None:
    validate_class_name(name)
    reserved = {"os", "morphopt", "Any", "ThisController"}
    for spec in catalog.values():
        reserved.update({spec.definition.name, spec.path.split(".")[-1]})
        reserved.update(spec.methods)
    if name in reserved:
        raise ValueError(f"类名与模块成员冲突 / Class name conflicts with a module member: {name}")


CONFIGURATION_CLASS_PATHS = {
    "problem": "ThisController",
    "params_class": "ThisController.Params",
    "geometry": "ThisController.Params.GeometryParams",
    "loads_group": "ThisController.Params.FEAParams",
    "materials": "ThisController.Params.MaterialsParams",
    "solver": "ThisController.Solver",
    "updater": "ThisController.Updater",
}


def class_path_for_node(node):
    """Generated configuration class selected by a model-tree row."""
    if node is None:
        return None
    return CONFIGURATION_CLASS_PATHS.get(node.kind)


def compatible_custom_classes(problem, target, parents=None):
    parents = parents if parents is not None else framework_class_catalog(problem)
    return [custom for custom in problem.custom_classes
            if (base := parents.get(custom.base_class)) is not None
            and issubclass(base.backend, target.backend)]


def apply_custom_classes(problem: ProblemDefinition, source: str) -> str:
    targets = class_catalog(problem, source)
    parents = framework_class_catalog(problem, targets)
    definitions = []
    customs = {}
    for custom in problem.custom_classes:
        if not isinstance(custom, CustomClassNode):
            raise ValueError("Invalid custom class definition")
        spec = parents.get(custom.base_class)
        if spec is None:
            raise ValueError(f"{custom.name}: 父类已不存在 / Base class missing: {custom.base_class}")
        validate_custom_name(custom.name, parents)
        if custom.name in customs:
            raise ValueError(f"重复的类名 / Duplicate class name: {custom.name}")
        customs[custom.name] = (custom, spec)
        lines = [f"class {custom.name}({spec.base_expression}):"]
        seen = set()
        for override in custom.children:
            method = spec.methods.get(override.name)
            if not isinstance(override, MethodOverrideNode) or method is None:
                raise ValueError(f"{custom.name}: 无效的重写方法 / Invalid override: {override.name}")
            if override.name in seen:
                raise ValueError(f"Duplicate override: {custom.name}.{override.name}")
            seen.add(override.name)
            if method.decorator:
                lines.append(f"    @{method.decorator}")
            lines.append(f"    {method.header}")
            body = override.body if override.body.strip() else "pass"
            lines.extend(f"        {line}" if line.strip() else "" for line in body.splitlines())
            lines.append("")
        if not seen:
            lines.append("    pass")
        definitions.append("\n".join(lines))

    lines = source.splitlines()
    removals = set()
    insertions = {}
    invalid_paths = set(problem.class_bindings) - set(CONFIGURATION_CLASS_PATHS.values())
    if invalid_paths:
        raise ValueError(f"Invalid configuration class selection: {sorted(invalid_paths)}")
    bindings = dict(problem.class_bindings)

    def check_usage(name, expression):
        if name not in customs:
            raise ValueError(f"自定义类已不存在 / Custom class missing: {name}")
        if not issubclass(customs[name][1].backend, _resolve(expression)):
            raise ValueError(f"{name} 不能用于 {expression} / Incompatible custom class")

    from .generator import part_class_names

    part_names = part_class_names(problem)
    for node in problem.root.iter_nodes():
        if not node.custom_class:
            continue
        if node.kind == "part_interface":
            path = "ThisController.Params.GeometryParams." + part_names[node.name]
            bindings[path] = node.custom_class
        elif node.kind == "objective":
            bindings["ThisController.ObjectiveFunction"] = node.custom_class
        elif node.kind == "interface":
            check_usage(node.custom_class, "morphopt.FEAParams." + node.interface_type + "Interface")
        elif node.kind == "material":
            check_usage(node.custom_class, "morphopt." + node.material_type)
        elif node.kind == "surface":
            factory = SURFACE_TYPES[node.surface_type]["factory"]
            check_usage(node.custom_class, "morphopt.BoundaryPartInterface." + (factory.split(".")[0] if factory else "FixedSurface"))
        else:
            raise ValueError(f"Unsupported custom class on node: {node.kind}")
    if problem.updater:
        configurations = [("geometry", config) for config in problem.updater.geometry]
        configurations += [("materials", config) for config in problem.updater.materials]
        for group, config in configurations:
            for key, category in (("objective_functions", "objectives"), ("constraints", "constraints")):
                for item in config.get(key, []):
                    if item.get("custom_class"):
                        expression = updater_item_base(item.get("type"), category, group)
                        if expression is None:
                            raise ValueError("Invalid custom objective/constraint type")
                        check_usage(item["custom_class"], expression)

    for path, name in bindings.items():
        target = targets.get(path)
        if target is None:
            raise ValueError(f"使用类的模型节点已不存在 / Class target missing: {path}")
        if name not in customs:
            raise ValueError(f"自定义类已不存在 / Custom class missing: {name}")
        custom, base = customs[name]
        if not issubclass(base.backend, target.backend):
            raise ValueError(f"{name} 不能用于 {path} / Incompatible custom class")
        node = target.definition
        lines[node.lineno - 1] = lines[node.lineno - 1].replace(
            f"({target.base_expression})", f"({name})")
        overridden = {method.name for method in custom.children}
        for method in node.body:
            # The UI constructor forwards its configured options through
            # the selected custom __init__. Explicit declaration hooks
            # replace the corresponding UI-generated method.
            if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and method.name != "__init__" and method.name in overridden:
                start = min([method.lineno] + [item.lineno for item in method.decorator_list])
                removals.update(range(start - 1, method.end_lineno))
        if all(index in removals or not lines[index].strip()
               for index in range(node.lineno, node.end_lineno)):
            insertions.setdefault(node.end_lineno, []).append(" " * (node.col_offset + 4) + "pass")
    first_class = targets["ThisController"].definition.lineno - 1
    output = []
    for index, line in enumerate(lines):
        if index == first_class and definitions:
            output.append("\n\n".join(definitions) + "\n\n")
        if index not in removals:
            output.append(line)
        output.extend(insertions.get(index + 1, []))
    result = "\n".join(output) + "\n"
    try:
        compile(result, "<custom classes>", "exec")
    except SyntaxError as exc:
        raise ValueError(f"自定义方法语法错误 / Invalid custom method: {exc}") from exc
    return result
