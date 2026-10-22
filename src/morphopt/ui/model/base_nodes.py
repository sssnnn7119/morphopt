"""Shared node bases, field serialization and node-local behavior."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from copy import deepcopy
from typing import TYPE_CHECKING, Any, ClassVar, Self, cast

from ..i18n import localized_message

if TYPE_CHECKING:
    from .node_types.structural import InstanceNode

from .fields import FieldSpec, field_defaults

# ---------------------------------------------------------------------------
# Node kinds of the problem-definition task tree (the explicit taxonomy).
#
# A problem is a fixed, ordered set of persisted sections rooted at a
# ``ProblemNode``.  The visual model tree may group related sections (the UI
# shows ``loads`` and ``steps`` under one ``loads_group`` row), but that
# presentation node is transient and is not serialized::
#
#     problem
#     ├── geometry   -- children: PartNode* (each owns InstanceNode*
#     │                  and optional SurfaceNode*; 0 = outer, 1.. = cavities)
#     ├── loads      -- children: FEAComponentNode* (BC / RP / forces / contacts)
#     ├── steps      -- one StepsNode   (step count + per-component amplitudes)
#     ├── materials  -- children: MaterialNode* (Part + element assignments)
#     ├── objective  -- one ObjectiveNode
#     ├── solver     -- one SolverNode
#     └── updater    -- one UpdaterNode (geometry / materials optimiser config)
#
# This module contains only generic node bases and shared typed families.
# Persisted concrete node classes live in :mod:`node_types`: each pins its
# ``kind`` and type name, declares fields, and is registered for hydration.
# The ``materials`` section is persisted explicitly and
# :meth:`Node.from_dict` re-hydrates each entry into its concrete subclass.
# ---------------------------------------------------------------------------

KIND_PROBLEM = "problem"
KIND_GEOMETRY = "geometry"
KIND_PART = "part"
KIND_CAD_OPERATION = "cad_operation"
KIND_INSTANCE = "instance"
KIND_SURFACE = "surface"
KIND_LOADS = "loads"
KIND_FEA_COMPONENT = "fea_component"
KIND_STEPS = "steps"
KIND_MATERIAL = "material"
KIND_MATERIALS = "materials"
KIND_OBJECTIVE = "objective"
KIND_SOLVER = "solver"
KIND_UPDATER = "updater"

# Fields whose persisted value is a name, but whose in-memory value is a
# direct node reference.  Names are deliberately confined to the .morph/UI/
# generated-code boundary; model behaviour follows the referenced object.
INSTANCE_REFERENCE_FIELDS = {
    "instance_name": "instance",
    "instance_name1": "instance1",
    "instance_name2": "instance2",
}
REFERENCE_POINT_FIELDS = {
    "rp_name": "reference_point",
    "rp_name1": "reference_point1",
    "rp_name2": "reference_point2",
}


#: canonical order of the top-level sections inside a problem tree.
SECTION_ORDER = (
    KIND_GEOMETRY,
    KIND_LOADS,
    KIND_STEPS,
    KIND_MATERIALS,
    KIND_OBJECTIVE,
    KIND_SOLVER,
    KIND_UPDATER,
)


class Node:
    """A node in the problem-definition tree (generic base).

    Subclasses pin :attr:`kind` to a fixed value; a bare ``Node`` still
    accepts any ``kind`` for tree infrastructure and tests.

    Concrete classes declare typed parameter attributes and immutable field
    metadata. Containers own typed collections (parts, instances, surfaces,
    operations, materials or class members); leaves cannot contain children.
    ``children`` is a read-only traversal and persistence view. Dynamic forms
    use ``get_field`` / ``set_field`` to edit the declared attributes.

    Parameters
    ----------
    kind:
        Machine-readable node type, e.g. ``"surface"``, ``"fea_component"``,
        ``"material"``.  Defaults to the subclass kind.  Every kind maps to a
        concrete class in :mod:`morphopt.ui.model.registry`.
    name:
        Display / reference name. For FEA components this is the name used
        in the load-step matrix and in generated FEA code (e.g. ``pressure_1``).
    params:
        Initial parameter values (declared keys -> typed attributes).
    children:
        Ordered child nodes (e.g. surfaces inside ``geometry``).
    """

    kind: str = ""
    type_name: ClassVar[str] = ""
    type_field: ClassVar[str] = ""
    backend_class: ClassVar[str] = ""
    label_key: ClassVar[str] = ""
    is_updatable: ClassVar[bool] = False
    custom_only: ClassVar[bool] = False
    hidden: ClassVar[bool] = False
    fields: ClassVar[tuple[FieldSpec, ...]] = ()

    #: names of the parameters this node exposes as real typed attributes.
    _FIELDS: tuple[str, ...] = ()

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict | None = None,
        children: Sequence[Node] | None = None,
    ) -> None:
        self.kind = kind or type(self).kind or ""
        self.name = name
        for child in children or ():
            self.add_child(child)
        self.custom_class: str = str((params or {}).get("custom_class") or "")
        # ``params`` is only forwarded by ``Node.from_dict`` for hydration;
        # concrete subclasses read it and assign their own typed attributes.

    # --------------------------------------------------- typed field access
    # There is deliberately NO ``params`` dict: a node's parameters are its
    # real, constructor-declared attributes (listed in ``_FIELDS`` only for
    # serialization / keyed form access).  ``get_field`` / ``set_field`` give
    # the dynamic editors a keyed view over those attributes.
    @classmethod
    def field_names(cls) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys((*cls._FIELDS, *(field.key for field in cls.fields)))
        )

    @classmethod
    def default_parameters(cls) -> dict[str, Any]:
        return field_defaults(cls.fields)

    def _initialize_fields(self, values: dict) -> None:
        unknown = set(values) - set(self.field_names()) - {"custom_class"}
        if unknown:
            raise ValueError(
                localized_message(
                    "ui.errors.nodes.unknown_fields_for_value_value",
                    value_0=type(self).__name__,
                    value_1=sorted(unknown),
                )
            )
        if self.type_field in values and values[self.type_field] != self.type_name:
            raise ValueError(
                localized_message(
                    "ui.errors.nodes.unknown_node_type",
                    kind=self.kind,
                    type_name=values[self.type_field],
                )
            )
        for field in self.fields:
            setattr(
                self,
                field.key,
                deepcopy(values[field.key])
                if field.key in values
                else field.new_default(),
            )

    def has_field(self, key: str) -> bool:
        return key in self.field_names()

    def get_field(self, key: str, default: object = None) -> Any:
        """Read one parameter; ``default`` is returned when it is unset."""
        if key not in self.field_names():
            raise KeyError(
                localized_message(
                    "ui.errors.nodes.value_has_no_field_value",
                    value_0=type(self).__name__,
                    value_1=key,
                )
            )
        value = getattr(self, key, None)
        return default if value is None else value

    def set_field(self, key: str, value: object) -> Node:
        """Write one parameter onto its attribute (chainable)."""
        if key not in self.field_names():
            raise KeyError(
                localized_message(
                    "ui.errors.nodes.value_has_no_field_value",
                    value_0=type(self).__name__,
                    value_1=key,
                )
            )
        setattr(self, key, value)
        return self

    def field_items(self) -> Iterator[tuple[str, object]]:
        """Yield ``(key, value)`` for every set parameter.

        Unset parameters (attribute ``None``) are omitted so the on-disk
        ``*.morph`` mapping never contains stray ``null`` entries.
        """
        for key in self.field_names():
            value = getattr(self, key, None)
            if value is not None:
                yield key, value

    # ------------------------------------------------------------------ tree
    @property
    def children(self) -> tuple[Node, ...]:
        """Read-only traversal view; containers own explicitly typed collections."""
        return ()

    def add_child(self, node: Node, index: int | None = None) -> Node:
        raise TypeError(
            localized_message(
                "ui.errors.nodes.invalid_child",
                parent=type(self).__name__,
                child=type(node).__name__,
            )
        )

    def remove_child(self, node: Node) -> None:
        raise ValueError(
            localized_message(
                "ui.errors.nodes.child_not_attached",
                parent=type(self).__name__,
            )
        )

    def iter_nodes(self) -> Iterator[Node]:
        yield self
        for child in self.children:
            yield from child.iter_nodes()

    def find(self, predicate) -> Node | None:
        """Depth-first search for the first node satisfying ``predicate``."""
        for node in self.iter_nodes():
            if predicate(node):
                return node
        return None

    # ----------------------------------------------------------- persistence
    def to_dict(self) -> dict:
        """Return an independent persistence mapping for this subtree."""
        params = deepcopy(dict(self.field_items()))
        if self.custom_class:
            params["custom_class"] = self.custom_class
        return {
            "kind": self.kind,
            "name": self.name,
            "params": params,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Restore the concrete registered class, including its descendants."""
        from .registry import resolve_node_type

        params = deepcopy(data.get("params", {}))
        node_type = resolve_node_type(data["kind"], params)
        if not issubclass(node_type, cls):
            raise TypeError(
                localized_message(
                    "ui.errors.nodes.unexpected_node_type",
                    expected=cls.__name__,
                    actual=node_type.__name__,
                )
            )
        legacy_fields = {"part_name"} if issubclass(node_type, PartNode) else set()
        unknown = set(params) - set(node_type.field_names()) - {"custom_class"} - legacy_fields
        if unknown:
            raise ValueError(
                localized_message(
                    "ui.errors.nodes.unknown_fields_for_value_value",
                    value_0=node_type.__name__,
                    value_1=sorted(unknown),
                )
            )
        node = node_type(
            name=data.get("name", ""),
            params=params,
            children=[Node.from_dict(child) for child in data.get("children", ())],
        )
        node.custom_class = str(params.get("custom_class") or "")
        return cast(Self, node)

    # ---------------------------------------------------------------- misc
    def clone(self) -> Self:
        return type(self).from_dict(self.to_dict())

    def __repr__(self) -> str:
        fields = ", ".join(self.field_names()) or "—"
        return (
            f"<{type(self).__name__} kind={self.kind!r} name={self.name!r} "
            f"fields={{{fields}}} children={len(self.children)}>"
        )


