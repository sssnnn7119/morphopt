"""Generic node-tree data model for an optimization problem definition."""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Node kinds of the problem-definition task tree (the explicit taxonomy).
#
# A problem is a fixed, ordered set of persisted sections rooted at a
# ``ProblemNode``.  The visual model tree may group related sections (the UI
# shows ``loads`` and ``steps`` under one ``loads_group`` row), but that
# presentation node is transient and is not serialized::
#
#     problem
#     ├── geometry   -- children: PartInterfaceNode* (each owns InstanceNode*
#     │                  and optional SurfaceNode*; 0 = outer, 1.. = cavities)
#     ├── loads      -- children: InterfaceNode* (BC / RP / forces / contacts)
#     ├── steps      -- one StepsNode   (step count + per-interface amplitudes)
#     ├── materials  -- children: MaterialNode* (Part + element assignments)
#     ├── objective  -- one ObjectiveNode
#     ├── solver     -- one SolverNode
#     └── updater    -- one UpdaterNode (geometry / materials optimiser config)
#
# ``Node`` stays the generic base; the concrete subclasses below make the tree
# explicit: ``kind`` is a fixed class attribute (no ad-hoc strings) and each
# class centralises its schema-driven construction so every caller builds the
# same default node.  The ``materials`` section is persisted explicitly and
# :meth:`Node.from_dict` re-hydrates each entry into its typed subclass.
# ---------------------------------------------------------------------------

KIND_PROBLEM = "problem"
KIND_GEOMETRY = "geometry"
KIND_PART_INTERFACE = "part_interface"
KIND_INSTANCE = "instance"
KIND_SURFACE = "surface"
KIND_LOADS = "loads"
KIND_INTERFACE = "interface"
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

# A file-backed template may point at an asset shipped next to that template.
# The marker stays portable in ``*.morph`` files; UI previews and generated
# headless jobs resolve it to the installed package directory.
TEMPLATE_MODEL_DIRECTORY = "$MORPHOPT_TEMPLATE_DIR"


