"""Named load cases, reference tracking and workspace-owned case generation."""

from __future__ import annotations

import ast
import hashlib
import io
import json
import math
import tokenize
from uuid import uuid4

from ...optcore.quadrature import actuation_boundary_gauss_points
from ...paths import sanitize_name
from ..i18n import localized_message, tr
from ..model.problem import ProblemDefinition

WORKSPACE_AXES = {
    "workspace_plane": [0, 2],
    "workspace_space": [0, 1, 2],
    "workspace_rotation": [3, 4, 5],
    "workspace_pose": [0, 2, 4],
}


def code_fields(problem: ProblemDefinition) -> list[tuple[object, str]]:
    fields = [(problem, "helper_code")]
    if problem.objective:
        fields.extend(
            (term, "body")
            for term in [
                *problem.objective.objective_terms,
                *problem.objective.metrics_terms,
            ]
            if "body" in term
        )
    for node in [
        *problem.helper_functions,
        *problem.helper_variables,
        *problem.custom_classes,
    ]:
        for child in node.iter_nodes():
            for key in ("body", "value"):
                if child.has_field(key) and isinstance(child.get_field(key), str):
                    fields.append((child, key))
    return fields


def _code_case_names(owner: object, key: str) -> set[str]:
    text = owner.get(key, "") if isinstance(owner, dict) else getattr(owner, key)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def term_case_names(term: dict) -> set[str]:
    names = set(term.get("case_names", []))
    if term.get("step_name"):
        names.add(term["step_name"])
    if "body" in term:
        names.update(_code_case_names(term, "body"))
    return names


def objective_terms(problem: ProblemDefinition) -> list[dict]:
    if problem.objective is None:
        return []
    return [*problem.objective.objective_terms, *problem.objective.metrics_terms]


def referenced_steps(
    problem: ProblemDefinition, exclude: tuple[dict, ...] = ()
) -> set[str]:
    names = set()
    for term in objective_terms(problem):
        if not any(term is omitted for omitted in exclude):
            if term.get("step_name"):
                names.add(term["step_name"])
            names.update(term.get("case_names", []))
    if problem.solver:
        names.update(name for group in problem.solver.task_step_list for name in group)
    for owner, key in code_fields(problem):
        if not any(owner is omitted for omitted in exclude):
            names.update(_code_case_names(owner, key))
    return names


def case_objectives(problem: ProblemDefinition, name: str) -> list[dict]:
    """Return objective and metric terms that reference the named case."""
    return [term for term in objective_terms(problem) if name in term_case_names(term)]


def unused_cases(problem: ProblemDefinition, terms: list[dict]) -> list[str]:
    """List cases made unreferenced by removing these terms, in registration order."""
    candidates = set().union(*(term_case_names(term) for term in terms))
    owners = {term["id"] for term in terms if "id" in term}
    candidates.update(
        name for name, owner in problem.steps.generated_by.items() if owner in owners
    )
    retained = referenced_steps(problem, exclude=tuple(terms))
    return [
        name
        for name in problem.steps.step_values
        if name in candidates and name not in retained
    ]


def remove_objectives(
    problem: ProblemDefinition, terms: list[dict], remove_unused: bool
) -> None:
    """Remove selected terms and apply the user's case-retention choice."""
    removable = unused_cases(problem, terms) if remove_unused else []
    for collection in (
        problem.objective.objective_terms,
        problem.objective.metrics_terms,
    ):
        collection[:] = [
            term for term in collection if not any(term is removed for removed in terms)
        ]
    owners = {term["id"] for term in terms if "id" in term}
    for name, owner in list(problem.steps.generated_by.items()):
        if owner in owners:
            del problem.steps.generated_by[name]
    for name in removable:
        del problem.steps.step_values[name]
        problem.steps.generated_by.pop(name, None)


def _replace_code_case(problem: ProblemDefinition, old: str, new: str | None) -> None:
    for owner, key in code_fields(problem):
        text = owner.get(key, "") if isinstance(owner, dict) else getattr(owner, key)
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
            for index, token in enumerate(tokens):
                if (
                    token.type == tokenize.STRING
                    and ast.literal_eval(token.string) == old
                ):
                    tokens[index] = token._replace(string=repr(new))
            updated = tokenize.untokenize(tokens)
        except (SyntaxError, ValueError, tokenize.TokenError):
            continue
        if isinstance(owner, dict):
            owner[key] = updated
        else:
            setattr(owner, key, updated)


def remove_case(
    problem: ProblemDefinition, name: str, remove_terms: bool, remove_unused: bool
) -> None:
    """Delete a case, removing its referring terms or clearing their references."""
    terms = case_objectives(problem, name)
    if remove_terms and terms:
        remove_objectives(problem, terms, remove_unused)
    else:
        for term in terms:
            if "step_name" in term:
                term["step_name"] = None
            if "case_names" in term:
                term["case_names"] = []
    _replace_code_case(problem, name, None)
    if problem.solver:
        problem.solver.task_step_list = [
            remaining
            for group in problem.solver.task_step_list
            if (remaining := [case for case in group if case != name])
        ]
    problem.steps.step_values.pop(name, None)
    problem.steps.generated_by.pop(name, None)


