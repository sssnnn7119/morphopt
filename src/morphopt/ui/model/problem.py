"""Generic node-tree data model for an optimization problem definition."""

from __future__ import annotations

from typing import Any, Iterable, Iterator, Optional

# ---------------------------------------------------------------------------
# Node kinds of the problem-definition task tree (the explicit taxonomy).
#
# A problem is a fixed, ordered set of persisted sections rooted at a
# ``ProblemNode``.  The visual model tree may group related sections (the UI
# shows ``loads`` and ``steps`` under one ``loads_group`` row), but that
# presentation node is transient and is not serialized::
#
#     problem
#     ├── geometry   -- children: SurfaceNode*  (index 0 = outer, 1.. = cavities)
#     ├── loads      -- children: InterfaceNode* (BC / RP / forces / contacts)
#     ├── steps      -- one StepsNode   (step count + per-interface amplitudes)
#     ├── material   -- one MaterialNode
#     ├── objective  -- one ObjectiveNode
#     ├── solver     -- one SolverNode
#     └── updater    -- one UpdaterNode (geometry / materials optimiser config)
#
# ``Node`` stays the generic base; the concrete subclasses below make the tree
# explicit: ``kind`` is a fixed class attribute (no ad-hoc strings) and each
# class centralises its schema-driven construction so every caller builds the
# same default node.  The on-disk ``*.morph`` layout is unchanged and
# :meth:`Node.from_dict` re-hydrates each entry into its typed subclass.
# ---------------------------------------------------------------------------

KIND_PROBLEM = "problem"
KIND_GEOMETRY = "geometry"
KIND_SURFACE = "surface"
KIND_LOADS = "loads"
KIND_INTERFACE = "interface"
KIND_STEPS = "steps"
KIND_MATERIAL = "material"
KIND_OBJECTIVE = "objective"
KIND_SOLVER = "solver"
KIND_UPDATER = "updater"

#: canonical order of the top-level sections inside a problem tree.
SECTION_ORDER = (KIND_GEOMETRY, KIND_LOADS, KIND_STEPS, KIND_MATERIAL,
                 KIND_OBJECTIVE, KIND_SOLVER, KIND_UPDATER)