def resolve_model_directory(directory: str | None) -> str:
    """Resolve a template asset marker or return the user path unchanged."""
    value = str(directory or "")
    if value == TEMPLATE_MODEL_DIRECTORY:
        return str(Path(__file__).resolve().parents[1] / "templates")
    return value

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

    Parameter storage is *explicit and dict-free*: every node class declares
    its parameters as real, typed attributes directly in ``__init__`` (best
    for maintenance and editor autocomplete).  ``get_field`` / ``set_field``
    give the dynamic editors a keyed view over those attributes and
    ``field_items`` feeds the on-disk ``*.morph`` mapping — there is no
    ``params`` dict anywhere in the model.

    Parameters
    ----------
    kind:
        Machine-readable node type, e.g. ``"surface"``, ``"interface"``,
        ``"material"``.  Defaults to the subclass kind.  Every kind maps to a
        field schema in :mod:`morphopt.ui.model.schemas`.
    name:
        Display / reference name.  For load interfaces this is the name used
        in the load-step matrix and in generated FEA code (e.g. ``pressure_1``).
    params:
        Initial parameter values (declared keys -> typed attributes).
    children:
        Ordered child nodes (e.g. surfaces inside ``geometry``).
    """

    kind: str | None = None

    #: names of the parameters this node exposes as real typed attributes.
    _FIELDS: tuple[str, ...] = ()

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict | None = None,
        children: list[Node] | None = None,
    ) -> None:
        self.kind = kind or type(self).kind or ""
        self.name = name
        self.children: list[Node] = list(children or [])
        # ``params`` is only forwarded by ``Node.from_dict`` for hydration;
        # concrete subclasses read it and assign their own typed attributes.

    # --------------------------------------------------- typed field access
    # There is deliberately NO ``params`` dict: a node's parameters are its
    # real, constructor-declared attributes (listed in ``_FIELDS`` only for
    # serialization / keyed form access).  ``get_field`` / ``set_field`` give
    # the dynamic editors a keyed view over those attributes.
    def field_names(self) -> tuple[str, ...]:
        """Names of this node's parameters (real attribute names)."""
        return type(self)._FIELDS

    def has_field(self, key: str) -> bool:
        return key in type(self)._FIELDS

    def get_field(self, key: str, default: object = None) -> Any:
        """Read one parameter; ``default`` is returned when it is unset."""
        if key not in type(self)._FIELDS:
            raise KeyError(f"{type(self).__name__} has no field {key!r}")
        value = getattr(self, key, None)
        return default if value is None else value

    def set_field(self, key: str, value: object) -> Node:
        """Write one parameter onto its attribute (chainable)."""
        if key not in type(self)._FIELDS:
            raise KeyError(f"{type(self).__name__} has no field {key!r}")
        setattr(self, key, value)
        return self

    def field_items(self) -> Iterator[tuple[str, object]]:
        """Yield ``(key, value)`` for every set parameter.

        Unset parameters (attribute ``None``) are omitted so the on-disk
        ``*.morph`` mapping never contains stray ``null`` entries.
        """
        for key in type(self)._FIELDS:
            value = getattr(self, key, None)
            if value is not None:
                yield key, value

    # ------------------------------------------------------------------ tree
    def add_child(self, node: Node, index: int | None = None) -> Node:
        if index is None:
            self.children.append(node)
        else:
            self.children.insert(index, node)
        return node

    def remove_child(self, node: Node) -> None:
        self.children.remove(node)

    def child(self, kind: str) -> Node | None:
        return next((c for c in self.children if c.kind == kind), None)

    def children_of(self, kind: str) -> list[Node]:
        return [c for c in self.children if c.kind == kind]

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
        return {
            "kind": self.kind,
            "name": self.name,
            "params": deepcopy(dict(self.field_items())),
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Node:
        """Rebuild a node (and its whole subtree) from a ``*.morph`` dict.

        The concrete subclass is selected from the stored ``kind`` so typed
        accessors keep working after a save / load round-trip.
        """
        kind = data.get("kind") or cls.kind or ""
        node_type = NODE_TYPES.get(kind, Node)
        return node_type(
            kind=kind,
            name=data.get("name", ""),
            params=deepcopy(dict(data.get("params", {}) or {})),
            children=[cls.from_dict(c) for c in data.get("children", [])],
        )

    # ---------------------------------------------------------------- misc
    def clone(self) -> Node:
        return Node.from_dict(self.to_dict())

    def __repr__(self) -> str:
        fields = ", ".join(type(self)._FIELDS) or "—"
        return (
            f"<{type(self).__name__} kind={self.kind!r} name={self.name!r} "
            f"fields={{{fields}}} children={len(self.children)}>"
        )


# ---------------------------------------------------------------------------
# concrete typed nodes
# ---------------------------------------------------------------------------


class ProblemNode(Node):
    """Root of one problem-definition tree; holds the ordered sections."""

    kind = KIND_PROBLEM

    def add_section(self, node: Node, index: int | None = None) -> Node:
        """Attach a top-level section node and return it (chainable)."""
        self.add_child(node, index)
        return node

    def section(self, kind: str) -> Node | None:
        """Return the direct child section of the given kind, if present."""
        return self.child(kind)

    def sections(self) -> list[Node]:
        return list(self.children)


class GeometryNode(Node):
    """Initial-geometry section: an ordered set of geometry interfaces.

    Every :class:`PartInterfaceNode` owns one Part plus its Instances;
    parameterised interfaces additionally own their boundary surfaces as
    children (index 0 = outer boundary, 1.. = cavities).  The default
    Instance is ``<part>-1``; extra Instances are declared in the Part's
    ``define_instance`` method.

    Geometry-specific parameters belong to the child Part interfaces.  This
    node only owns and orders those interfaces.
    """

    kind = KIND_GEOMETRY
    _FIELDS = ()

    def __init__(
        self,
        kind: str | None = None,
        name: str = "Geometry",
        params: dict | None = None,
        children: list[Node] | None = None,
    ) -> None:
        super().__init__(kind=kind, name=name, children=children)

    # ----------------------------------------------------------- interfaces
    def add_interface(
        self, interface: PartInterfaceNode, index: int | None = None
    ) -> PartInterfaceNode:
        """Attach a geometry interface and return it (chainable)."""
        self.add_child(interface, index)
        return interface

    def interfaces(self) -> list[PartInterfaceNode]:
        return [c for c in self.children if c.kind == KIND_PART_INTERFACE]

    def interface_count(self) -> int:
        return len(self.interfaces())

    def owner(self, surface: SurfaceNode) -> PartInterfaceNode | None:
        """Interface holding ``surface`` (``None`` when it is detached)."""
        return next(
            (
                interface
                for interface in self.interfaces()
                if surface in interface.children
            ),
            None,
        )

    # ------------------------------------------------------------- surfaces
    def surfaces(self) -> list[SurfaceNode]:
        """All boundary surfaces of every interface, in the canonical order."""
        return [
            child for interface in self.interfaces() for child in interface.surfaces()
        ]

    def surface_count(self) -> int:
        return len(self.surfaces())


class PartInterfaceNode(Node):
    """One geometry interface: a Part and (optional) boundary surfaces.

    Instance declarations belong to the generated Part class's
    ``define_instance()`` method.
    """

    kind = KIND_PART_INTERFACE
    _FIELDS = (
        "type",
        "part_name",
        "fea_seed_size",
        "mesh_order",
        "shell_thickness",
        "num_layers",
        "exterior_surface",
        "mesh_file",
        "inp_part_name",
        "model_directory",
        "model_filename",
        "model_part_name",
    )

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict | None = None,
        children: list[Node] | None = None,
    ) -> None:
        super().__init__(kind=kind, name=name, children=children)
        data = dict(params or {})
        self.type: str = str(data.get("type") or "")
        self.part_name: str = str(data.get("part_name") or "").strip()
        self.fea_seed_size: float | None = data.get("fea_seed_size")
        self.mesh_order: int | None = data.get("mesh_order")
        self.shell_thickness: float | None = data.get("shell_thickness")
        self.num_layers: int | None = data.get("num_layers")
        self.exterior_surface: str | None = data.get("exterior_surface")
        self.mesh_file: str | None = data.get("mesh_file")
        self.inp_part_name: str | None = data.get("inp_part_name")
        self.model_directory: str | None = data.get("model_directory")
        self.model_filename: str | None = data.get("model_filename")
        self.model_part_name: str | None = data.get("model_part_name")

        # A Part always has at least its identity Instance.  Keeping this in
        # the model tree makes placement a real persisted UI value instead of
        # an implicit code-generator convention.
        if not self.instances():
            part_name = self.resolved_part_name() or "part"
            self.add_instance(
                InstanceNode(name=f"{part_name}-1")
            )

    # ----------------------------------------------------------- properties
    @property
    def interface_type(self) -> str:
        """Backend part-interface class name, e.g. ``"INPPartInterface"``."""
        return self.type

    @property
    def spec(self) -> dict:
        from .schemas import PART_INTERFACE_TYPES

        return PART_INTERFACE_TYPES.get(self.type, {})

    @property
    def has_surfaces(self) -> bool:
        """Whether this interface type is described by boundary surfaces."""
        return bool(self.spec.get("surfaces", False))

    def resolved_part_name(self) -> str:
        """Part name used by generated code (falls back to the node name)."""
        return (self.part_name or self.name or "").strip()

    def resolved_instance_names(self) -> list[str]:
        """Return this Part's Instance names in registration order."""
        return [instance.name for instance in self.instances()]

    def instances(self) -> list[InstanceNode]:
        """Return the Instance children in their registration order."""
        return [child for child in self.children if child.kind == KIND_INSTANCE]

    def add_instance(
        self, instance: InstanceNode, index: int | None = None
    ) -> InstanceNode:
        """Attach one Instance declaration to this Part."""
        if not instance.name.strip():
            raise ValueError("Instance name cannot be empty")
        if any(existing.name == instance.name for existing in self.instances()):
            raise ValueError(f"Instance {instance.name!r} already exists")
        self.add_child(instance, index=index)
        return instance

    # ------------------------------------------------------------- surfaces
    def add_surface(
        self, surface: SurfaceNode, index: int | None = None
    ) -> SurfaceNode:
        self.add_child(surface, index)
        return surface

    def surfaces(self) -> list[SurfaceNode]:
        return [c for c in self.children if c.kind == KIND_SURFACE]

    def surface_count(self) -> int:
        return len(self.surfaces())

    @classmethod
    def create(
        cls, interface_type: str, name: str = "", **overrides
    ) -> PartInterfaceNode:
        """Build a geometry interface from schema defaults + overrides."""
        from .schemas import clone_defaults, part_interface_spec

        spec = part_interface_spec(interface_type)
        allowed = {f["key"] for f in spec["params"]}
        unknown = set(overrides) - allowed
        if unknown:
            raise ValueError(
                f"Unknown geometry-interface field(s) {sorted(unknown)} for "
                f"{interface_type!r}; allowed: {sorted(allowed)}"
            )
        params = {"type": interface_type}
        params.update(clone_defaults(spec["params"]))
        params.update(overrides)
        return cls(name=name, params=params)


