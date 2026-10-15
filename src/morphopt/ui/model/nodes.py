"""Typed definition nodes, field serialization and node-local behavior."""

from __future__ import annotations
from ..i18n import localized_message

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
#     ├── geometry   -- children: PartNode* (each owns InstanceNode*
#     │                  and optional SurfaceNode*; 0 = outer, 1.. = cavities)
#     ├── loads      -- children: FEAComponentNode* (BC / RP / forces / contacts)
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
KIND_CAD_OPERATION = "cad_operation"
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
        self.custom_class: str = str((params or {}).get("custom_class") or "")
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
            raise KeyError(localized_message("ui.errors.nodes.value_has_no_field_value", value_0=type(self).__name__, value_1=key))
        value = getattr(self, key, None)
        return default if value is None else value

    def set_field(self, key: str, value: object) -> Node:
        """Write one parameter onto its attribute (chainable)."""
        if key not in type(self)._FIELDS:
            raise KeyError(localized_message("ui.errors.nodes.value_has_no_field_value", value_0=type(self).__name__, value_1=key))
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
    def from_dict(cls, data: dict) -> Node:
        """Rebuild a node (and its whole subtree) from a ``*.morph`` dict.

        The concrete subclass is selected from the stored ``kind`` so typed
        accessors keep working after a save / load round-trip.
        """
        kind = data["kind"]
        if kind not in NODE_TYPES:
            raise ValueError(localized_message("ui.errors.nodes.unknown_model_node_kind_value", value_0=kind))
        node_type = NODE_TYPES[kind]
        params = dict(data.get("params", {}))
        unknown = set(params) - set(node_type._FIELDS) - {"custom_class"}
        if unknown:
            raise ValueError(localized_message("ui.errors.nodes.unknown_fields_for_value_value", value_0=kind, value_1=sorted(unknown)))
        node = node_type(
            kind=kind,
            name=data.get("name", ""),
            params=deepcopy(params),
            children=[cls.from_dict(c) for c in data.get("children", [])],
        )
        node.custom_class = str((data.get("params") or {}).get("custom_class") or "")
        return node

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

    Every :class:`PartNode` owns one Part plus its Instances;
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
        self, interface: PartNode, index: int | None = None
    ) -> PartNode:
        """Attach a geometry interface and return it (chainable)."""
        self.add_child(interface, index)
        return interface

    def interfaces(self) -> list[PartNode]:
        return [c for c in self.children if c.kind == KIND_PART_INTERFACE]

    def interface_count(self) -> int:
        return len(self.interfaces())

    def owner(self, surface: SurfaceNode) -> PartNode | None:
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


class CADOperationNode(Node):
    """One ordered TorchFEA CAD feature stored below a CAD Part."""

    kind = KIND_CAD_OPERATION
    _FIELDS = (
        "operation_type",
        "operation_id",
        "object_id",
        "tool_id",
        "input_id",
        "filename",
        "data",
        "x",
        "y",
        "z",
        "dx",
        "dy",
        "dz",
        "ltx",
        "radius",
        "radius1",
        "radius2",
        "major_radius",
        "minor_radius",
        "ax",
        "ay",
        "az",
        "angle",
        "sx",
        "sy",
        "sz",
        "a",
        "b",
        "c",
        "d",
    )

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict | None = None,
        children: list[Node] | None = None,
    ) -> None:
        super().__init__(kind=kind, name=name, params=params, children=children)
        data = dict(params or {})
        self.operation_type: str = str(data.get("operation_type") or "")
        self.operation_id: str = str(data.get("operation_id") or "").strip()
        self.object_id: str | None = data.get("object_id")
        self.tool_id: str | None = data.get("tool_id")
        self.input_id: str | None = data.get("input_id")
        self.filename: str | None = data.get("filename")
        self.data: str | None = data.get("data")
        self.x: float | str | None = data.get("x")
        self.y: float | str | None = data.get("y")
        self.z: float | str | None = data.get("z")
        self.dx: float | str | None = data.get("dx")
        self.dy: float | str | None = data.get("dy")
        self.dz: float | str | None = data.get("dz")
        self.ltx: float | str | None = data.get("ltx")
        self.radius: float | str | None = data.get("radius")
        self.radius1: float | str | None = data.get("radius1")
        self.radius2: float | str | None = data.get("radius2")
        self.major_radius: float | str | None = data.get("major_radius")
        self.minor_radius: float | str | None = data.get("minor_radius")
        self.ax: float | str | None = data.get("ax")
        self.ay: float | str | None = data.get("ay")
        self.az: float | str | None = data.get("az")
        self.angle: float | str | None = data.get("angle")
        self.sx: float | str | None = data.get("sx")
        self.sy: float | str | None = data.get("sy")
        self.sz: float | str | None = data.get("sz")
        self.a: float | str | None = data.get("a")
        self.b: float | str | None = data.get("b")
        self.c: float | str | None = data.get("c")
        self.d: float | str | None = data.get("d")

    @classmethod
    def create(
        cls, operation_type: str, operation_id: str, **overrides
    ) -> CADOperationNode:
        """Create an operation node with that operation's schema defaults."""
        from .schemas import CAD_OPERATION_TYPES, clone_defaults

        spec = CAD_OPERATION_TYPES.get(operation_type)
        if spec is None:
            raise ValueError(localized_message("ui.errors.nodes.unknown_cad_operation_type_value", value_0=operation_type))
        params = {"operation_type": operation_type}
        params.update(clone_defaults(spec["params"]))
        params["operation_id"] = str(operation_id).strip()
        allowed = {field["key"] for field in spec["params"]}
        unknown = set(overrides) - allowed
        if unknown:
            raise ValueError(
                localized_message("ui.errors.nodes.unknown_value_field_s_value", value_0=operation_type, value_1=sorted(unknown))
            )
        params.update(overrides)
        return cls(name=params["operation_id"], params=params)


