"""File-backed optimization templates and their registry."""

from __future__ import annotations

import json
from pathlib import Path

from ..model import schemas as S
from ..model.problem import (
    GeometryNode,
    InterfaceNode,
    LoadsNode,
    MaterialNode,
    MaterialsNode,
    Node,
    ObjectiveNode,
    PartInterfaceNode,
    ProblemDefinition,
    SolverNode,
    StepsNode,
    SurfaceNode,
    UpdaterNode,
)
from .snippets import CodeSnippet, shared_fea_snippets


class SchemeTemplate:
    """Describes one optimization scheme for the UI.

    A template is the single source of truth for *one* task-tree shape: it
    declares starter data (geometry title, default material type and code-slot
    defaults) and builds a
    fully-populated :class:`ProblemDefinition` out of the typed task-tree
    nodes via the shared ``make_*`` section builders below.
    """

    scheme: str = ""
    label: str = ""
    label_en: str = ""
    #: material implementation chosen by this scheme's default tree.
    MATERIAL_TYPE: str = ""
    #: display title of the Geometry section (used by the model tree)
    geometry_title: str = "Geometry"
    #: registration (Part) name of the scheme's default geometry
    BODY_NAME: str = "body"

    # ------------------------------------------------------------------ ui
    def create_problem(self, label: str) -> ProblemDefinition:
        """Build a fully-populated default problem tree for this scheme."""
        problem = ProblemDefinition(scheme=self.scheme, label=label)
        problem.root = self.build_root()
        problem.root.name = label
        return problem

    def build_root(self) -> Node:
        raise NotImplementedError

    # ------------------------------------------------------- node factories
    # Low-level factories delegate to the typed node classes, so schema
    # defaults + validation live in exactly one place (model/problem.py).
    def make_surface(
        self, surface_type: str, index: int = 0, **overrides
    ) -> SurfaceNode:
        """Build a fresh surface; name stays empty, index 0 = outer."""
        return SurfaceNode.create(surface_type, index=index, **overrides)

    def make_interface(
        self, interface_type: str, name: str | None = None, **overrides
    ) -> InterfaceNode:
        """Build a fresh load interface from schema defaults."""
        return InterfaceNode.create(interface_type, name=name, **overrides)

    def make_material(
        self, material_type: str | None = None, **overrides
    ) -> MaterialNode:
        """Build a fresh material interface."""
        selected_type = material_type or self.material_type
        if selected_type not in self.available_material_types():
            raise ValueError(
                f"Unknown material interface type {selected_type!r}."
            )
        mat = MaterialNode.create(selected_type, **overrides)
        return mat

    def available_material_types(self) -> tuple[str, ...]:
        """Return every material interface supported by the unified kernel."""
        return tuple(S.MATERIAL_TYPES)

    def make_materials(self, *materials: MaterialNode) -> MaterialsNode:
        """Build the material-interface collection for the problem tree."""
        section = MaterialsNode(name="Materials")
        for material in materials:
            section.add_material(material)
        return section

    @property
    def material_type(self) -> str:
        """Concrete material class used by this scheme."""
        if not self.MATERIAL_TYPE:
            raise NotImplementedError(
                f"{type(self).__name__} must declare MATERIAL_TYPE"
            )
        return self.MATERIAL_TYPE

    # ------------------------------------------------------ section builders
    # Each ``make_*`` constructs ONE explicit top-level section of the task
    # tree.  Scheme templates only *assemble* these (never hand-roll dicts),
    # so all schemes share identical structure and default population.
    def make_geometry(self, name: str | None = None) -> GeometryNode:
        """Geometry section: an empty container for geometry interfaces."""
        return GeometryNode(name=name or self.geometry_title)

    def make_part_interface(
        self, interface_type: str | None = None, name: str | None = None, **overrides
    ) -> PartInterfaceNode:
        """Build one part interface (Part + Instances) of this scheme."""
        selected = interface_type or self.default_part_interface_type()
        if selected not in self.available_geometry_types():
            raise ValueError(
                f"Unknown geometry interface type {selected!r}."
            )
        return PartInterfaceNode.create(selected, name=name or "", **overrides)

    def available_geometry_types(self) -> tuple[str, ...]:
        """Return every UI-enabled Part interface.

        Templates choose an initial model only.  The Part types that can be
        combined into that model are independent of the starter template.
        """
        return tuple(
            name
            for name, spec in S.PART_INTERFACE_TYPES.items()
            if not spec.get("hidden", False)
        )

    def default_part_interface_type(self) -> str:
        """Part-interface type used by this scheme's default geometry."""
        types = self.available_geometry_types()
        if not types:
            raise NotImplementedError(
                f"{type(self).__name__} declares no geometry interfaces"
            )
        return types[0]

    def make_geometry_with_body(self, **overrides):
        """Default geometry section holding one empty boundary part."""
        geometry = self.make_geometry()
        geometry.add_interface(
            self.make_part_interface(
                self.default_part_interface_type(), name=self.body_name, **overrides
            )
        )
        return geometry

    @property
    def body_name(self) -> str:
        """Registration (Part) name of the scheme's default geometry."""
        return self.BODY_NAME

    @property
    def body_instance_name(self) -> str:
        """Instance name generated for the default geometry's Part."""
        return f"{self.body_name}-1"

    def make_loads(self) -> LoadsNode:
        """Loads section (empty container; add interfaces afterwards)."""
        return LoadsNode(name="Loads")

    def make_steps(self, num_steps: int, step_values: list) -> StepsNode:
        """Steps section: total count + per-interface amplitudes per step."""
        return StepsNode(
            name="Load steps",
            params={
                "num_steps": int(num_steps),
                "step_values": list(step_values),
            },
        )

    def make_objective(
        self,
        objective: str | None = None,
        metrics: str | None = None,
        jacobian_needed: list | None = None,
    ) -> ObjectiveNode:
        """Objective section: code slots + requested load Jacobian names."""
        return ObjectiveNode(
            name="Objective Function",
            params={
                "jacobian_needed": (
                    list(jacobian_needed)
                    if jacobian_needed is not None
                    else self.default_jacobian_needed()
                ),
                "_objective_function": objective or self.default_objective_slot(),
                "_get_metrics": metrics or self.default_metrics_slot(),
            },
        )

    def make_solver(
        self, num_process: int = 1, gpus=None, task_index_list=None
    ) -> SolverNode:
        """Solver section: FEA process count, gpus and task partitioning."""
        return SolverNode(
            name="Solver",
            params={
                "num_process": int(num_process),
                "gpus": list(gpus or []),
                "task_index_list": list(task_index_list or []),
            },
        )

    def make_updater(
        self, geometry: dict | None = None, materials: dict | None = None
    ) -> UpdaterNode:
        """Updater section; ``geometry``/``materials`` are sub-updater configs."""
        return UpdaterNode(
            name="Updater",
            params={
                "geometry": [geometry] if geometry is not None else [],
                "materials": [materials] if materials is not None else [],
            },
        )

    # ----------------------------------------------------- objective slots
    def default_objective_slot(self) -> str:
        return "return self.fe_results[0].GC[-2]\n"

    def default_metrics_slot(self) -> str:
        return "return [self.fe_results[0].GC[-2]]\n"

    def objective_code_snippets(self) -> tuple[CodeSnippet, ...]:
        """Snippets offered by the Objective editor for this scheme.

        Subclasses may extend this only for fields guaranteed by that scheme;
        general-purpose FEA extraction lives in :mod:`.snippets`.
        """
        return shared_fea_snippets()

    def default_jacobian_needed(self) -> list:
        return []

    # ---------------------------------------------------------- code slots
    def default_apply_surface_constraints(self) -> str:
        return "pass\n"