# ---------------------------------------------------------------------------
# Shared typed node families
# ---------------------------------------------------------------------------


class TypedNode(Node):
    """A node whose concrete class fixes its backend type and editable fields."""

    type_field = "type"
    _FIELDS = ("type",)

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict[str, Any] | None = None,
        children: Sequence[Node] | None = None,
        **values: Any,
    ) -> None:
        data = {**(params or {}), **values}
        super().__init__(kind=kind, name=name, params=data, children=children)
        self._initialize_fields(data)

    @property
    def type(self) -> str:
        return self.type_name


class ObjectiveTermNode(TypedNode):
    kind = "objective_term"
    group: ClassVar[str] = ""
    gen: ClassVar[str] = ""


class PenaltyTermNode(TypedNode):
    kind = "penalty_term"
    group: ClassVar[str] = ""
    gen: ClassVar[str] = ""


class SurfaceConstraintNode(TypedNode):
    kind = "surface_constraint"
    factory: ClassVar[str | None] = None
    method: ClassVar[str | None] = None
    related_surface: ClassVar[bool] = False


class CADOperationNode(Node):
    """Base of an explicit TorchFEA CAD operation type."""

    kind = KIND_CAD_OPERATION
    type_field = "operation_type"
    _FIELDS = ("operation_type", "operation_id")
    operation_id: str
    operation_kind: ClassVar[str] = ""
    group: ClassVar[str] = ""
    object_id: str | None = None
    tool_id: str | None = None
    input_id: str | None = None

    @property
    def operation_type(self) -> str:
        return self.type_name

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict[str, Any] | None = None,
        children: Sequence[Node] | None = None,
        **values: Any,
    ) -> None:
        data = {**(params or {}), **values}
        super().__init__(kind=kind, name=name, params=data, children=children)
        self.operation_id = str(data.get("operation_id", name)).strip()
        self._initialize_fields(data)

    @classmethod
    def create(
        cls, operation_type: str, operation_id: str, **overrides
    ) -> CADOperationNode:
        from .registry import CAD_OPERATION_TYPES

        return CAD_OPERATION_TYPES[operation_type](
            name=operation_id,
            operation_id=operation_id,
            **overrides,
        )