class InstanceNode(Node):
    """One placement of a Part in the TorchFEA Assembly.

    ``translation`` and ``rotation`` are the three translational and three
    rotational exponential-coordinate components passed to TorchFEA as one
    ``[tx, ty, tz, rx, ry, rz]`` pose.
    """

    kind = KIND_INSTANCE
    _FIELDS = ("translation", "rotation")

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict | None = None,
        children: list[Node] | None = None,
    ) -> None:
        super().__init__(kind=kind, name=name, children=children)
        data = dict(params or {})
        self.translation = self._vector3(data.get("translation"), "translation")
        self.rotation = self._vector3(data.get("rotation"), "rotation")

    @staticmethod
    def _vector3(value: object, label: str) -> list[float]:
        values = [0.0, 0.0, 0.0] if value is None else [float(item) for item in value]
        if len(values) != 3:
            raise ValueError(f"Instance {label} must have exactly 3 components")
        return values

    @property
    def pose(self) -> list[float]:
        """Return TorchFEA's six-component translation/rotation pose."""
        return [*self.translation, *self.rotation]


class SurfaceNode(Node):
    """One boundary surface of the remeshed geometry (0 = outer, 1.. = inner).

    Fields are the union of every surface type's schema keys, each declared as
    an explicit typed attribute in ``__init__``; only the keys of this
    surface's ``type`` are set (the others stay ``None`` and are not written
    to the on-disk mapping).
    """

    kind = KIND_SURFACE
    _FIELDS = (
        "type",
        "flip",
        "r0",
        "length",
        "seed_size",
        "num_U_ratio",
        "num_V_ratio",
        "degree",
        "init_location",
        "maxR",
        "maxC",
        "MaxC",
        "maxFF",
        "perturbation_L",
        "path_stl",
    )

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict | None = None,
        children: list[Node] | None = None,
    ) -> None:
        super().__init__(kind=kind, name=name, children=children)
        data = dict(params or {})
        # ---- explicit typed parameters (union of surface schema fields) --
        self.type: str = str(data.get("type") or "")
        self.flip: bool = bool(data.get("flip", False))
        self.r0: float | None = data.get("r0")
        self.length: float | None = data.get("length")
        self.seed_size: float | None = data.get("seed_size")
        self.num_U_ratio: int | None = data.get("num_U_ratio")
        self.num_V_ratio: int | None = data.get("num_V_ratio")
        self.degree: int | None = data.get("degree")
        self.init_location: list | None = data.get("init_location")
        self.maxR: float | None = data.get("maxR")
        self.maxC: float | None = data.get("maxC")
        self.MaxC: float | None = data.get("MaxC")
        self.maxFF: float | None = data.get("maxFF")
        self.perturbation_L: float | None = data.get("perturbation_L")
        self.path_stl: str | None = data.get("path_stl")

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
        """Build a surface from its schema defaults, then apply overrides.

        The inner-cavity ``flip`` flag is derived from ``index`` (0 = outer).
        Unknown field names raise immediately, so typos never slip through.
        """
        from .schemas import clone_defaults, surface_spec

        spec = surface_spec(surface_type)
        allowed = {f["key"] for f in spec["params"]}
        unknown = set(overrides) - allowed
        if unknown:
            raise ValueError(
                f"Unknown surface field(s) {sorted(unknown)} for "
                f"{surface_type!r}; allowed: {sorted(allowed)}"
            )
        params = {"type": surface_type, "flip": index > 0}
        params.update(clone_defaults(spec["params"]))
        params.update(overrides)
        params["flip"] = index > 0
        return cls(name=name, params=params)