def rename_case(problem: ProblemDefinition, old: str, new: str) -> None:
    new = new.strip()
    if (
        not new
        or new != sanitize_name(new)
        or any(
            name != old and name.casefold() == new.casefold()
            for name in problem.steps.step_values
        )
    ):
        raise ValueError(localized_message("ui.load_cases.invalid_name"))
    if new == old:
        return
    problem.steps.step_values = {
        new if name == old else name: values
        for name, values in problem.steps.step_values.items()
    }
    if old in problem.steps.generated_by:
        problem.steps.generated_by[new] = problem.steps.generated_by.pop(old)
    if problem.objective:
        for term in [
            *problem.objective.objective_terms,
            *problem.objective.metrics_terms,
        ]:
            if term.get("step_name") == old:
                term["step_name"] = new
            if "case_names" in term:
                term["case_names"] = [
                    new if name == old else name for name in term["case_names"]
                ]
    if problem.solver:
        problem.solver.task_step_list = [
            [new if name == old else name for name in group]
            for group in problem.solver.task_step_list
        ]
    _replace_code_case(problem, old, new)


def workspace_spec(term: dict, problem: ProblemDefinition) -> dict:
    axes = WORKSPACE_AXES[term["kind"]]
    inputs = term.get("inputs", [])
    if len(inputs) != len(axes):
        raise ValueError(
            localized_message(
                "ui.workspace_objective.requires_inputs",
                count=len(axes),
                selected=len(inputs),
            )
        )
    if term.get("reference_point_name") not in problem.reference_point_names():
        raise ValueError(localized_message("ui.workspace_objective.requires_reference"))
    components = {load.name: load for load in problem.amplitude_components()}
    seen = set()
    for entry in inputs:
        upper = float(entry["upper"])
        if not math.isfinite(upper) or upper <= 0:
            raise ValueError(localized_message("ui.workspace_objective.invalid_upper"))
        if not entry["parameters"]:
            raise ValueError(
                localized_message("ui.workspace_objective.requires_parameter")
            )
        for name, component in entry["parameters"]:
            if (
                name not in components
                or not 0 <= component < components[name].num_values
                or (name, component) in seen
            ):
                raise ValueError(
                    localized_message("ui.workspace_objective.invalid_parameters")
                )
            seen.add((name, component))
    order = int(term.get("gauss_order", 2))
    points, weights, tangents, orientations = actuation_boundary_gauss_points(
        [(0.0, float(entry["upper"])) for entry in inputs], order
    )
    return {
        "axes": axes,
        "points": points,
        "weights": weights.tolist(),
        "tangents": tangents.tolist(),
        "orientations": orientations.tolist(),
    }


def workspace_case_status(term: dict, problem: ProblemDefinition) -> str:
    """Describe registered Gauss-point cases or the missing workspace settings."""
    try:
        spec = workspace_spec(term, problem)
    except (ValueError, TypeError, KeyError) as error:
        return str(error)
    names = term.get("case_names", [])
    registered = len(names) == len(spec["points"]) and all(
        name in problem.steps.step_values for name in names
    )
    if registered:
        key = "ui.workspace_objective.cases_generated"
    elif not names and "case_signature" in term:
        key = "ui.workspace_objective.cases_cleared"
    else:
        key = "ui.workspace_objective.case_count"
    return tr(key, count=len(spec["points"]))


def synchronize_workspaces(problem: ProblemDefinition) -> None:
    if problem.steps is None or problem.objective is None:
        return
    steps = problem.steps
    terms = [
        term
        for term in problem.objective.objective_terms
        if term.get("type") == "workspace"
    ]
    active = set()
    for term in terms:
        owner = term.setdefault("id", uuid4().hex)
        active.add(owner)
        try:
            spec = workspace_spec(term, problem)
        except (ValueError, KeyError, TypeError):
            continue
        signature = hashlib.sha256(
            json.dumps([term["inputs"], term["gauss_order"]], sort_keys=True).encode()
        ).hexdigest()
        names = term.get("case_names", [])
        # Keep deliberately cleared references empty until the sampling changes.
        complete = len(names) == len(spec["points"]) and all(
            name in steps.step_values for name in names
        )
        if term.get("case_signature") == signature and (not names or complete):
            continue
        retained = referenced_steps(problem, exclude=(term,))
        for name, case_owner in list(steps.generated_by.items()):
            if case_owner == owner:
                if name not in retained:
                    steps.step_values.pop(name, None)
                steps.generated_by.pop(name, None)
        names = []
        prefix = term.setdefault("name", f"workspace_{len(active)}")
        for index, point in enumerate(spec["points"], 1):
            base = f"{prefix}_case_{index}"
            name, suffix = base, 2
            while name in steps.step_values:
                name = f"{base}_{suffix}"
                suffix += 1
            values = {
                load: [0.0] * load.num_values for load in problem.amplitude_components()
            }
            loads = {load.name: load for load in values}
            for entry, amplitude in zip(term["inputs"], point):
                for load, component in entry["parameters"]:
                    values[loads[load]][component] = float(amplitude)
            steps.step_values[name] = values
            steps.generated_by[name] = owner
            names.append(name)
        term["case_names"], term["case_signature"] = names, signature
    for name, owner in list(steps.generated_by.items()):
        if owner not in active:
            del steps.generated_by[name]