class PartNode(TypedNode):
    """One Part and its ordered Instance declarations."""

    instances: list[InstanceNode]

    kind = KIND_PART
    has_surfaces: ClassVar[bool] = False
    exterior_surface: str

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict[str, Any] | None = None,
        children: Sequence[Node] | None = None,
        **values: Any,
    ) -> None:
        self.instances: list[InstanceNode] = []
        data = {**(params or {}), **values}
        # Older definitions stored a second, editable Assembly Part name.
        # Keep its physical identity on import, with a single name thereafter.
        legacy_name = str(data.pop("part_name", "") or "").strip()
        if legacy_name:
            name = legacy_name
        super().__init__(
            kind=kind, name=name, params=data, children=children
        )
        if not self.instances:
            from .node_types.structural import InstanceNode

            self.add_instance(InstanceNode(name=f"{self.assembly_name or 'part'}-1"))

    # ----------------------------------------------------------- properties
    @property
    def assembly_name(self) -> str:
        """Part name used in the assembly and generated script."""
        return self.name.strip()

    @property
    def instance_names(self) -> list[str]:
        return [instance.name for instance in self.instances]

    @property
    def children(self) -> tuple[Node, ...]:
        return tuple(self.instances)

    def add_child(self, node: Node, index: int | None = None) -> Node:
        from .node_types.structural import InstanceNode

        if not isinstance(node, InstanceNode):
            return super().add_child(node, index)
        if index is None:
            self.instances.append(node)
        else:
            self.instances.insert(index, node)
        return node

    def remove_child(self, node: Node) -> None:
        from .node_types.structural import InstanceNode

        if not isinstance(node, InstanceNode):
            return super().remove_child(node)
        self.instances.remove(node)

    def add_instance(
        self, instance: InstanceNode, index: int | None = None
    ) -> InstanceNode:
        """Attach one Instance declaration to this Part."""
        if not instance.name.strip():
            raise ValueError(
                localized_message("ui.errors.nodes.instance_name_cannot_be_empty")
            )
        if any(existing.name == instance.name for existing in self.instances):
            raise ValueError(
                localized_message(
                    "ui.errors.nodes.instance_value_already_exists",
                    value_0=instance.name,
                )
            )
        self.add_child(instance, index=index)
        return instance

    @classmethod
    def create(cls, part_type: str, name: str = "", **overrides) -> PartNode:
        from .registry import PART_TYPES

        return PART_TYPES[part_type](name=name, **overrides)