class LoadsNode(Node):
    """Holds the load interfaces (BC / RPs / forces / moments / contacts ...)."""

    kind = KIND_LOADS

    def add_interface(
        self, interface: InterfaceNode, index: int | None = None
    ) -> InterfaceNode:
        """Attach an interface and return it (chainable)."""
        self.add_child(interface, index)
        return interface

    def interfaces(self) -> list[InterfaceNode]:
        return [c for c in self.children if c.kind == KIND_INTERFACE]


class InterfaceNode(Node):
    """One FEA load / boundary interface.

    ``name`` is the reference used by the load-step matrix and by generated
    FEA code (e.g. ``pressure_1``); ``interface_type`` is the backend class.
    Fields are the union of every interface type's schema keys, declared as
    explicit typed attributes in ``__init__``.
    """

    kind = KIND_INTERFACE
    _FIELDS = (
        "type",
        "instance_name",
        "surface_name",
        "set_nodes_name",
        "index_dof",
        "rp_name",
        "rp_location",
        "obj_name",
        "s",
        "obj_type",
        "rp_name1",
        "rp_name2",
        "instance_name1",
        "surface_name1",
        "instance_name2",
        "surface_name2",
        "penalty_threshold_h",
        "element_name",
    )

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict | None = None,
        children: list[Node] | None = None,
    ) -> None:
        super().__init__(kind=kind, name=name, children=children)
        data = dict(params or {})
        # ---- explicit typed parameters (union of interface schema fields) -
        self.type: str = str(data.get("type") or "")
        self._reference_names = {
            key: str(data.get(key) or "").strip()
            for key in (*INSTANCE_REFERENCE_FIELDS, *REFERENCE_POINT_FIELDS)
        }
        self.instance: InstanceNode | None = None
        self.instance1: InstanceNode | None = None
        self.instance2: InstanceNode | None = None
        self.reference_point: InterfaceNode | None = None
        self.reference_point1: InterfaceNode | None = None
        self.reference_point2: InterfaceNode | None = None
        self.surface_name: str | None = data.get("surface_name")
        self.set_nodes_name: str | None = data.get("set_nodes_name")
        self.index_dof: list | None = data.get("index_dof")
        self.rp_location: list | None = data.get("rp_location")
        self.obj_name: str | None = data.get("obj_name")
        self.s: int | None = data.get("s")
        self.obj_type: str | None = data.get("obj_type")
        self.surface_name1: str | None = data.get("surface_name1")
        self.surface_name2: str | None = data.get("surface_name2")
        self.penalty_threshold_h: float | None = data.get("penalty_threshold_h")
        self.element_name: str | None = data.get("element_name")

    @property
    def interface_type(self) -> str:
        return self.type

    def reference_name(self, field: str) -> str:
        """Display/serialized name of one node reference field."""
        attr = INSTANCE_REFERENCE_FIELDS.get(field) or REFERENCE_POINT_FIELDS.get(field)
        if attr is None:
            raise KeyError(f"{field!r} is not a reference field")
        target = getattr(self, attr)
        return target.name if target is not None else self._reference_names[field]

    def set_reference(self, field: str, target: Node | None) -> None:
        """Bind one reference field to an in-memory target node."""
        attr = INSTANCE_REFERENCE_FIELDS.get(field) or REFERENCE_POINT_FIELDS.get(field)
        if attr is None:
            raise KeyError(f"{field!r} is not a reference field")
        setattr(self, attr, target)
        self._reference_names[field] = ""

    def pending_reference_name(self, field: str) -> str:
        """Name read from persistence before the aggregate binds it."""
        return self._reference_names[field]

    def _reference_property(field: str):
        def getter(self: InterfaceNode) -> str | None:
            value = self.reference_name(field)
            return value or None

        def setter(self: InterfaceNode, value: object) -> None:
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
        cls, interface_type: str, name: str | None = None, **overrides
    ) -> InterfaceNode:
        """Build an interface from its schema defaults, then apply overrides.

        Unknown field names raise immediately so typos never slip through.
        """
        from .schemas import clone_defaults, interface_spec

        spec = interface_spec(interface_type)
        allowed = {f["key"] for f in spec["params"]}
        unknown = set(overrides) - allowed
        if unknown:
            raise ValueError(
                f"Unknown interface field(s) {sorted(unknown)} for "
                f"{interface_type!r}; allowed: {sorted(allowed)}"
            )
        params = {"type": interface_type}
        params.update(clone_defaults(spec["params"]))
        params.update(overrides)
        if name is None:
            name = f"{spec.get('name_hint', '')}{interface_type}"
        return cls(name=name, params=params)


