"""Context-aware, dependency-free completions for MorphOpt code slots.

The generated source is the authority for execution, but hand-written code
slots only edit a method body.  This module supplies the small, stable part of
that method context which is useful while typing: known ``self`` attributes,
current surface indices, and load/interface names.  It intentionally does not
attempt full Python type inference; an optional language-server integration can
be added behind the same item interface later.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..model.problem import ProblemDefinition


@dataclass(frozen=True)
class CompletionItem:
    """One completion candidate shown in the editor popup."""

    label: str
    insert_text: str


_PYTHON_ITEMS = (
    CompletionItem("return", "return "),
    CompletionItem("if", "if "),
    CompletionItem("for", "for "),
    CompletionItem("import torch", "import torch"),
    CompletionItem("len()", "len()"),
    CompletionItem("range()", "range()"),
)

_OBJECTIVE_ITEMS = (
    CompletionItem("self", "self"),
    CompletionItem("self.fe", "self.fe"),
    CompletionItem("self.fe_results", "self.fe_results"),
    CompletionItem("torch.abs", "torch.abs("),
    CompletionItem("torch.cat", "torch.cat([])"),
    CompletionItem("torch.clamp", "torch.clamp("),
    CompletionItem("torch.flip", "torch.flip("),
    CompletionItem("torch.mean", "torch.mean("),
    CompletionItem("torch.norm", "torch.norm("),
    CompletionItem("torch.stack", "torch.stack([])"),
    CompletionItem("torch.sum", "torch.sum("),
    CompletionItem("torch.where", "torch.where("),
)

_TENSOR_MEMBERS = (
    "abs()", "backward()", "clone()", "cpu()", "detach()", "device",
    "dtype", "flatten()", "item()", "max()", "mean()", "min()", "norm()",
    "numpy()", "reshape()", "shape", "squeeze()", "sum()", "to()",
    "unsqueeze()", "view()",
)

_SURFACE_CONSTRAINT_ITEMS = (
    CompletionItem("self", "self"),
    CompletionItem("self.surface_list", "self.surface_list"),
    CompletionItem("ThisController", "ThisController"),
    CompletionItem("ThisController.Params.GeometryParams",
                   "ThisController.Params.GeometryParams"),
    CompletionItem("surface = self.surface_list[0]",
                   "surface = self.surface_list[0]"),
    CompletionItem("control_points = surface._cps.reshape(...)",
                   "control_points = surface._cps.reshape(\n"
                   "    surface.model.size[0], surface.model.size[1], 3)"),
    CompletionItem("torch.flip(..., dims=[1])", "torch.flip("),
    CompletionItem("pass", "pass"),
)

_DESIGN_FIELD_ITEMS = (
    CompletionItem("nodes", "nodes"),
    CompletionItem("return nodes", "return nodes"),
    CompletionItem("torch.where", "torch.where(, , )"),
    CompletionItem("torch.clamp", "torch.clamp(, min=, max=)"),
)


def completion_items(slot_key: str,
                     problem: "ProblemDefinition | None" = None,
                     member_expression: str | None = None,
                     ) -> list[CompletionItem]:
    """Return completions appropriate for one hand-written code slot.

    ``slot_key`` intentionally accepts both model storage names (for example
    ``"_objective_function"``) and generated method names.  Candidate labels
    remain deterministic; model-derived entries are appended in tree order.
    """
    key = slot_key.lstrip("_")
    items = list(_PYTHON_ITEMS)
    if key in {"objective_function", "get_metrics"}:
        items.extend(_OBJECTIVE_ITEMS)
        items.extend(_objective_result_items(problem))
        items.extend(_objective_reference_items(problem))
        if _is_tensor_expression(member_expression):
            items.extend(_tensor_items(member_expression))
    elif key == "apply_surface_constraints":
        items.extend(_SURFACE_CONSTRAINT_ITEMS)
        items.extend(_surface_items(problem))
    elif key == "map_bsp_designfield":
        items.extend(_DESIGN_FIELD_ITEMS)
    return _unique_items(items)


def _is_tensor_expression(expression: str | None) -> bool:
    """Whether a member expression is a known ``FEAResult.GC`` tensor."""
    if not expression:
        return False
    return bool(re.search(r"\.GC(?:\[[^\]]+\])?$", expression))


def _tensor_items(expression: str) -> list[CompletionItem]:
    """Return Tensor members as full paths for the current GC expression."""
    return [CompletionItem(member, f"{expression}.{member}")
            for member in _TENSOR_MEMBERS]


def _objective_reference_items(problem: "ProblemDefinition | None") -> list[CompletionItem]:
    if problem is None:
        return []
    items: list[CompletionItem] = []
    names = [interface.name for interface in problem.amplitude_interfaces()]
    for result_index in _result_indices(problem):
        for name in names:
            items.append(CompletionItem(
                f"result[{result_index}].jacobian[{name!r}]",
                f"self.fe_results[{result_index}].jacobian[{name!r}]",
            ))
    items.extend(CompletionItem(f"load name: {name}", repr(name))
                 for name in names)
    return items


def _objective_result_items(problem: "ProblemDefinition | None") -> list[CompletionItem]:
    """Build result candidates from the current number of load steps."""
    items: list[CompletionItem] = []
    for result_index in _result_indices(problem):
        result = f"self.fe_results[{result_index}]"
        items.extend((
            CompletionItem(result, result),
            CompletionItem(f"{result}.GC", f"{result}.GC"),
            CompletionItem(f"{result}.GC[-2]", f"{result}.GC[-2]"),
            CompletionItem(f"{result}.jacobian", f"{result}.jacobian"),
            CompletionItem(f"return result[{result_index}] displacement",
                           f"return {result}.GC[-2]"),
        ))
    return items


def _result_indices(problem: "ProblemDefinition | None") -> range:
    """Result-list indices currently valid for objective code completion."""
    step_count = problem.steps.num_steps if problem is not None and problem.steps else 1
    return range(max(1, int(step_count)))


def _surface_items(problem: "ProblemDefinition | None") -> list[CompletionItem]:
    if problem is None:
        return []
    return [
        CompletionItem(
            f"self.surface_list[{index}] ({surface.surface_type})",
            f"self.surface_list[{index}]",
        )
        for index, surface in enumerate(problem.surfaces())
    ]


def _unique_items(items: list[CompletionItem]) -> list[CompletionItem]:
    """Preserve the first candidate for each displayed label."""
    seen: set[str] = set()
    unique: list[CompletionItem] = []
    for item in items:
        if item.label not in seen:
            seen.add(item.label)
            unique.append(item)
    return unique