class SurfaceNode(TypedNode):
    """Base of one boundary surface type (outer or cavity)."""

    kind = KIND_SURFACE
    _FIELDS = ("type", "flip", "is_updatable")
    factory: ClassVar[str | None] = None
    flip: bool
    is_updatable: bool

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict[str, Any] | None = None,
        children: Sequence[Node] | None = None,
        **values: Any,
    ) -> None:
        data = {**(params or {}), **values}
        super().__init__(kind=kind, name=name, params=data, children=children)
        self.flip = bool(data.get("flip", False))
        self.is_updatable = bool(data.get("is_updatable", type(self).is_updatable))

    @property
    def surface_type(self) -> str:
        """Backend surface class name, e.g. ``"bsp_cylinder"``."""
        return self.type

    @property
    def is_inner(self) -> bool:
        """Whether this surface is an inner cavity (normals flipped)."""
        return self.flip

    @classmethod
    def create(
        cls, surface_type: str, index: int = 0, name: str = "", **overrides
    ) -> SurfaceNode:
        from .registry import SURFACE_TYPES

        overrides["flip"] = index > 0
        return SURFACE_TYPES[surface_type](name=name, **overrides)


class FEAComponentNode(TypedNode):
    """Shared references and amplitude metadata of loads and constraints."""

    kind = KIND_FEA_COMPONENT
    num_values: ClassVar[int] = 0
    name_hint: ClassVar[str] = "load_"

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict[str, Any] | None = None,
        children: Sequence[Node] | None = None,
        **values: Any,
    ) -> None:
        self._reference_names: dict[str, str] = {
            key: "" for key in (*INSTANCE_REFERENCE_FIELDS, *REFERENCE_POINT_FIELDS)
        }
        self.instance: InstanceNode | None = None
        self.instance1: InstanceNode | None = None
        self.instance2: InstanceNode | None = None
        self.reference_point: FEAComponentNode | None = None
        self.reference_point1: FEAComponentNode | None = None
        self.reference_point2: FEAComponentNode | None = None
        super().__init__(
            kind=kind, name=name, params=params, children=children, **values
        )

    def reference_name(self, field: str) -> str:
        """Display/serialized name of one node reference field."""
        attr = INSTANCE_REFERENCE_FIELDS.get(field) or REFERENCE_POINT_FIELDS.get(field)
        if attr is None:
            raise KeyError(
                localized_message(
                    "ui.errors.nodes.value_is_not_a_reference_field", value_0=field
                )
            )
        target = getattr(self, attr)
        return target.name if target is not None else self._reference_names[field]

    def set_reference(self, field: str, target: Node | None) -> None:
        """Bind one reference field to an in-memory target node."""
        attr = INSTANCE_REFERENCE_FIELDS.get(field) or REFERENCE_POINT_FIELDS.get(field)
        if attr is None:
            raise KeyError(
                localized_message(
                    "ui.errors.nodes.value_is_not_a_reference_field", value_0=field
                )
            )
        setattr(self, attr, target)
        self._reference_names[field] = ""

    def pending_reference_name(self, field: str) -> str:
        """Name read from persistence before the aggregate binds it."""
        return self._reference_names[field]

    def _reference_property(field: str):
        def getter(self: FEAComponentNode) -> str:
            value = self.reference_name(field)
            return value

        def setter(self: FEAComponentNode, value: object) -> None:
            self.set_reference(field, None)
            self._reference_names[field] = str(value or "").strip()

        return property(getter, setter)

    instance_name = _reference_property("instance_name")
    instance_name1 = _reference_property("instance_name1")
    instance_name2 = _reference_property("instance_name2")
    rp_name = _reference_property("rp_name")
    rp_name1 = _reference_property("rp_name1")
    rp_name2 = _reference_property("rp_name2")

    @classmethod
    def create(
        cls, component_type: str, name: str | None = None, **overrides
    ) -> FEAComponentNode:
        from .registry import LOAD_TYPES

        node_type = LOAD_TYPES[component_type]
        return node_type(
            name=name if name is not None else f"{node_type.name_hint}{component_type}",
            **overrides,
        )