class StepsNode(Node):
    """Load-step plan: total step count + per-interface amplitudes per step.

    Canonical parameters are explicit, typed attributes assigned in
    ``__init__`` (``num_steps`` and ``step_values``).
    """

    kind = KIND_STEPS
    _FIELDS = ("num_steps", "step_values")

    def __init__(
        self,
        kind: str | None = None,
        name: str = "Load steps",
        params: dict | None = None,
        children: list[Node] | None = None,
    ) -> None:
        super().__init__(kind=kind, name=name, children=children)
        data = dict(params or {})
        # ---- explicit typed parameters ----------------------------------
        self.num_steps: int = int(data["num_steps"]) if "num_steps" in data else 1
        self.step_values: list[dict[InterfaceNode | str, list]] = [
            dict(v) for v in (data.get("step_values") or [])
        ]

    def field_items(self) -> Iterator[tuple[str, object]]:
        """Serialize object-keyed amplitudes using the referenced load names."""
        yield "num_steps", self.num_steps
        yield "step_values", [
            {
                key.name if isinstance(key, InterfaceNode) else str(key): value
                for key, value in step.items()
            }
            for step in self.step_values
        ]


class MaterialsNode(Node):
    """Container for the ordered material-assignment interfaces."""

    kind = KIND_MATERIALS

    def add_material(
        self, material: MaterialNode, index: int | None = None
    ) -> MaterialNode:
        self.add_child(material, index=index)
        return material

    def materials(self) -> list[MaterialNode]:
        return [child for child in self.children if child.kind == KIND_MATERIAL]