class PartNode(Node):
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
        "exterior_surface",
        "mesh_file",
        "inp_part_name",
        "model_directory",
        "model_filename",
        "model_part_name",
        "shell_thickness",
        "length",
        "height",
        "depth",
        "mesh_size",
        "r0",
        "init_location",
        "direction",
        "num_layers",
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
        self.exterior_surface: str | None = data.get("exterior_surface")
        self.mesh_file: str | None = data.get("mesh_file")
        self.inp_part_name: str | None = data.get("inp_part_name")
        self.model_directory: str | None = data.get("model_directory")
        self.model_filename: str | None = data.get("model_filename")
        self.model_part_name: str | None = data.get("model_part_name")
        self.shell_thickness: float | None = data.get("shell_thickness")
        self.num_layers: int | None = data.get("num_layers")
        self.length: float | None = data.get("length")
        self.height: float | None = data.get("height")
        self.depth: float | None = data.get("depth")
        self.mesh_size: float | None = data.get("mesh_size")
        self.r0: float | None = data.get("r0")
        self.init_location: list | None = data.get("init_location")
        self.direction: list | None = data.get("direction")

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
        """Backend part-interface class name, e.g. ``"INPPart"``."""
        return self.type

    @property
    def spec(self) -> dict:
        from .schemas import PART_INTERFACE_TYPES

        return PART_INTERFACE_TYPES.get(self.type, {})

    @property
    def has_surfaces(self) -> bool:
        """Whether this interface type is described by boundary surfaces."""
        return bool(self.spec.get("surfaces", False))

    @property
    def is_updatable(self) -> bool:
        """Whether this Part type supplies geometry design variables."""
        return bool(self.spec.get("design", False))

    def resolved_part_name(self) -> str:
        """Part name used by generated code (falls back to the node name)."""
        return (self.part_name or self.name or "").strip()

    def resolved_instance_names(self) -> list[str]:
        """Return this Part's Instance names in registration order."""
        return [instance.name for instance in self.instances()]

    def instances(self) -> list[InstanceNode]:
        """Return the Instance children in their registration order."""
        return [child for child in self.children if child.kind == KIND_INSTANCE]

    def cad_operations(self) -> list[CADOperationNode]:
        """Return this Part's CAD feature nodes in history order."""
        return [
            child for child in self.children if isinstance(child, CADOperationNode)
        ]

    def live_cad_operations(
        self, operations: list[CADOperationNode] | None = None
    ) -> list[CADOperationNode]:
        """Return history features that still represent live OCC entities."""
        history = self.cad_operations() if operations is None else operations
        consumed_ids = {
            input_id
            for operation in history
            for input_id in (
                operation.object_id,
                operation.tool_id,
                operation.input_id,
            )
            if input_id
        }
        return [
            operation
            for operation in history
            if operation.operation_id not in consumed_ids
        ]

    def add_cad_operation(
        self, operation: CADOperationNode, index: int | None = None
    ) -> CADOperationNode:
        """Attach one ordered CAD feature to this CAD Part."""
        if self.interface_type != "CADPart":
            raise TypeError(localized_message("ui.errors.nodes.cad_operations_can_only_belong_to_a_cadpartinterface"))
        if any(
            item.operation_id == operation.operation_id
            for item in self.cad_operations()
        ):
            raise ValueError(localized_message("ui.errors.nodes.cad_operation_id_value_already_exists", value_0=operation.operation_id))
        self.add_child(operation, index=index)
        return operation

    def add_instance(
        self, instance: InstanceNode, index: int | None = None
    ) -> InstanceNode:
        """Attach one Instance declaration to this Part."""
        if not instance.name.strip():
            raise ValueError(localized_message("ui.errors.nodes.instance_name_cannot_be_empty"))
        if any(existing.name == instance.name for existing in self.instances()):
            raise ValueError(localized_message("ui.errors.nodes.instance_value_already_exists", value_0=instance.name))
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
    ) -> PartNode:
        """Build a geometry interface from schema defaults + overrides."""
        from .schemas import clone_defaults, part_interface_spec

        spec = part_interface_spec(interface_type)
        allowed = {f["key"] for f in spec["params"]}
        unknown = set(overrides) - allowed
        if unknown:
            raise ValueError(
                localized_message("ui.errors.nodes.unknown_geometry_interface_field_s_value_for_value_allowed_value", value_0=sorted(unknown), value_1=interface_type, value_2=sorted(allowed))
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
    def _vector3(value: object, label: str) -> list[float] | str:
        if isinstance(value, str):
            return value
        values = [0.0, 0.0, 0.0] if value is None else [float(item) for item in value]
        if len(values) != 3:
            raise ValueError(localized_message("ui.errors.nodes.instance_value_must_have_exactly_3_components", value_0=label))
        return values

    @property
    def pose(self) -> list[float]:
        """Return TorchFEA's six-component translation/rotation pose."""
        if isinstance(self.translation, str) or isinstance(self.rotation, str):
            raise ValueError(localized_message("ui.errors.nodes.a_helper_variable_pose_cannot_be_previewed_before_execution"))
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
                localized_message("ui.errors.nodes.unknown_surface_field_s_value_for_value_allowed_value", value_0=sorted(unknown), value_1=surface_type, value_2=sorted(allowed))
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
        self, interface: FEAComponentNode, index: int | None = None
    ) -> FEAComponentNode:
        """Attach an interface and return it (chainable)."""
        self.add_child(interface, index)
        return interface

    def interfaces(self) -> list[FEAComponentNode]:
        return [c for c in self.children if c.kind == KIND_INTERFACE]