class MaterialNode(TypedNode):
    """Shared Part reference of an explicit material assignment type."""

    kind = KIND_MATERIAL
    material_model: str
    density: float | str
    elementname: str

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict[str, Any] | None = None,
        children: Sequence[Node] | None = None,
        **values: Any,
    ) -> None:
        self._part_name = ""
        self.part: PartNode | None = None
        super().__init__(
            kind=kind, name=name, params=params, children=children, **values
        )

    @property
    def material_type(self) -> str:
        return self.type

    @property
    def part_name(self) -> str:
        """Physical Assembly Part name at the persistence/codegen boundary."""
        if self.part is not None:
            return self.part.assembly_name
        return self._part_name

    @part_name.setter
    def part_name(self, value: object) -> None:
        self.part = None
        self._part_name = str(value or "").strip()

    def set_part(self, part: PartNode) -> None:
        """Bind this material assignment to one geometry Part."""
        self.part = part
        self._part_name = ""

    @property
    def pending_part_name(self) -> str:
        """Part name read from persistence before the aggregate binds it."""
        return self._part_name

    @classmethod
    def create(cls, material_type: str, name: str = "", **overrides) -> MaterialNode:
        from .registry import MATERIAL_TYPES

        return MATERIAL_TYPES[material_type](name=name, **overrides)


def find_node(root: Node, kind: str, name: str | None = None) -> Node | None:
    """Find a node by kind (and optionally name)."""
    return root.find(lambda n: n.kind == kind and (name is None or n.name == name))


def list_node_paths(root: Node) -> list[str]:
    """Return human-readable paths of every node (for debugging / display)."""
    out: list[str] = []

    def walk(node: Node, prefix: str) -> None:
        label = node.name or node.kind
        path = f"{prefix}/{label}" if prefix else label
        out.append(path)
        for c in node.children:
            walk(c, path)

    walk(root, "")
    return out