class MorphTemplate(SchemeTemplate):
    """Optimization template loaded from one ``ui/templates/*.morph`` file.

    The file is an ordinary problem definition plus a small top-level
    ``template`` mapping.  This keeps the starter tree editable in the same
    format as user projects while making new templates discoverable without
    adding Python registration code.
    """

    def __init__(self, path: Path, data: dict) -> None:
        meta = dict(data.get("template") or {})
        self.path = path
        self.scheme = str(data.get("scheme") or meta.get("id") or path.stem)
        self.label = str(meta.get("label") or self.scheme)
        self.label_en = str(meta.get("label_en") or self.label)
        self.MATERIAL_TYPE = str(meta.get("material_type") or "")
        self.geometry_title = str(meta.get("geometry_title") or "Geometry")
        self.BODY_NAME = str(meta.get("body_name") or "body")
        self._blank_interface_fields = tuple(
            meta.get("blank_interface_fields")
            or (
                "instance_name",
                "instance_name1",
                "instance_name2",
                "surface_name",
                "surface_name1",
                "surface_name2",
                "set_nodes_name",
            )
        )
        self._objective_slot = meta.get("default_objective_slot")
        self._metrics_slot = meta.get("default_metrics_slot")
        self._problem = ProblemDefinition.from_dict(data)

    def create_problem(self, label: str) -> ProblemDefinition:
        """Clone the file tree so each newly selected template is isolated."""
        problem = ProblemDefinition.from_dict(self._problem.to_dict())
        problem.scheme = self.scheme
        problem.label = label
        problem.root.name = label
        return problem

    def build_root(self) -> Node:
        return Node.from_dict(self._problem.root.to_dict())

    def make_interface(
        self, interface_type: str, name: str | None = None, **overrides
    ) -> InterfaceNode:
        spec = S.INTERFACE_TYPES.get(interface_type, {})
        for field in spec.get("params", []):
            if field["key"] in self._blank_interface_fields:
                overrides.setdefault(field["key"], "")
        return super().make_interface(interface_type, name=name, **overrides)

    def default_objective_slot(self) -> str:
        return self._objective_slot or super().default_objective_slot()

    def default_metrics_slot(self) -> str:
        return self._metrics_slot or super().default_metrics_slot()