class FEAComponentNode(Node):
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
        self.reference_point: FEAComponentNode | None = None
        self.reference_point1: FEAComponentNode | None = None
        self.reference_point2: FEAComponentNode | None = None
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
            raise KeyError(localized_message("ui.errors.nodes.value_is_not_a_reference_field", value_0=field))
        target = getattr(self, attr)
        return target.name if target is not None else self._reference_names[field]

    def set_reference(self, field: str, target: Node | None) -> None:
        """Bind one reference field to an in-memory target node."""
        attr = INSTANCE_REFERENCE_FIELDS.get(field) or REFERENCE_POINT_FIELDS.get(field)
        if attr is None:
            raise KeyError(localized_message("ui.errors.nodes.value_is_not_a_reference_field", value_0=field))
        setattr(self, attr, target)
        self._reference_names[field] = ""

    def pending_reference_name(self, field: str) -> str:
        """Name read from persistence before the aggregate binds it."""
        return self._reference_names[field]

    def _reference_property(field: str):
        def getter(self: FEAComponentNode) -> str | None:
            value = self.reference_name(field)
            return value or None

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
        cls, interface_type: str, name: str | None = None, **overrides
    ) -> FEAComponentNode:
        """Build an interface from its schema defaults, then apply overrides.

        Unknown field names raise immediately so typos never slip through.
        """
        from .schemas import clone_defaults, interface_spec

        spec = interface_spec(interface_type)
        allowed = {f["key"] for f in spec["params"]}
        unknown = set(overrides) - allowed
        if unknown:
            raise ValueError(
                localized_message("ui.errors.nodes.unknown_interface_field_s_value_for_value_allowed_value", value_0=sorted(unknown), value_1=interface_type, value_2=sorted(allowed))
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
        self.step_values: list[dict[FEAComponentNode | str, list]] = [
            dict(v) for v in (data.get("step_values") or [])
        ]

    def field_items(self) -> Iterator[tuple[str, object]]:
        """Serialize object-keyed amplitudes using the referenced load names."""
        yield "num_steps", self.num_steps
        yield "step_values", [
            {
                key.name if isinstance(key, FEAComponentNode) else str(key): value
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
        self.part: PartNode | None = None
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
        self.materialpenalty: int | None = data.get("materialpenalty")

    @property
    def material_type(self) -> str:
        return self.type

    @property
    def is_updatable(self) -> bool:
        """Whether this material interface supplies design variables."""
        from .schemas import MATERIAL_TYPES

        return bool(MATERIAL_TYPES.get(self.material_type, {}).get("design", False))

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

    def set_part(self, part: PartNode) -> None:
        """Bind this material assignment to one geometry Part interface."""
        self.part = part
        self._part_name = ""

    @property
    def pending_part_name(self) -> str:
        """Part name read from persistence before the aggregate binds it."""
        return self._part_name

    @classmethod
    def create(cls, material_type: str, name: str = "", **overrides) -> MaterialNode:
        from .schemas import clone_defaults, material_spec

        spec = material_spec(material_type)
        allowed = {f["key"] for f in spec["params"]}
        unknown = set(overrides) - allowed
        if unknown:
            raise ValueError(
                localized_message("ui.errors.nodes.unknown_material_field_s_value_for_value_allowed_value", value_0=sorted(unknown), value_1=material_type, value_2=sorted(allowed))
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
        self.jacobian_needed: list[FEAComponentNode | str] = list(
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
            item.name if isinstance(item, FEAComponentNode) else str(item)
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
        self.num_process: int | str = data.get("num_process", 1)
        self.gpus: list = list(data.get("gpus") or [])
        self.task_index_list: list = list(data.get("task_index_list") or [])


class UpdaterNode(Node):
    """Optimisation sub-updater configuration (geometry / materials section).

    Each section is a list of config dicts, one for every updated target.
    Geometry configs keep an ordered ``symmetry_constraints`` list and a
    separate penalty ``constraints`` list; materials currently keep penalty
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
        if any("code" in config for config in self.geometry + self.materials):
            raise ValueError(localized_message("ui.errors.nodes.raw_updater_code_is_unsupported_use_method_overrides"))

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


class MethodOverrideNode(Node):
    """Body of one overridden method; its signature comes from the base class."""

    kind = "method_override"
    _FIELDS = ("body",)

    def __init__(self, kind=None, name="", params=None, children=None):
        super().__init__(kind=kind, name=name, children=children)
        self.body: str = str((params or {}).get("body", ""))


class CustomClassNode(Node):
    """A module-level framework subclass, selected explicitly by model nodes."""

    kind = "custom_class"
    _FIELDS = ("base_class",)

    def __init__(self, kind=None, name="", params=None, children=None):
        super().__init__(kind=kind, name=name, children=children)
        self.base_class: str = str((params or {}).get("base_class", ""))


class HelperVariableNode(Node):
    """One named module-level value expression."""

    kind = "helper_variable"
    _FIELDS = ("value",)

    def __init__(self, kind=None, name="", params=None, children=None):
        super().__init__(kind=kind, name=name, children=children)
        self.value: str = str((params or {}).get("value", "None"))


class HelperFunctionNode(Node):
    """One named module-level function with explicit parameters and body."""

    kind = "helper_function"
    _FIELDS = ("parameters", "body")

    def __init__(self, kind=None, name="", params=None, children=None):
        super().__init__(kind=kind, name=name, children=children)
        self.parameters: str = str((params or {}).get("parameters", ""))
        self.body: str = str((params or {}).get("body", "pass"))


#: kind -> concrete node class used by :meth:`Node.from_dict`.
NODE_TYPES: dict[str, type[Node]] = {
    CustomClassNode.kind: CustomClassNode,
    MethodOverrideNode.kind: MethodOverrideNode,
    HelperVariableNode.kind: HelperVariableNode,
    HelperFunctionNode.kind: HelperFunctionNode,
    KIND_PROBLEM: ProblemNode,
    KIND_GEOMETRY: GeometryNode,
    KIND_PART_INTERFACE: PartNode,
    KIND_CAD_OPERATION: CADOperationNode,
    KIND_INSTANCE: InstanceNode,
    KIND_SURFACE: SurfaceNode,
    KIND_LOADS: LoadsNode,
    KIND_INTERFACE: FEAComponentNode,
    KIND_STEPS: StepsNode,
    KIND_MATERIALS: MaterialsNode,
    KIND_MATERIAL: MaterialNode,
    KIND_OBJECTIVE: ObjectiveNode,
    KIND_SOLVER: SolverNode,
    KIND_UPDATER: UpdaterNode,
}


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


