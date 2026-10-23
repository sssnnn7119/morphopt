"""Static definition diagnostics, independent of widgets and geometry evaluation."""

from __future__ import annotations

import ast
import builtins
import json
import keyword
import math
import operator
import symtable
import textwrap
from collections import Counter
from copy import copy
from numbers import Real
from pathlib import Path
from typing import Any

from ..codegen.custom_classes import CONFIGURATION_CLASS_PATHS, _resolve
from ..codegen.generator import (
    _metrics_function_body,
    _objective_function_body,
    _render_updater_item,
    _surface_constraints_for_part,
)
from ..i18n import tr
from ..model.fields import FieldSpec
from ..model.node_types.cad import StepImportOperationNode
from ..model.node_types.parts import BoundaryPartNode, CADPartNode
from ..model.node_types.surfaces import BREPSurfaceNode
from ..model.problem import (
    INSTANCE_REFERENCE_FIELDS,
    REFERENCE_POINT_FIELDS,
    FEAComponentNode,
    MaterialNode,
    Node,
    ProblemDefinition,
)
from ..model.registry import SURFACE_SYMMETRY_CONSTRAINTS, UPDATER_CATALOG
from .fields import fields_for_node
from .part_sets import PartSetCatalog

_UNKNOWN = object()


class DefinitionValidation:
    """Collect errors by definition identity without executing user definitions.

    Dictionary entries (objective terms and updater configurations) retain their
    own identities so navigation projections can display the same diagnostics.
    Virtual class-selection rows use their registered configuration paths.
    """

    def __init__(self, problem: ProblemDefinition) -> None:
        self.problem = problem
        self.errors: dict[int | str, list[str]] = {}
        self.constant_nodes = {node.name: node for node in problem.helper_variables}
        self.constants = {
            name: node.value for name, node in self.constant_nodes.items()
        }
        self.classes = {node.name for node in problem.custom_classes}
        self.known_names: set[str] = set()

    def add(self, owner: object, key: str, **values: object) -> None:
        message = tr(f"ui.validation.{key}", **values)
        identity = owner if isinstance(owner, str) else id(owner)
        messages = self.errors.setdefault(identity, [])
        if message not in messages:
            messages.append(message)

    def check_source(
        self,
        owner: object,
        source: str,
        *,
        expression: bool = False,
        check_names: bool = False,
    ) -> None:
        try:
            compile(source, "<definition>", "eval" if expression else "exec")
            if check_names:
                table = symtable.symtable(
                    source, "<definition>", "eval" if expression else "exec"
                )

                def globals_used(scope: symtable.SymbolTable) -> set[str]:
                    names = {
                        symbol.get_name()
                        for symbol in scope.get_symbols()
                        if symbol.is_global() and symbol.is_referenced()
                    }
                    for child in scope.get_children():
                        names.update(globals_used(child))
                    return names

                for name in sorted(globals_used(table) - self.known_names):
                    self.add(owner, "reference", field="Python", name=name)
        except (SyntaxError, ValueError) as exc:
            self.add(owner, "code", reason=str(exc))

    def literal(self, expression: str, active: frozenset[str] = frozenset()) -> Any:
        """Resolve literal constants only; calls and arbitrary expressions stay unknown."""
        if expression in self.constants:
            if expression in active:
                raise ValueError(tr("ui.validation.constant_cycle", name=expression))
            return self.literal(self.constants[expression], active | {expression})

        def resolve(node: ast.AST) -> Any:
            if isinstance(node, ast.Name) and node.id in self.constants:
                return self.literal(node.id, active)
            if isinstance(node, (ast.List, ast.Tuple)):
                values = [resolve(item) for item in node.elts]
                return _UNKNOWN if any(item is _UNKNOWN for item in values) else values
            if isinstance(node, ast.Constant):
                return node.value
            if isinstance(node, ast.UnaryOp) and isinstance(
                node.op, (ast.UAdd, ast.USub)
            ):
                value = resolve(node.operand)
                if isinstance(value, Real):
                    return value if isinstance(node.op, ast.UAdd) else -value
            operations = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
                ast.FloorDiv: operator.floordiv,
                ast.Mod: operator.mod,
            }
            if isinstance(node, ast.BinOp) and type(node.op) in operations:
                left, right = resolve(node.left), resolve(node.right)
                if isinstance(left, Real) and isinstance(right, Real):
                    return operations[type(node.op)](float(left), float(right))
            return _UNKNOWN

        return resolve(ast.parse(expression, mode="eval").body)

    def field(self, owner: object, spec: FieldSpec, value: object) -> None:
        if spec.hidden or spec.read_only:
            return
        label = (
            tr(spec.label_key) if spec.label_key.startswith("ui.") else spec.label_key
        )
        numeric = spec.type in {"float", "int", "vec3", "vec6", "vecN", "mat", "dofs"}
        if isinstance(value, str) and (numeric or spec.type == "file"):
            if value in self.constants:
                if self.errors.get(id(self.constant_nodes[value])):
                    self.add(owner, "invalid_constant", field=label, name=value)
                try:
                    value = self.literal(value)
                except (SyntaxError, ValueError, ArithmeticError) as exc:
                    self.add(owner, "field", field=label, reason=str(exc))
                    return
                if value is _UNKNOWN:
                    return
            elif numeric:
                self.add(owner, "number", field=label)
                return
        if spec.type in {"int", "float"}:
            if (
                not isinstance(value, Real)
                or isinstance(value, bool)
                or not math.isfinite(value)
            ):
                self.add(owner, "number", field=label)
            elif spec.type == "int" and int(value) != value:
                self.add(owner, "integer", field=label)
            elif (spec.minimum is not None and value < spec.minimum) or (
                spec.maximum is not None and value > spec.maximum
            ):
                self.add(
                    owner,
                    "range",
                    field=label,
                    minimum=spec.minimum if spec.minimum is not None else "−∞",
                    maximum=spec.maximum if spec.maximum is not None else "+∞",
                )
        elif spec.type == "combo" and spec.choices and value not in spec.choices:
            self.add(owner, "choice", field=label)
        elif spec.type in {"vec3", "vec6", "vecN", "mat", "dofs"}:
            size = {"vec3": 3, "vec6": 6}.get(spec.type)
            if not isinstance(value, (list, tuple)) or (
                size is not None and len(value) != size
            ):
                if size is None:
                    self.add(owner, "sequence", field=label)
                else:
                    self.add(owner, "vector", field=label, size=size)
                return
            # GPU names and solver task groups are string sequences.
            if spec.key in {"gpus", "task_step_list"}:
                return
            for entry in value:
                if spec.type == "mat":
                    self.field(
                        owner, FieldSpec(spec.key, spec.label_key, "vecN"), entry
                    )
                else:
                    self.field(
                        owner,
                        FieldSpec(
                            spec.key,
                            spec.label_key,
                            "int" if spec.ints or spec.type == "dofs" else "float",
                            minimum=spec.minimum,
                            maximum=spec.maximum,
                        ),
                        entry,
                    )
            if spec.type == "dofs" and any(
                isinstance(v, Real) and v not in range(6) for v in value
            ):
                self.add(owner, "choice", field=label)
        elif spec.type == "file":
            if (
                not isinstance(value, str)
                or not value.strip()
                or not Path(value).expanduser().is_file()
            ):
                self.add(owner, "asset", field=label)
        elif spec.type == "code":
            self.check_source(owner, self.function_source("self", str(value)))

    @staticmethod
    def function_source(parameters: str, body: str) -> str:
        return f"def _definition({parameters}):\n" + textwrap.indent(
            body.strip() or "pass", "    "
        )

    def names(self, nodes: list[Node], *, identifiers: bool = False) -> None:
        counts = Counter(node.name for node in nodes)
        for node in nodes:
            if not node.name.strip():
                self.add(node, "required", field="name")
            elif identifiers and (
                not node.name.isidentifier() or keyword.iskeyword(node.name)
            ):
                self.add(node, "identifier", name=node.name)
            if counts[node.name] > 1:
                self.add(node, "duplicate", name=node.name)

    def custom_class(self, owner: object, name: str) -> None:
        if name and name not in self.classes:
            self.add(owner, "reference", field="custom_class", name=name)

    def overridden(self, node: Node) -> bool:
        path = CONFIGURATION_CLASS_PATHS.get(node.kind, "")
        return bool(node.custom_class or self.problem.class_bindings.get(path))

    def node(self, node: Node) -> None:
        try:
            fields = (
                fields_for_node(node)[0]
                if isinstance(node, MaterialNode)
                else node.fields
            )
        except KeyError:
            self.add(node, "choice", field="material_model")
            fields = ()
        for spec in fields:
            self.field(node, spec, node.get_field(spec.key))
            if spec.key == "bounding_box":
                value = node.get_field(spec.key)
                if (
                    isinstance(value, (list, tuple))
                    and len(value) == 6
                    and all(isinstance(v, Real) for v in value)
                    and any(value[index] >= value[index + 1] for index in (0, 2, 4))
                ):
                    self.add(node, "bounding_box")
        self.custom_class(node, node.custom_class)
        if node.custom_only and not node.custom_class:
            self.add(node, "required", field="custom_class")
        if node.kind == "part" and not node.instances and not node.custom_class:
            self.add(node, "required", field="instances")
        if isinstance(node, FEAComponentNode):
            for spec in fields:
                name = node.get_field(spec.key)
                candidates = None
                if spec.key in INSTANCE_REFERENCE_FIELDS:
                    candidates = self.problem.instance_names()
                elif spec.key in REFERENCE_POINT_FIELDS:
                    candidates = self.problem.reference_point_names()
                if candidates is not None and name not in candidates:
                    self.add(node, "reference", field=tr(spec.label_key), name=name)
                elif (
                    spec.key
                    in {
                        "surface_name",
                        "surface_name1",
                        "surface_name2",
                        "set_nodes_name",
                        "element_name",
                        "obj_name",
                    }
                    and not name
                ):
                    self.add(node, "required", field=tr(spec.label_key))
                elif spec.key in {
                    "surface_name",
                    "surface_name1",
                    "surface_name2",
                    "set_nodes_name",
                }:
                    suffix = spec.key[-1] if spec.key[-1] in "12" else ""
                    part = self.problem.part_for_instance(
                        node.reference_name("instance_name" + suffix)
                    )
                    if isinstance(part, BoundaryPartNode) and not part.custom_class:
                        try:
                            sets = PartSetCatalog.boundary(part, self.problem)
                        except ValueError:
                            continue  # The invalid face map is reported on its asset node.
                        if any(surface.custom_class for surface in part.surfaces):
                            continue  # A custom surface may declare additional sets.
                        available = (
                            sets.nodes
                            if spec.key == "set_nodes_name"
                            else sets.surfaces
                        )
                        if name not in available:
                            self.add(
                                node, "reference", field=tr(spec.label_key), name=name
                            )
        if isinstance(node, MaterialNode) and node.part not in self.problem.parts():
            self.add(node, "reference", field="part_name", name=node.part_name)
        if (
            isinstance(node, (StepImportOperationNode, BREPSurfaceNode))
            and not node.data
        ):
            self.add(node, "asset", field="STEP")
        if isinstance(node, BREPSurfaceNode):
            for key in ("face_map", "brep_metadata"):
                try:
                    if not isinstance(json.loads(node.get_field(key)), dict):
                        raise ValueError(key)
                except ValueError as exc:
                    self.add(node, "field", field=key, reason=str(exc))
        if (
            isinstance(node, BoundaryPartNode)
            and not node.surfaces
            and not node.custom_class
        ):
            self.add(node, "required", field="surfaces")
        if isinstance(node, CADPartNode):
            if not node.operations and not node.custom_class:
                self.add(node, "required", field="operations")
            ids = Counter(op.operation_id for op in node.operations)
            for index, op in enumerate(node.operations):
                if not op.operation_id:
                    self.add(op, "required", field="operation_id")
                elif ids[op.operation_id] > 1:
                    self.add(op, "duplicate", name=op.operation_id)
                available = {
                    prior.operation_id
                    for prior in node.live_cad_operations(node.operations[:index])
                }
                for key in ("object_id", "tool_id", "input_id"):
                    if op.has_field(key) and op.get_field(key) not in available:
                        self.add(op, "reference", field=key, name=op.get_field(key))

    def objectives(self) -> None:
        objective = self.problem.objective
        if objective is None:
            return
        if objective.objective_terms:
            try:
                if not any(
                    float(term.get("weight", 0)) > 0
                    for term in objective.objective_terms
                ):
                    self.add(objective, "weight")
            except (TypeError, ValueError):
                pass  # Each term reports its own malformed weight.
        for value in objective.jacobian_needed:
            name = value.name if isinstance(value, Node) else value
            if name not in {node.name for node in self.problem.amplitude_components()}:
                self.add(objective, "reference", field="jacobian_needed", name=name)
        for category, terms, render in (
            ("objective", objective.objective_terms, _objective_function_body),
            ("metric", objective.metrics_terms, _metrics_function_body),
        ):
            for term in terms:
                isolated = copy(objective)
                setattr(
                    isolated,
                    "objective_terms" if category == "objective" else "metrics_terms",
                    [dict(term)],
                )
                try:
                    if category == "objective":
                        weight = float(term.get("weight", 0))
                        if not math.isfinite(weight) or weight < 0:
                            raise ValueError(tr("ui.validation.weight"))
                        isolated.objective_terms[0]["weight"] = 1.0
                    body = render(isolated, self.problem)
                    self.check_source(term, self.function_source("self", body))
                    if category == "metric" and term.get("type") == "displacement":
                        for key, candidates in (
                            (
                                "reference_point_name",
                                self.problem.reference_point_names(),
                            ),
                            (
                                "step_name",
                                self.problem.steps.step_values
                                if self.problem.steps
                                else (),
                            ),
                        ):
                            if term.get(key) not in candidates:
                                self.add(
                                    term, "reference", field=key, name=term.get(key)
                                )
                        if term.get("component") not in {
                            "ux",
                            "uy",
                            "uz",
                            "rx",
                            "ry",
                            "rz",
                        }:
                            self.add(term, "choice", field="component")
                except (ValueError, TypeError, SyntaxError) as exc:
                    self.add(term, "definition", reason=str(exc))

    def steps(self) -> None:
        steps = self.problem.steps
        if steps is None:
            return
        if not steps.step_values:
            self.add(steps, "required", field="load_cases")
        loads = {node.name: node for node in self.problem.amplitude_components()}
        for name, values in steps.step_values.items():
            if not name.strip():
                self.add(steps, "required", field="name")
            for key, value in values.items():
                load_name = key.name if isinstance(key, Node) else key
                load = loads.get(load_name)
                if load is None:
                    self.add(steps, "reference", field=name, name=load_name)
                else:
                    self.field(
                        steps,
                        FieldSpec(
                            name, name, "vec6" if load.num_values == 6 else "vecN"
                        ),
                        value,
                    )
                    if (
                        isinstance(value, (list, tuple))
                        and len(value) != load.num_values
                    ):
                        self.add(
                            steps,
                            "vector",
                            field=f"{name}/{load_name}",
                            size=load.num_values,
                        )
        solver = self.problem.solver
        if solver is not None:
            registered: set[str] = set()
            for group in solver.task_step_list:
                if not isinstance(group, (list, tuple)):
                    self.add(solver, "choice", field="task_step_list")
                    continue
                for name in group:
                    if name not in steps.step_values:
                        self.add(solver, "reference", field="task_step_list", name=name)
                    elif name in registered:
                        self.add(solver, "duplicate", name=name)
                    registered.add(name)

    def updaters(self) -> None:
        updater = self.problem.updater
        if updater is None:
            return
        if (
            not updater.geometry
            and not updater.materials
            and not self.overridden(updater)
        ):
            self.add(updater, "required", field="optimizers")
        for group, configs in (
            ("geometry", updater.geometry),
            ("materials", updater.materials),
        ):
            for cfg in configs:
                target = (
                    self.problem.config_part_node(cfg)
                    if group == "geometry"
                    else self.problem.config_material_node(cfg)
                )
                if target is None or target not in (
                    self.problem.parts()
                    if group == "geometry"
                    else self.problem.material_nodes()
                ):
                    self.add(cfg, "required", field="target")
                self.custom_class(cfg, str(cfg.get("custom_class") or ""))
                self.field(
                    cfg,
                    FieldSpec("max_step_iter", "max_step_iter", "int", minimum=1),
                    cfg.get("max_step_iter", 50),
                )
                self.field(
                    cfg,
                    FieldSpec("max_step_length", "max_step_length", "float", minimum=0),
                    cfg.get("max_step_length", 0.5 if group == "geometry" else 1.0),
                )
                for key, category in (
                    ("objective_functions", "objectives"),
                    ("constraints", "constraints"),
                    ("symmetry_constraints", "symmetry"),
                ):
                    for item in cfg.get(key, []):
                        self.custom_class(item, str(item.get("custom_class") or ""))
                        catalog = (
                            SURFACE_SYMMETRY_CONSTRAINTS
                            if category == "symmetry"
                            else UPDATER_CATALOG[category]
                        )
                        spec = catalog.get(item.get("type"))
                        if spec is not None:
                            for field in spec.fields:
                                self.field(
                                    item,
                                    field,
                                    item.get("params", {}).get(
                                        field.key, field.new_default()
                                    ),
                                )
                        try:
                            if category == "symmetry":
                                if target is not None:
                                    _surface_constraints_for_part(
                                        {"symmetry_constraints": [item]},
                                        target,
                                        self.problem,
                                    )
                            else:
                                _render_updater_item(item, category, self.problem)
                        except (ValueError, TypeError, SyntaxError) as exc:
                            self.add(item, "definition", reason=str(exc))

    def collect(self) -> dict[int | str, list[str]]:
        problem = self.problem
        self.check_source(problem, problem.helper_code)
        helpers = [
            *problem.helper_variables,
            *problem.helper_functions,
            *problem.custom_classes,
        ]
        self.known_names = set(vars(builtins)) | {
            "morphopt",
            "torchfea",
            "np",
            "torch",
            "Any",
            "Path",
            "os",
            *(node.name for node in helpers),
        }
        try:
            table = symtable.symtable(problem.helper_code, "<definition>", "exec")
            self.known_names.update(
                symbol.get_name()
                for symbol in table.get_symbols()
                if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()
            )
        except SyntaxError:
            pass  # Already reported on the free code block.
        for node in problem.root.iter_nodes():
            path = CONFIGURATION_CLASS_PATHS.get(node.kind)
            if path is not None:
                self.custom_class(node, problem.class_bindings.get(path, ""))
        for kind in ("params_class", "loads_group"):
            path = CONFIGURATION_CLASS_PATHS[kind]
            self.custom_class(path, problem.class_bindings.get(path, ""))
        self.names(helpers, identifiers=True)
        for node in problem.helper_variables:
            self.check_source(node, node.value, expression=True, check_names=True)
            try:
                self.literal(node.name)
            except (ValueError, SyntaxError, ArithmeticError) as exc:
                self.add(node, "definition", reason=str(exc))
        for node in problem.helper_functions:
            self.check_source(
                node, self.function_source(node.parameters, node.body), check_names=True
            )
        for node in problem.custom_classes:
            self.names(list(node.members), identifiers=True)
            if node.class_type == "override" and not node.base_class.strip():
                self.add(node, "required", field="base_class")
            elif node.class_type == "override":
                try:
                    base = _resolve(node.base_class)
                    if not isinstance(base, type):
                        raise ValueError(node.base_class)
                    for member in node.members:
                        if not callable(getattr(base, member.name, None)):
                            self.add(
                                member, "reference", field="method", name=member.name
                            )
                except (AttributeError, ValueError) as exc:
                    self.add(node, "field", field="base_class", reason=str(exc))
            for member in node.members:
                self.check_source(
                    member,
                    self.function_source(
                        getattr(member, "parameters", "self"), member.body
                    ),
                )
        for node in problem.root.iter_nodes():
            self.node(node)
        for nodes in (
            problem.parts(),
            [instance for part in problem.parts() for instance in part.instances],
            problem.fea_components(),
            problem.material_nodes(),
        ):
            self.names(nodes)
        if (
            problem.geometry is not None
            and not problem.parts()
            and not self.overridden(problem.geometry)
        ):
            self.add(problem.geometry, "required", field="parts")
        if (
            problem.materials is not None
            and not problem.material_nodes()
            and not self.overridden(problem.materials)
        ):
            self.add(problem.materials, "required", field="materials")
        self.steps()
        self.objectives()
        self.updaters()
        return self.errors