#: Registry name -> template instance.  It is built lazily so importing the
#: data model never scans the package filesystem unnecessarily.
SCHEME_REGISTRY: dict[str, SchemeTemplate] = {}
TEMPLATE_DIRECTORY = Path(__file__).resolve().parents[1] / "templates"
HIDDEN_TEMPLATE_IDS = {"codesign"}


def _build_registry() -> None:
    if SCHEME_REGISTRY:
        return
    if not TEMPLATE_DIRECTORY.is_dir():
        raise FileNotFoundError(
            f"MorphOpt template directory does not exist: {TEMPLATE_DIRECTORY}"
        )
    for path in sorted(TEMPLATE_DIRECTORY.glob("*.morph")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid MorphOpt template file: {path}") from exc
        template = MorphTemplate(path, data)
        if template.scheme in HIDDEN_TEMPLATE_IDS:
            continue
        if template.scheme in SCHEME_REGISTRY:
            raise ValueError(f"Duplicate MorphOpt template id: {template.scheme!r}")
        SCHEME_REGISTRY[template.scheme] = template


def available_templates() -> tuple[SchemeTemplate, ...]:
    """Return the visible file-backed templates in filename order."""
    _build_registry()
    return tuple(SCHEME_REGISTRY.values())


def get_template(scheme: str) -> SchemeTemplate:
    _build_registry()
    if scheme not in SCHEME_REGISTRY:
        raise KeyError(f"No scheme template registered for {scheme!r}")
    return SCHEME_REGISTRY[scheme]


def scheme_label(scheme: str, *, english: bool = False) -> str:
    """Return a scheme-owned display name without consulting field schemas."""
    try:
        template = get_template(scheme)
    except KeyError:
        return scheme
    return template.label_en if english else template.label