class MaterialNode(Node):
    """One material interface (the selected type supplies its parameters)."""

    kind = KIND_MATERIAL
    _FIELDS = (
        "type",
        "part_name",
        "material_model",
        "E",
        "nu",
        "mu",
        "kappa",
        "c10",
        "c01",
        "c1",
        "c2",
        "c3",
        "Jm",
        "N",
        "alpha",
        "density",
        "elementname",
        "mumax",
        "kappamax",
        "simp_ratio_min",
        "bounding_box",
        "simp_field_resolution",
        "degree",
        "initial_ratio",
        "voidpenalfactor",
        "materialpenalty",
    )

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict | None = None,
        children: list[Node] | None = None,
    ) -> None:
        super().__init__(kind=kind, name=name, children=children)
        data = dict(params or {})
        # ---- explicit typed parameters (union of material schema fields) --
        self.type: str = str(data.get("type") or "")
        self._part_name = str(data.get("part_name") or "").strip()
        self.part: PartInterfaceNode | None = None
        if not self._part_name:
            raise ValueError("MaterialNode.part_name cannot be empty.")
        self.material_model: str = str(data.get("material_model") or "NeoHookeanLnJ")
        self.E: float | None = data.get("E")
        self.nu: float | None = data.get("nu")
        self.mu: float | None = data.get("mu")
        self.kappa: float | None = data.get("kappa")
        self.c10: float | None = data.get("c10")
        self.c01: float | None = data.get("c01")
        self.c1: float | None = data.get("c1")
        self.c2: float | None = data.get("c2")
        self.c3: float | None = data.get("c3")
        self.Jm: float | None = data.get("Jm")
        self.N: float | None = data.get("N")
        self.alpha: list | None = data.get("alpha")
        self.density: float | None = data.get("density")
        self.elementname: str | None = data.get("elementname")
        self.mumax: float | None = data.get("mumax")
        self.kappamax: float | None = data.get("kappamax")
        self.simp_ratio_min: float | None = data.get("simp_ratio_min")
        self.bounding_box: list | None = data.get("bounding_box")
        self.simp_field_resolution: float | None = data.get("simp_field_resolution")
        self.degree: int | None = data.get("degree")
        self.initial_ratio: float | None = data.get("initial_ratio")
        self.voidpenalfactor: float | None = data.get("voidpenalfactor")
        self.materialpenalty: float | None = data.get("materialpenalty")

    @property
    def material_type(self) -> str:
        return self.type

    @property
    def part_name(self) -> str:
        """Physical Assembly Part name at the persistence/codegen boundary."""
        if self.part is not None:
            return self.part.resolved_part_name()
        return self._part_name

    @part_name.setter
    def part_name(self, value: object) -> None:
        self.part = None
        self._part_name = str(value or "").strip()

    def set_part(self, part: PartInterfaceNode) -> None:
        """Bind this material assignment to one geometry Part interface."""
        self.part = part
        self._part_name = ""

    @property
    def pending_part_name(self) -> str:
        """Part name read from persistence before the aggregate binds it."""
        return self._part_name

    def set_field(self, key: str, value: object) -> Node:
        if key == "part_name" and not str(value or "").strip():
            raise ValueError("MaterialNode.part_name cannot be empty.")
        return super().set_field(key, value)

    @classmethod
    def create(cls, material_type: str, name: str = "", **overrides) -> MaterialNode:
        from .schemas import clone_defaults, material_spec

        spec = material_spec(material_type)
        allowed = {f["key"] for f in spec["params"]}
        unknown = set(overrides) - allowed
        if unknown:
            raise ValueError(
                f"Unknown material field(s) {sorted(unknown)} for "
                f"{material_type!r}; allowed: {sorted(allowed)}"
            )
        params = {"type": material_type}
        params.update(clone_defaults(spec["params"]))
        params.update(overrides)
        return cls(name=name, params=params)