class Node:
    """A node in the problem-definition tree (generic base).

    Subclasses pin :attr:`kind` to a fixed value; a bare ``Node`` still
    accepts any ``kind`` so legacy / fallback uses keep working.

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

    kind: Optional[str] = None

    #: names of the parameters this node exposes as real typed attributes.
    _FIELDS: tuple[str, ...] = ()

    def __init__(self, kind: Optional[str] = None, name: str = "",
                 params: Optional[dict] = None,
                 children: Optional[list["Node"]] = None) -> None:
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

    def get_field(self, key: str, default: Any = None) -> Any:
        """Read one parameter; ``default`` is returned when it is unset."""
        if key not in type(self)._FIELDS:
            raise KeyError(f"{type(self).__name__} has no field {key!r}")
        value = getattr(self, key, None)
        return default if value is None else value

    def set_field(self, key: str, value: Any) -> "Node":
        """Write one parameter onto its attribute (chainable)."""
        if key not in type(self)._FIELDS:
            raise KeyError(f"{type(self).__name__} has no field {key!r}")
        setattr(self, key, value)
        return self

    def field_items(self) -> Iterator[tuple[str, Any]]:
        """Yield ``(key, value)`` for every set parameter.

        Unset parameters (attribute ``None``) are omitted so the on-disk
        ``*.morph`` mapping never contains stray ``null`` entries.
        """
        for key in type(self)._FIELDS:
            value = getattr(self, key, None)
            if value is not None:
                yield key, value

    # ------------------------------------------------------------------ tree
    def add_child(self, node: "Node", index: Optional[int] = None) -> "Node":
        if index is None:
            self.children.append(node)
        else:
            self.children.insert(index, node)
        return node

    def remove_child(self, node: "Node") -> None:
        self.children.remove(node)

    def child(self, kind: str) -> Optional["Node"]:
        return next((c for c in self.children if c.kind == kind), None)

    def children_of(self, kind: str) -> list["Node"]:
        return [c for c in self.children if c.kind == kind]

    def iter_nodes(self) -> Iterator["Node"]:
        yield self
        for child in self.children:
            yield from child.iter_nodes()

    def find(self, predicate) -> Optional["Node"]:
        """Depth-first search for the first node satisfying ``predicate``."""
        for node in self.iter_nodes():
            if predicate(node):
                return node
        return None

    # ----------------------------------------------------------- persistence
    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "name": self.name,
            "params": dict(self.field_items()),
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Node":
        """Rebuild a node (and its whole subtree) from a ``*.morph`` dict.

        The concrete subclass is selected from the stored ``kind`` so typed
        accessors keep working after a save / load round-trip.
        """
        kind = data.get("kind") or cls.kind or ""
        node_type = NODE_TYPES.get(kind, Node)
        return node_type(
            kind=kind,
            name=data.get("name", ""),
            params=dict(data.get("params", {}) or {}),
            children=[cls.from_dict(c) for c in data.get("children", [])],
        )

    # ---------------------------------------------------------------- misc
    def clone(self) -> "Node":
        return Node.from_dict(self.to_dict())

    def __repr__(self) -> str:
        fields = ", ".join(type(self)._FIELDS) or "—"
        return (f"<{type(self).__name__} kind={self.kind!r} name={self.name!r} "
                f"fields={{{fields}}} children={len(self.children)}>")


# ---------------------------------------------------------------------------
# concrete typed nodes
# ---------------------------------------------------------------------------

class ProblemNode(Node):
    """Root of one problem-definition tree; holds the ordered sections."""

    kind = KIND_PROBLEM

    def add_section(self, node: Node, index: Optional[int] = None) -> Node:
        """Attach a top-level section node and return it (chainable)."""
        self.add_child(node, index)
        return node

    def section(self, kind: str) -> Optional[Node]:
        """Return the direct child section of the given kind, if present."""
        return self.child(kind)

    def sections(self) -> list[Node]:
        return list(self.children)


class GeometryNode(Node):
    """Initial-geometry definition for every optimization scheme.

    Canonical parameters are explicit, typed attributes assigned in
    ``__init__``; their names match the legacy ``params`` / ``*.morph`` keys.
    SIMP links to one model exported by TorchFEA; shape optimization continues
    to store its ordered boundary surfaces as child nodes.
    """

    kind = KIND_GEOMETRY
    _FIELDS = ("fea_seed_size", "mesh_order", "reinitialize_per_iter",
               "thickness", "num_layers",
               "model_directory", "model_filename",
               "_apply_surface_constraints")

    def __init__(self, kind: Optional[str] = None, name: str = "Geometry",
                 params: Optional[dict] = None,
                 children: Optional[list["Node"]] = None) -> None:
        super().__init__(kind=kind, name=name, children=children)
        data = dict(params or {})
        # ---- explicit typed parameters ----------------------------------
        self.fea_seed_size: Optional[float] = data.get("fea_seed_size")
        self.mesh_order: Optional[int] = data.get("mesh_order")
        self.reinitialize_per_iter: Optional[int] = data.get("reinitialize_per_iter")
        self.thickness: Optional[float] = data.get("thickness")
        self.num_layers: Optional[int] = data.get("num_layers")
        self.model_directory: str = str(data.get("model_directory") or "")
        self.model_filename: str = str(data.get("model_filename") or "")
        # Legacy storage for symmetry/equality code.  New definitions store
        # this body in the updater's equality-constraint item (MirrorSymmetry
        # by default).
        self._apply_surface_constraints: str = str(
            data.get("_apply_surface_constraints") or "")

    @property
    def apply_surface_constraints(self) -> str:
        """Legacy geometry BC slot kept for loading old definitions."""
        return self._apply_surface_constraints

    @apply_surface_constraints.setter
    def apply_surface_constraints(self, code: str) -> None:
        self._apply_surface_constraints = str(code or "")

    def add_surface(self, surface: "SurfaceNode",
                    index: Optional[int] = None) -> "SurfaceNode":
        """Attach a surface and return it (chainable)."""
        self.add_child(surface, index)
        return surface

    def surfaces(self) -> list["SurfaceNode"]:
        return [c for c in self.children if c.kind == KIND_SURFACE]

    def surface_count(self) -> int:
        return len(self.surfaces())

    def index_of_surface(self, surface: "SurfaceNode") -> int:
        return self.children.index(surface)


class SurfaceNode(Node):
    """One boundary surface of the remeshed geometry (0 = outer, 1.. = inner).

    Fields are the union of every surface type's schema keys, each declared as
    an explicit typed attribute in ``__init__``; only the keys of this
    surface's ``type`` are set (the others stay ``None`` and are not written
    to the on-disk mapping).
    """

    kind = KIND_SURFACE
    _FIELDS = ("type", "flip", "r0", "length", "seed_size", "num_U_ratio",
               "num_V_ratio", "degree", "init_location", "maxR", "maxC",
               "MaxC", "maxFF", "perturbation_L", "path_stl")

    def __init__(self, kind: Optional[str] = None, name: str = "",
                 params: Optional[dict] = None,
                 children: Optional[list["Node"]] = None) -> None:
        super().__init__(kind=kind, name=name, children=children)
        data = dict(params or {})
        # ---- explicit typed parameters (union of surface schema fields) --
        self.type: str = str(data.get("type") or "")
        self.flip: bool = bool(data.get("flip", False))
        self.r0: Optional[float] = data.get("r0")
        self.length: Optional[float] = data.get("length")
        self.seed_size: Optional[float] = data.get("seed_size")
        self.num_U_ratio: Optional[int] = data.get("num_U_ratio")
        self.num_V_ratio: Optional[int] = data.get("num_V_ratio")
        self.degree: Optional[int] = data.get("degree")
        self.init_location: Optional[list] = data.get("init_location")
        self.maxR: Optional[float] = data.get("maxR")
        self.maxC: Optional[float] = data.get("maxC")
        self.MaxC: Optional[float] = data.get("MaxC")
        self.maxFF: Optional[float] = data.get("maxFF")
        self.perturbation_L: Optional[float] = data.get("perturbation_L")
        self.path_stl: Optional[str] = data.get("path_stl")

    @property
    def surface_type(self) -> str:
        """Backend surface class name, e.g. ``"bsp_cylinder"``."""
        return self.type

    @property
    def is_inner(self) -> bool:
        """Whether this surface is an inner cavity (normals flipped)."""
        return self.flip

    @classmethod
    def create(cls, surface_type: str, index: int = 0, name: str = "",
               **overrides) -> "SurfaceNode":
        """Build a surface from its schema defaults, then apply overrides.

        The inner-cavity ``flip`` flag is derived from ``index`` (0 = outer).
        Unknown field names raise immediately, so typos never slip through.
        """
        from .schemas import surface_spec, clone_defaults
        spec = surface_spec(surface_type)
        allowed = {f["key"] for f in spec["params"]}
        unknown = set(overrides) - allowed
        if unknown:
            raise ValueError(
                f"Unknown surface field(s) {sorted(unknown)} for "
                f"{surface_type!r}; allowed: {sorted(allowed)}")
        params = {"type": surface_type, "flip": index > 0}
        params.update(clone_defaults(spec["params"]))
        params.update(overrides)
        params["flip"] = index > 0
        return cls(name=name, params=params)


class LoadsNode(Node):
    """Holds the load interfaces (BC / RPs / forces / moments / contacts ...)."""

    kind = KIND_LOADS

    def add_interface(self, interface: "InterfaceNode",
                      index: Optional[int] = None) -> "InterfaceNode":
        """Attach an interface and return it (chainable)."""
        self.add_child(interface, index)
        return interface

    def interfaces(self) -> list["InterfaceNode"]:
        return [c for c in self.children if c.kind == KIND_INTERFACE]


class InterfaceNode(Node):
    """One FEA load / boundary interface.

    ``name`` is the reference used by the load-step matrix and by generated
    FEA code (e.g. ``pressure_1``); ``interface_type`` is the backend class.
    Fields are the union of every interface type's schema keys, declared as
    explicit typed attributes in ``__init__``.
    """

    kind = KIND_INTERFACE
    _FIELDS = ("type", "instance_name", "surface_name", "set_nodes_name",
               "index_dof", "rp_name", "rp_location", "obj_name", "s",
               "obj_type", "rp_name1", "rp_name2", "instance_name1",
               "surface_name1", "instance_name2", "surface_name2",
               "penalty_threshold_h", "element_name")

    def __init__(self, kind: Optional[str] = None, name: str = "",
                 params: Optional[dict] = None,
                 children: Optional[list["Node"]] = None) -> None:
        super().__init__(kind=kind, name=name, children=children)
        data = dict(params or {})
        # ---- explicit typed parameters (union of interface schema fields) -
        self.type: str = str(data.get("type") or "")
        self.instance_name: Optional[str] = data.get("instance_name")
        self.surface_name: Optional[str] = data.get("surface_name")
        self.set_nodes_name: Optional[str] = data.get("set_nodes_name")
        self.index_dof: Optional[list] = data.get("index_dof")
        self.rp_name: Optional[str] = data.get("rp_name")
        self.rp_location: Optional[list] = data.get("rp_location")
        self.obj_name: Optional[str] = data.get("obj_name")
        self.s: Optional[int] = data.get("s")
        self.obj_type: Optional[str] = data.get("obj_type")
        self.rp_name1: Optional[str] = data.get("rp_name1")
        self.rp_name2: Optional[str] = data.get("rp_name2")
        self.instance_name1: Optional[str] = data.get("instance_name1")
        self.surface_name1: Optional[str] = data.get("surface_name1")
        self.instance_name2: Optional[str] = data.get("instance_name2")
        self.surface_name2: Optional[str] = data.get("surface_name2")
        self.penalty_threshold_h: Optional[float] = data.get("penalty_threshold_h")
        self.element_name: Optional[str] = data.get("element_name")

    @property
    def interface_type(self) -> str:
        return self.type

    @classmethod
    def create(cls, interface_type: str, name: Optional[str] = None,
               **overrides) -> "InterfaceNode":
        """Build an interface from its schema defaults, then apply overrides.

        Unknown field names raise immediately so typos never slip through.
        """
        from .schemas import interface_spec, clone_defaults
        spec = interface_spec(interface_type)
        allowed = {f["key"] for f in spec["params"]}
        unknown = set(overrides) - allowed
        if unknown:
            raise ValueError(
                f"Unknown interface field(s) {sorted(unknown)} for "
                f"{interface_type!r}; allowed: {sorted(allowed)}")
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

    def __init__(self, kind: Optional[str] = None, name: str = "Load steps",
                 params: Optional[dict] = None,
                 children: Optional[list["Node"]] = None) -> None:
        super().__init__(kind=kind, name=name, children=children)
        data = dict(params or {})
        # ---- explicit typed parameters ----------------------------------
        self.num_steps: int = int(data["num_steps"]) if "num_steps" in data else 1
        self.step_values: list[dict] = [dict(v) for v in (data.get("step_values") or [])]


class MaterialNode(Node):
    """One material (scheme chooses the concrete material type).

    Fields are the union of every material type's schema keys plus the
    ``_map_bsp_designfield`` code slot, declared as explicit typed attributes
    in ``__init__``.
    """

    kind = KIND_MATERIAL
    _FIELDS = ("type", "part_name", "mu", "kappa", "density", "elementname", "mumax",
               "kappamax", "simp_ratio_min", "bounding_box",
               "simp_field_resolution", "degree", "initial_ratio",
               "voidpenalfactor", "materialpenalty", "shell_mu",
               "shell_kappa", "shell_density", "shell_elementname",
               "_map_bsp_designfield")

    def __init__(self, kind: Optional[str] = None, name: str = "",
                 params: Optional[dict] = None,
                 children: Optional[list["Node"]] = None) -> None:
        super().__init__(kind=kind, name=name, children=children)
        data = dict(params or {})
        # ---- explicit typed parameters (union of material schema fields) --
        self.type: str = str(data.get("type") or "")
        self.part_name: str = str(data.get("part_name") or "")
        self.mu: Optional[float] = data.get("mu")
        self.kappa: Optional[float] = data.get("kappa")
        self.density: Optional[float] = data.get("density")
        self.elementname: Optional[str] = data.get("elementname")
        self.mumax: Optional[float] = data.get("mumax")
        self.kappamax: Optional[float] = data.get("kappamax")
        self.simp_ratio_min: Optional[float] = data.get("simp_ratio_min")
        self.bounding_box: Optional[list] = data.get("bounding_box")
        self.simp_field_resolution: Optional[float] = data.get("simp_field_resolution")
        self.degree: Optional[int] = data.get("degree")
        self.initial_ratio: Optional[float] = data.get("initial_ratio")
        self.voidpenalfactor: Optional[float] = data.get("voidpenalfactor")
        self.materialpenalty: Optional[float] = data.get("materialpenalty")
        self.shell_mu: Optional[float] = data.get("shell_mu")
        self.shell_kappa: Optional[float] = data.get("shell_kappa")
        self.shell_density: Optional[float] = data.get("shell_density")
        self.shell_elementname: Optional[str] = data.get("shell_elementname")
        self._map_bsp_designfield: str = str(data.get("_map_bsp_designfield") or "")

    @property
    def material_type(self) -> str:
        return self.type

    @property
    def map_designfield(self) -> str:
        """Material code slot (stored under ``_map_bsp_designfield``)."""
        return self._map_bsp_designfield

    @map_designfield.setter
    def map_designfield(self, code: str) -> None:
        self._map_bsp_designfield = str(code or "")

    @classmethod
    def create(cls, material_type: str, name: str = "",
               **overrides) -> "MaterialNode":
        from .schemas import material_spec, clone_defaults
        spec = material_spec(material_type)
        allowed = {f["key"] for f in spec["params"]}
        unknown = set(overrides) - allowed
        if unknown:
            raise ValueError(
                f"Unknown material field(s) {sorted(unknown)} for "
                f"{material_type!r}; allowed: {sorted(allowed)}")
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

    def __init__(self, kind: Optional[str] = None,
                 name: str = "Objective Function",
                 params: Optional[dict] = None,
                 children: Optional[list["Node"]] = None) -> None:
        super().__init__(kind=kind, name=name, children=children)
        data = dict(params or {})
        # ---- explicit typed parameters ----------------------------------
        self.jacobian_needed: list[str] = list(data.get("jacobian_needed") or [])
        self._objective_function: Optional[str] = data.get("_objective_function")
        self._get_metrics: Optional[str] = data.get("_get_metrics")

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


class SolverNode(Node):
    """FEA solver settings (process count, gpu devices, task partitioning).

    Canonical parameters are explicit, typed attributes assigned in
    ``__init__``.
    """

    kind = KIND_SOLVER
    _FIELDS = ("num_process", "gpus", "task_index_list")

    def __init__(self, kind: Optional[str] = None, name: str = "Solver",
                 params: Optional[dict] = None,
                 children: Optional[list["Node"]] = None) -> None:
        super().__init__(kind=kind, name=name, children=children)
        data = dict(params or {})
        # ---- explicit typed parameters ----------------------------------
        self.num_process: int = int(data["num_process"]) if "num_process" in data else 1
        self.gpus: list = list(data.get("gpus") or [])
        self.task_index_list: list = list(data.get("task_index_list") or [])


class UpdaterNode(Node):
    """Optimisation sub-updater configuration (geometry / materials section).

    Each section is a config dict (or ``None`` when that sub-optimiser is not
    active); geometry configs keep one ``equality_constraints`` item and a
    separate ``constraints`` list, while materials currently keep penalty
    ``constraints``.  It is stored as the explicit ``geometry`` /
    ``materials`` attributes declared in ``__init__``.
    """

    kind = KIND_UPDATER
    _FIELDS = ("geometry", "materials")

    def __init__(self, kind: Optional[str] = None, name: str = "Updater",
                 params: Optional[dict] = None,
                 children: Optional[list["Node"]] = None) -> None:
        super().__init__(kind=kind, name=name, children=children)
        data = dict(params or {})
        # ---- explicit typed parameters ----------------------------------
        self.geometry: Optional[dict] = data.get("geometry")
        self.materials: Optional[dict] = data.get("materials")

    def geometry_config(self) -> Optional[dict]:
        """Config dict of the geometry sub-updater (None when inactive)."""
        return self.geometry if isinstance(self.geometry, dict) else None

    def set_geometry_config(self, config: Optional[dict]) -> None:
        self.geometry = config

    def materials_config(self) -> Optional[dict]:
        """Config dict of the material sub-updater (None when inactive)."""
        return self.materials if isinstance(self.materials, dict) else None

    def set_materials_config(self, config: Optional[dict]) -> None:
        self.materials = config


#: kind -> concrete node class used by :meth:`Node.from_dict`.
NODE_TYPES: dict[str, type[Node]] = {
    KIND_PROBLEM: ProblemNode,
    KIND_GEOMETRY: GeometryNode,
    KIND_SURFACE: SurfaceNode,
    KIND_LOADS: LoadsNode,
    KIND_INTERFACE: InterfaceNode,
    KIND_STEPS: StepsNode,
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

    SCHEMES = ("simp", "shapeopt", "codesign")

    def __init__(
        self,
        scheme: str = "shapeopt",
        label: str = "Untitled",
        result_folder: str = ".results/",
        device: str = "cpu",
        updater_device: Optional[str] = None,
        restart_per_iteration: int = 10,
        root: Optional[Node] = None,
    ) -> None:
        if scheme not in self.SCHEMES:
            raise ValueError(f"Unknown scheme {scheme!r}; expected one of {self.SCHEMES}")
        self.scheme = scheme
        self.label = label
        self.result_folder = result_folder
        self.device = device
        # device for the Updater only; None -> follow ``device``
        self.updater_device = updater_device
        self.restart_per_iteration = restart_per_iteration
        self.root = root if root is not None else ProblemNode(name=label)

    # ------------------------------------------------------------ accessors
    def node(self, kind: str) -> Optional[Node]:
        """First node anywhere in the tree with the given kind."""
        return self.root.find(lambda n: n.kind == kind)

    def nodes(self, kind: str) -> list[Node]:
        return [n for n in self.root.iter_nodes() if n.kind == kind]

    def surfaces(self) -> list[SurfaceNode]:
        """All geometry surfaces in their canonical tree order."""
        geometry = self.geometry
        return geometry.surfaces() if geometry is not None else []

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
            interface for interface in self.interfaces()
            if (interface.name
                and INTERFACE_TYPES.get(interface.interface_type, {})
                .get("num_values", 0))
        ]

    def instance_names(self) -> list[str]:
        """Known FEA instance names, in first-use order.

        SIMP reads these from the linked TorchFEA Assembly.  Other schemes use
        their generated ``final_model`` instance plus any custom names already
        present in the interface tree.
        """
        names = [] if self.scheme == "simp" else ["final_model"]
        summary = self.imported_model_summary()
        if summary is not None:
            names.extend(item.name for item in summary.instances)
        for interface in self.interfaces():
            for field in ("instance_name", "instance_name1", "instance_name2"):
                value = getattr(interface, field, None)
                if isinstance(value, str) and value.strip():
                    names.append(value.strip())
        return list(dict.fromkeys(names))

    def part_names(self) -> list[str]:
        summary = self.imported_model_summary()
        return [part.name for part in summary.parts] if summary is not None else []

    def imported_model_summary(self):
        """Inspect the linked TorchFEA model, returning ``None`` if unset."""
        geometry = self.geometry
        if (self.scheme != "simp" or geometry is None
                or not geometry.model_directory or not geometry.model_filename):
            return None
        try:
            from ...optcore.modelparams.geometry import inspect_model
            return inspect_model(
                geometry.model_directory, geometry.model_filename)
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
                (item for item in summary.parts if item.name == part_name), None)
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
            interface.name for interface in self.interfaces()
            if interface.interface_type == "ReferencePoint" and interface.name
        ]

    def element_names(self, part_name: str = "") -> list[str]:
        """Material and load element-family names, in stable unique order."""
        names: list[str] = []
        part = self._part_summary(part_name=part_name)
        if part is not None:
            names.extend(part.element_types)
        if self.material is not None:
            for field in ("elementname", "shell_elementname"):
                value = getattr(self.material, field, None)
                if isinstance(value, str) and value.strip():
                    names.append(value.strip())
        for interface in self.interfaces():
            if isinstance(interface.element_name, str) and interface.element_name.strip():
                names.append(interface.element_name.strip())
        return list(dict.fromkeys(names))

    # typed top-level section accessors (return None when the scheme lacks it)
    def section(self, kind: str) -> Optional[Node]:
        return self.root.section(kind) if isinstance(self.root, ProblemNode) \
            else self.root.child(kind)

    @property
    def geometry(self) -> Optional[GeometryNode]:
        return self.section(KIND_GEOMETRY)

    @property
    def loads(self) -> Optional[LoadsNode]:
        return self.section(KIND_LOADS)

    @property
    def steps(self) -> Optional[StepsNode]:
        return self.section(KIND_STEPS)

    @property
    def material(self) -> Optional[MaterialNode]:
        return self.section(KIND_MATERIAL)

    @property
    def objective(self) -> Optional[ObjectiveNode]:
        return self.section(KIND_OBJECTIVE)

    @property
    def solver(self) -> Optional[SolverNode]:
        return self.section(KIND_SOLVER)

    @property
    def updater(self) -> Optional[UpdaterNode]:
        return self.section(KIND_UPDATER)

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
        after loading legacy files.
        """
        config = self._geometry_updater_config()
        if config is None:
            return

        count = len(self.surfaces())
        states = self._bool_list(config.get("if_update"))
        config["if_update"] = (states[:count] + [True] * count)[:count]

        for parameters in self._distance_constraint_parameters(config):
            matrix = self._square_matrix(parameters.get("min_distance"))
            if matrix is None:
                continue
            parameters["min_distance"] = self._resize_matrix(matrix, count)

    def add_surface(self, surface: SurfaceNode,
                    index: Optional[int] = None) -> SurfaceNode:
        """Insert ``surface`` and synchronise all surface-indexed state."""
        geometry = self._require_geometry()
        surfaces = geometry.surfaces()
        target_index = len(surfaces) if index is None else index
        if not 0 <= target_index <= len(surfaces):
            raise IndexError(f"Surface insertion index out of range: {target_index}")

        geometry.add_surface(surface, index=target_index)
        self._insert_surface_state(target_index)
        self._refresh_surface_flags()
        return surface

    def clone_surface(self, surface: SurfaceNode) -> SurfaceNode:
        """Duplicate ``surface`` directly below itself and return the copy."""
        geometry = self._require_geometry()
        position = geometry.index_of_surface(surface)
        clone = surface.clone()
        if not isinstance(clone, SurfaceNode):  # defensive for custom nodes
            raise TypeError("A surface clone must remain a SurfaceNode")
        return self.add_surface(clone, position + 1)

    def remove_surface(self, surface: SurfaceNode) -> None:
        """Remove one surface while preserving the remaining updater mapping."""
        geometry = self._require_geometry()
        surfaces = geometry.surfaces()
        if len(surfaces) <= 1:
            raise ValueError("A problem must keep at least one surface")
        position = geometry.index_of_surface(surface)
        geometry.remove_child(surface)
        self._remove_surface_state(position)
        self._refresh_surface_flags()

    def move_surface(self, surface: SurfaceNode, offset: int) -> bool:
        """Move a surface by ``offset`` positions and return whether it moved."""
        geometry = self._require_geometry()
        source = geometry.index_of_surface(surface)
        target = source + offset
        if not 0 <= target < geometry.surface_count():
            return False
        geometry.children[source], geometry.children[target] = (
            geometry.children[target], geometry.children[source])
        self._swap_surface_state(source, target)
        self._refresh_surface_flags()
        return True

    def suggest_interface_name(self, prefix: str) -> str:
        """Return the first unused ``<prefix><number>`` interface name."""
        names = {interface.name for interface in self.interfaces()}
        index = 1
        while f"{prefix}{index}" in names:
            index += 1
        return f"{prefix}{index}"

    def add_interface(self, interface: InterfaceNode,
                      index: Optional[int] = None) -> InterfaceNode:
        """Insert an interface into the load section."""
        self._require_loads().add_interface(interface, index=index)
        return interface

    def clone_interface(self, interface: InterfaceNode, name_prefix: str) -> InterfaceNode:
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
            loads.children[target], loads.children[source])
        return True

    def remove_interface(self, interface: InterfaceNode) -> None:
        """Remove an interface and every reference to its name."""
        self._require_loads().remove_child(interface)
        if self.steps is not None:
            for values in self.steps.step_values:
                values.pop(interface.name, None)
        if self.objective is not None:
            self.objective.jacobian_needed = [
                name for name in self.objective.jacobian_needed
                if name != interface.name
            ]

    def rename_interface(self, interface: InterfaceNode, new_name: str) -> bool:
        """Rename an interface and cascade its references.

        ``False`` means the requested name is blank or already belongs to a
        different interface; in that case the model remains unchanged.
        """
        new_name = new_name.strip()
        old_name = interface.name
        if not new_name or new_name == old_name:
            return False
        if any(item is not interface and item.name == new_name
               for item in self.interfaces()):
            return False

        interface.name = new_name
        if self.steps is not None:
            for values in self.steps.step_values:
                if old_name in values:
                    values[new_name] = values.pop(old_name)
        if self.objective is not None:
            self.objective.jacobian_needed = [
                new_name if name == old_name else name
                for name in self.objective.jacobian_needed
            ]
        return True

    # ---------------------------------------------------- mutation helpers
    def _require_geometry(self) -> GeometryNode:
        if self.geometry is None:
            raise ValueError("This problem has no geometry section")
        return self.geometry

    def _require_loads(self) -> LoadsNode:
        if self.loads is None:
            raise ValueError("This problem has no loads section")
        return self.loads

    def _geometry_updater_config(self) -> Optional[dict]:
        updater = self.updater
        return updater.geometry_config() if updater is not None else None

    @staticmethod
    def _bool_list(value: Any) -> list[bool]:
        if value is None:
            return []
        if isinstance(value, bool):
            return [value]
        if not isinstance(value, (list, tuple)):
            return [bool(value)]
        return [bool(item) for item in value]

    @staticmethod
    def _square_matrix(value: Any) -> Optional[list[list[float]]]:
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
            [rows[row_index][column_index]
             if row_index < len(rows) and column_index < len(rows[row_index])
             else 2.5
             for column_index in range(size)]
            for row_index in range(size)
        ]

    @staticmethod
    def _resize_matrix(matrix: list[list[float]], size: int) -> list[list[float]]:
        return [
            [matrix[row_index][column_index]
             if row_index < len(matrix) and column_index < len(matrix[row_index])
             else 2.5
             for column_index in range(size)]
            for row_index in range(size)
        ]

    @staticmethod
    def _distance_constraint_parameters(config: dict) -> Iterator[dict]:
        for constraint in config.get("constraints", []) or []:
            if (isinstance(constraint, dict)
                    and constraint.get("type") == "Distance"
                    and isinstance(constraint.get("params"), dict)):
                yield constraint["params"]

    def _insert_surface_state(self, index: int) -> None:
        config = self._geometry_updater_config()
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
        self.align_surface_dependent_state()

    def _remove_surface_state(self, index: int) -> None:
        config = self._geometry_updater_config()
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
        self.align_surface_dependent_state()

    def _swap_surface_state(self, first: int, second: int) -> None:
        config = self._geometry_updater_config()
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
        for index, surface in enumerate(self.surfaces()):
            surface.flip = index > 0

    # ----------------------------------------------------------- persistence
    def to_dict(self) -> dict:
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
    def from_dict(cls, data: dict) -> "ProblemDefinition":
        return cls(
            scheme=data.get("scheme", "shapeopt"),
            label=data.get("label", "Untitled"),
            result_folder=data.get("result_folder", ".results/"),
            device=data.get("device", "cpu"),
            updater_device=data.get("updater_device"),
            restart_per_iteration=data.get("restart_per_iteration", 10),
            root=Node.from_dict(data.get("root", {"kind": "problem"})),
        )


def find_node(root: Node, kind: str, name: Optional[str] = None) -> Optional[Node]:
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
