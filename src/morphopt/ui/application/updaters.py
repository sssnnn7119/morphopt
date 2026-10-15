"""Updater item construction and normalization, without Qt controls."""
from __future__ import annotations
from ..model import schemas as S
from ..model.problem import SurfaceNode


def symmetry_item(item_type: str, surfaces: list[SurfaceNode]) -> dict | None:
    item = S.symmetry_constraint(item_type)
    if item_type != "Custom":
        spec = S.SURFACE_SYMMETRY_CONSTRAINTS[item_type]
        compatible = [index for index, surface in enumerate(surfaces) if S.surface_factory_for_type(surface.surface_type) == spec["factory"]]
        if not compatible or (spec.get("related_surface") and len(compatible) < 2):
            return None
        if spec.get("related_surface"):
            item["related_surface_index"] = None
    return item


def updater_item(item_type: str, category: str, custom_class: str = "") -> dict:
    item = {"type": item_type, "params": {} if item_type == "Custom" else S.updater_item_defaults(
        item_type,
        category,
    )}
    if custom_class:
        item["custom_class"] = custom_class
    return item


def distance_matrix(stored, size: int, default: float = 2.5) -> list[list[float | str]]:
    rows: list[list[float | str]] = []
    if isinstance(stored, (list, tuple)):
        for row in stored:
            if isinstance(row, (list, tuple)):
                rows.append([value if isinstance(value, str) else float(value) for value in row])
            elif isinstance(row, (int, float)):
                rows.append([float(row)])
    out = []
    for index in range(size):
        row = rows[index] if index < len(rows) else []
        out.append(row[:size] + [default] * (size - len(row)))
    return out

def specs_for(group: str, category: str):
    out = []
    cat = S.UPDATER_CATALOG.get(category, {})
    for name, spec in cat.items():
        if spec["group"] == group and not spec.get("hidden", False):
            s = dict(spec)
            s["_type"] = name
            out.append(s)
    return out


def find_spec(itype: str, category: str):
    cat = S.UPDATER_CATALOG.get(category, {})
    spec = cat.get(itype)
    return dict(spec) if spec else None


def as_bool_list(cur, n: int, default: bool = True) -> list[bool]:
    """Coerce an ``if_update`` value into a length-``n`` bool list.

    One entry per surface (index 0, 1, …).  ``None`` / scalars are expanded;
    a too-short list is padded with ``default``.
    """
    if isinstance(cur, (list, tuple)):
        return [bool(cur[i]) if i < len(cur) else default for i in range(n)]
    if cur is None:
        return [default] * n
    return [bool(cur)] * n


from dataclasses import dataclass
from ..model.problem import Node, ProblemDefinition, UpdaterNode


@dataclass(frozen=True)
class UpdaterSection:
    group: str
    config: dict
    index: int
    count: int
    target: Node | None


def updater_sections(
    updater: UpdaterNode,
    problem: ProblemDefinition,
    group: str | None = None,
    index: int | None = None,
) -> list[UpdaterSection]:
    sections = []
    for kind, configs, target_for in (
        ("geometry", updater.geometry, problem.config_part_node),
        ("materials", updater.materials, problem.config_material_node),
    ):
        if group is not None and kind != group:
            continue
        selected = min(max(index, 0), len(configs) - 1) if index is not None and configs else None
        for position, config in enumerate(configs):
            if selected is None or position == selected:
                sections.append(UpdaterSection(kind, config, position, len(configs), target_for(config)))
    return sections


class UpdaterItems:
    """Shared ordered-item policy for objectives, penalties and symmetries."""
    def __init__(self, config: dict, group: str, category: str, problem: ProblemDefinition):
        self.config, self.group, self.category, self.problem = config, group, category, problem
        self.key = {"objectives": "objective_functions", "geometry_symmetry": "symmetry_constraints", "constraints": "constraints"}[category]

    @property
    def items(self) -> list[dict]:
        return self.config.get(self.key, [])

    @property
    def surfaces(self):
        target = self.problem.config_part_node(self.config) if self.group == "geometry" else None
        return target.surfaces() if target is not None else []

    def specs(self) -> dict[str, dict]:
        if self.category == "geometry_symmetry":
            allowed = set(S.available_surface_symmetry_types(surface.surface_type for surface in self.surfaces)) | {"Custom"}
            return {name: spec for name, spec in S.SURFACE_SYMMETRY_CONSTRAINTS.items() if name in allowed}
        return {spec["_type"]: spec for spec in specs_for(self.group, self.category)}

    def spec(self, item: dict) -> dict:
        if self.category == "geometry_symmetry":
            return S.SURFACE_SYMMETRY_CONSTRAINTS.get(item["type"], {})
        return find_spec(item["type"], self.category) or {}

    def compatible_surfaces(self, spec: dict):
        return [(index, surface) for index, surface in enumerate(self.surfaces) if S.surface_factory_for_type(surface.surface_type) == spec["factory"]]

    def custom_choices(self):
        from ..codegen.custom_classes import custom_options, updater_item_base
        candidates = {name: expression for name in self.specs() if (expression := updater_item_base(
            name,
            self.category,
        )) is not None}
        choices = custom_options(self.problem, candidates)
        taken = {custom.name for _, custom in choices}
        choices.extend((name, custom) for name, custom in custom_options(
            self.problem,
            {"Custom": updater_item_base("Custom", self.category, self.group)},
        ) if custom.name not in taken)
        return choices

    def add(self, item_type: str, custom_class: str = "") -> bool:
        item = symmetry_item(item_type, self.surfaces) if self.category == "geometry_symmetry" else updater_item(
            item_type,
            self.category,
            custom_class,
        )
        if item is None:
            return False
        self.config.setdefault(self.key, []).append(item)
        return True

    def remove(self, item: dict) -> None:
        index = next(index for index, candidate in enumerate(self.items) if candidate is item)
        self.items.pop(index)

    def move(self, item: dict, offset: int) -> bool:
        source = next(index for index, candidate in enumerate(self.items) if candidate is item)
        target = source + offset
        if not 0 <= target < len(self.items):
            return False
        self.items[source], self.items[target] = self.items[target], self.items[source]
        return True


def editor_signature(problem: ProblemDefinition, sections: list[UpdaterSection], category: str | None) -> tuple:
    """Structural changes which require rebuilding an updater page, excluding values."""
    from ..model.problem import PartNode
    records = []
    for section in sections:
        surfaces = section.target.surfaces() if isinstance(section.target, PartNode) else []
        item_order = tuple(
            tuple((id(item), item["type"], item.get("custom_class")) for item in section.config.get(key, []))
            for key in ("objective_functions", "constraints", "symmetry_constraints")
        )
        records.append((section.group, id(section.config), section.target.name if section.target else None,
                        tuple(id(surface) for surface in surfaces), item_order))
    return (id(problem), category, tuple(records), tuple(helper.name for helper in problem.helper_variables),
            tuple((custom.name, custom.base_class) for custom in problem.custom_classes))