class ObjectiveNode(Node):
    """Objective function: body code slots + requested load Jacobian names.

    The code-slot bodies are stored as explicit (private) attributes
    ``_objective_function`` / ``_get_metrics`` and exposed through the public
    ``objective_body`` / ``metrics_body`` properties.
    """

    kind = KIND_OBJECTIVE
    _FIELDS = ("jacobian_needed", "_objective_function", "_get_metrics")

    def __init__(
        self,
        kind: str | None = None,
        name: str = "Objective Function",
        params: dict | None = None,
        children: list[Node] | None = None,
    ) -> None:
        super().__init__(kind=kind, name=name, children=children)
        data = dict(params or {})
        # ---- explicit typed parameters ----------------------------------
        self.jacobian_needed: list[InterfaceNode | str] = list(
            data.get("jacobian_needed") or []
        )
        self._objective_function: str | None = data.get("_objective_function")
        self._get_metrics: str | None = data.get("_get_metrics")

    @property
    def objective_body(self) -> str:
        return self._objective_function or ""

    @objective_body.setter
    def objective_body(self, body: str) -> None:
        self._objective_function = str(body or "")

    @property
    def metrics_body(self) -> str:
        return self._get_metrics or ""

    @metrics_body.setter
    def metrics_body(self, body: str) -> None:
        self._get_metrics = str(body or "")

    def field_items(self) -> Iterator[tuple[str, object]]:
        """Serialize Jacobian load-object references as their names."""
        yield "jacobian_needed", [
            item.name if isinstance(item, InterfaceNode) else str(item)
            for item in self.jacobian_needed
        ]
        if self._objective_function is not None:
            yield "_objective_function", self._objective_function
        if self._get_metrics is not None:
            yield "_get_metrics", self._get_metrics


class SolverNode(Node):
    """FEA solver settings (process count, gpu devices, task partitioning).

    Canonical parameters are explicit, typed attributes assigned in
    ``__init__``.
    """

    kind = KIND_SOLVER
    _FIELDS = ("num_process", "gpus", "task_index_list")

    def __init__(
        self,
        kind: str | None = None,
        name: str = "Solver",
        params: dict | None = None,
        children: list[Node] | None = None,
    ) -> None:
        super().__init__(kind=kind, name=name, children=children)
        data = dict(params or {})
        # ---- explicit typed parameters ----------------------------------
        self.num_process: int = int(data["num_process"]) if "num_process" in data else 1
        self.gpus: list = list(data.get("gpus") or [])
        self.task_index_list: list = list(data.get("task_index_list") or [])


