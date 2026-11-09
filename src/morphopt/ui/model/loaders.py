"""JSON persistence with schema projection at the file import boundary.

Supported content is retained, omissions use current defaults, and discarded
content is reported. Internal model hydration remains strict.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

from ...constants import CONSTANT
from ..i18n import LocalizedMessage, localized_message
from ..schemes.base import get_template
from .configuration import (
    geometry_updater_config, materials_updater_config,
    metric_term_config, objective_term_config,
)
from .fields import field_defaults
from .problem import Node, ProblemDefinition, ProblemNode
from .registry import (
    CONFIGURATION_CLASS_PATHS, NODE_FAMILIES, NODE_TYPES, SURFACE_SYMMETRY_CONSTRAINTS,
    UPDATER_CONSTRAINTS, UPDATER_OBJECTIVES, resolve_node_type,
)
from .strategies import STRATEGY_CATALOG, strategy_specs

MORPH_SUFFIX = ".morph"


def save_morph(problem: ProblemDefinition, path: str | Path) -> str:
    """Write ``problem`` to a ``*.morph`` file (appends suffix if missing)."""
    path = str(path)
    if not path.endswith(MORPH_SUFFIX):
        path += MORPH_SUFFIX
    Path(path).write_text(json.dumps(problem.to_dict(), indent=2, ensure_ascii=False),
                          encoding="utf-8")
    return path


def load_morph(path: str | Path, *, issues: list[LocalizedMessage] | None = None) -> ProblemDefinition:
    """Read supported fields, default omissions and report discarded content."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(localized_message("ui.import.invalid_document"))
    reader = _DefinitionReader()
    problem = reader.read(data)
    if issues is not None:
        issues.extend(reader.issues)
    else:
        for issue in reader.issues:
            logging.getLogger(__name__).warning("%s", issue)
    return problem