class UpdaterNode(Node):
    """Optimisation sub-updater configuration (geometry / materials section).

    Each section is a list of config dicts, one for every updated target.
    Geometry configs keep one ``equality_constraints`` item and a separate
    ``constraints`` list, while materials currently keep penalty
    ``constraints``.
    """

    kind = KIND_UPDATER
    _FIELDS = ("geometry", "materials")

    def __init__(
        self,
        kind: str | None = None,
        name: str = "Updater",
        params: dict | None = None,
        children: list[Node] | None = None,
    ) -> None:
        super().__init__(kind=kind, name=name, children=children)
        data = dict(params or {})
        self.geometry: list[dict] = list(data.get("geometry") or [])
        self.materials: list[dict] = list(data.get("materials") or [])

    def field_items(self) -> Iterator[tuple[str, object]]:
        """Serialize object targets without retaining name references in memory."""
        yield "geometry", [self._serialize_config(config, "part_name") for config in self.geometry]
        yield "materials", [
            self._serialize_config(config, "interface_name")
            for config in self.materials
        ]

    @staticmethod
    def _serialize_config(config: dict, name_key: str) -> dict:
        target = config.get("target")
        data = {key: value for key, value in config.items() if key != "target"}
        if isinstance(target, Node):
            data[name_key] = target.name
        elif name_key not in data:
            data[name_key] = ""
        return data

    def add_geometry_config(self, config: dict | None = None) -> dict:
        """Append one geometry sub-updater config and return it."""
        from .schemas import geometry_updater_config

        config = config if config is not None else geometry_updater_config()
        self.geometry.append(config)
        return config

    def add_materials_config(self, config: dict | None = None) -> dict:
        """Append one material sub-updater config and return it."""
        from .schemas import materials_updater_config

        config = config if config is not None else materials_updater_config()
        self.materials.append(config)
        return config


#: kind -> concrete node class used by :meth:`Node.from_dict`.
NODE_TYPES: dict[str, type[Node]] = {
    KIND_PROBLEM: ProblemNode,
    KIND_GEOMETRY: GeometryNode,
    KIND_PART_INTERFACE: PartInterfaceNode,
    KIND_INSTANCE: InstanceNode,
    KIND_SURFACE: SurfaceNode,
    KIND_LOADS: LoadsNode,
    KIND_INTERFACE: InterfaceNode,
    KIND_STEPS: StepsNode,
    KIND_MATERIALS: MaterialsNode,
    KIND_MATERIAL: MaterialNode,
    KIND_OBJECTIVE: ObjectiveNode,
    KIND_SOLVER: SolverNode,
    KIND_UPDATER: UpdaterNode,
}


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

    def material_nodes(self) -> list[MaterialNode]:
        """Material assignments in their canonical tree order."""
        section = self.materials
        return section.materials() if section is not None else []

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
        (``<part>-1``, or its legacy ``<part>`` spelling) follows this change;
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
            next(
                (instance for instance in interface.instances() if instance.name == part_name),
                None,
            ),
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
    def _square_matrix(value: object) -> list[list[float]] | None:
        if not isinstance(value, (list, tuple)) or not value:
            return None
        rows: list[list[float]] = []
        for row in value:
            if isinstance(row, (list, tuple)):
                rows.append([float(item) for item in row])
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
    def _resize_matrix(matrix: list[list[float]], size: int) -> list[list[float]]:
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
            "version": 1,
            "scheme": self.scheme,
            "label": self.label,
            "result_folder": self.result_folder,
            "device": self.device,
            "updater_device": self.updater_device,
            "restart_per_iteration": self.restart_per_iteration,
            "root": self.root.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> ProblemDefinition:
        root = Node.from_dict(data.get("root", {"kind": "problem"}))
        problem = cls(
            scheme=data.get("scheme", "shapeopt"),
            label=data.get("label", "Untitled"),
            result_folder=data.get("result_folder", ".results/"),
            device=data.get("device", "cpu"),
            updater_device=data.get("updater_device"),
            restart_per_iteration=data.get("restart_per_iteration", 10),
            root=root,
        )
        problem.resolve_references()
        return problem


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