class _DefinitionReader:
    """Project a file onto the current schema without weakening model constructors."""

    def __init__(self) -> None:
        self.issues: list[LocalizedMessage] = []

    def note(self, key: str, path: str, **values: object) -> None:
        self.issues.append(localized_message(f"ui.import.{key}", path=path, **values))

    def mapping(self, value: object, defaults: dict, path: str, optional: tuple[str, ...] = ()) -> dict:
        if not isinstance(value, dict):
            self.note("skipped", path, reason=localized_message("ui.import.expected_object"))
            return deepcopy(defaults)
        unknown = value.keys() - defaults.keys() - set(optional)
        missing = defaults.keys() - value.keys()
        if unknown:
            self.note("ignored_fields", path, fields=", ".join(sorted(unknown)))
        if missing:
            self.note("default_fields", path, fields=", ".join(sorted(missing)))
        return {
            **deepcopy(defaults),
            **{key: item for key, item in value.items() if key in defaults or key in optional},
        }

    def sequence(self, value: object, path: str) -> list:
        if isinstance(value, list):
            return value
        self.note("skipped", path, reason=localized_message("ui.import.expected_list"))
        return []

    def node(self, value: object, path: str) -> Node | None:
        if not isinstance(value, dict) or not isinstance(value.get("kind"), str) or value["kind"] not in NODE_TYPES:
            self.note("skipped", path, reason=str(value.get("kind") if isinstance(value, dict) else type(value).__name__))
            return None
        kind = value["kind"]
        raw = value.get("params", {})
        if not isinstance(raw, dict):
            self.note("skipped", f"{path}.params", reason=localized_message("ui.import.expected_object"))
            raw = {}
        base = NODE_TYPES[kind]
        if kind in NODE_FAMILIES and base.type_field not in raw:
            default_type = next(iter(NODE_FAMILIES[kind]))
            self.note("default_fields", path, fields=f"{base.type_field}={default_type}")
            raw = {**raw, base.type_field: default_type}
        try:
            node_type = resolve_node_type(kind, raw)
        except (TypeError, ValueError) as error:
            self.note("skipped", path, reason=str(error))
            return None
        defaults = node_type().to_dict()["params"]
        params = self.mapping(raw, defaults, f"{path}.params", ("custom_class",))
        if kind == "updater":
            for group, factory in (("geometry", geometry_updater_config), ("materials", materials_updater_config)):
                configs = self.sequence(params[group], f"{path}.{group}")
                params[group] = [
                    self.updater(config, factory(), group, f"{path}.{group}[{index}]")
                    for index, config in enumerate(configs)
                ]
        elif kind == "objective":
            for field, factory, default_type in (
                ("objective_terms", objective_term_config, CONSTANT.UI.OBJECTIVE.DEFAULT_TYPE),
                ("metrics_terms", metric_term_config, CONSTANT.UI.METRIC.DEFAULT_TYPE),
            ):
                params[field] = self.terms(params[field], factory, f"{path}.{field}", default_type)
        node_data = self.mapping(value, {"kind": kind, "name": "", "params": {}, "children": []}, path)
        try:
            node = node_type(name=node_data["name"], params=params, children=[])
            node.custom_class = str(params.get("custom_class") or "")
        except (TypeError, ValueError) as error:
            self.note("skipped", path, reason=str(error))
            return None
        for index, child in enumerate(self.sequence(node_data["children"], f"{path}.children")):
            child_path = f"{path}.children[{index}]"
            restored = self.node(child, child_path)
            if restored is not None:
                try:
                    node.add_child(restored)
                except (TypeError, ValueError) as error:
                    self.note("skipped", child_path, reason=str(error))
        return node

    def terms(self, value: object, factory: Callable[[str], dict], path: str, default_type: str) -> list[dict]:
        terms = []
        for index, term in enumerate(self.sequence(value, path)):
            item_path = f"{path}[{index}]"
            try:
                defaults = factory(term.get("type", default_type))
            except (AttributeError, KeyError, TypeError, ValueError) as error:
                self.note("skipped", item_path, reason=str(error))
                continue
            restored = self.mapping(term, defaults, item_path, ("name", "id", "case_signature"))
            if restored.get("type") == "workspace":
                restored["inputs"] = [
                    self.mapping(item, {"parameters": [], "upper": 0.0}, f"{item_path}.inputs[{i}]")
                    for i, item in enumerate(self.sequence(restored["inputs"], f"{item_path}.inputs"))
                ]
            terms.append(restored)
        return terms

    def updater(self, value: object, defaults: dict, group: str, path: str) -> dict:
        config = self.mapping(value, defaults, path, ("custom_class",))
        categories = [("objective_functions", UPDATER_OBJECTIVES), ("constraints", UPDATER_CONSTRAINTS)]
        if group == "geometry":
            categories.append(("symmetry_constraints", SURFACE_SYMMETRY_CONSTRAINTS))
        for field, catalog in categories:
            items = []
            for index, item in enumerate(self.sequence(config[field], f"{path}.{field}")):
                item_path = f"{path}.{field}[{index}]"
                if not isinstance(item, dict):
                    self.note("skipped", item_path, reason=localized_message("ui.import.expected_object"))
                    continue
                default_items = defaults[field]
                default_type = default_items[0]["type"] if default_items else next(iter(catalog))
                name = item.get("type", default_type)
                if not isinstance(name, str):
                    self.note("skipped", item_path, reason=str(name))
                    continue
                if name == "Custom" and item.get("custom_class"):
                    item_defaults = {"type": name, "params": {}}
                elif name in catalog:
                    item_defaults = {"type": name, "params": catalog[name].default_parameters()}
                else:
                    self.note("skipped", item_path, reason=str(name))
                    continue
                if field == "symmetry_constraints" and name != "Custom":
                    item_defaults["surface_index"] = None
                    if catalog[name].related_surface:
                        item_defaults["related_surface_index"] = None
                restored = self.mapping(item, item_defaults, item_path, ("custom_class",))
                restored["params"] = self.mapping(restored["params"], item_defaults["params"], f"{item_path}.params")
                items.append(restored)
            config[field] = items
        for key in STRATEGY_CATALOG:
            specs = strategy_specs(key, group)
            raw = config[key]
            name = raw.get("type") if isinstance(raw, dict) else None
            if not isinstance(name, str) or name not in specs:
                self.note("skipped", f"{path}.{key}", reason=str(name))
                config[key] = deepcopy(defaults[key])
                continue
            spec = specs[name]
            policy_defaults = {"type": name, "params": field_defaults(spec.fields)}
            policy = self.mapping(raw, policy_defaults, f"{path}.{key}")
            policy["params"] = self.mapping(policy["params"], policy_defaults["params"], f"{path}.{key}.params")
            config[key] = policy
        return config

    def read(self, data: dict) -> ProblemDefinition:
        defaults = ProblemDefinition().to_dict()
        if data.get("version") != defaults["version"]:
            self.note("version", "version", version=data.get("version"), current=defaults["version"])
        document = self.mapping(data, defaults, "document")
        try:
            get_template(document["scheme"])
        except (KeyError, TypeError, ValueError):
            self.note("skipped", "scheme", reason=str(document["scheme"]))
            document["scheme"] = defaults["scheme"]
        root_data = document["root"]
        if not isinstance(root_data, dict):
            root_data = {}
        if root_data.get("kind") != "problem":
            self.note("default_fields", "root", fields="kind=problem")
            root_data = {**root_data, "kind": "problem"}
        root = self.node(ProblemDefinition._normalize_part_names(root_data), "root")
        if not isinstance(root, ProblemNode):
            root = ProblemNode(name=document["label"])
        for kind in ("geometry", "loads", "steps", "materials", "objective", "solver", "updater"):
            if not any(node.kind == kind for node in root.children):
                self.note("default_fields", "root", fields=kind)
                root.add_child(NODE_TYPES[kind]())
        document["root"] = root
        for field, expected in (("custom_classes", "custom_class"), ("helper_variables", "helper_variable"), ("helper_functions", "helper_function")):
            nodes = []
            for index, value in enumerate(self.sequence(document[field], field)):
                node = self.node(value, f"{field}[{index}]")
                if node is not None and node.kind == expected:
                    nodes.append(node)
                elif node is not None:
                    self.note("skipped", f"{field}[{index}]", reason=node.kind)
            document[field] = nodes
        document["class_bindings"] = self.mapping(
            document["class_bindings"], {}, "class_bindings",
            tuple(CONFIGURATION_CLASS_PATHS.values()),
        )
        document.pop("version")
        problem = ProblemDefinition(**document)
        problem.resolve_references()
        return problem
