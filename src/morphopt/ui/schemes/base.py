"""Base scheme template and registry."""

from __future__ import annotations

from typing import Optional

from ..model.problem import (
    ProblemDefinition, Node,
    GeometryNode, SurfaceNode, InterfaceNode, LoadsNode, StepsNode,
    MaterialNode, ObjectiveNode, SolverNode, UpdaterNode,
)
from ..model import schemas as S
from .snippets import CodeSnippet, shared_fea_snippets


class SchemeTemplate:
    """Describes one optimization scheme for the UI.

    A template is the single source of truth for *one* task-tree shape: it
    declares the backend ``BASES`` mapping, the scheme's data (geometry
    title, material type, code-slot defaults) and builds a
    fully-populated :class:`ProblemDefinition` out of the typed task-tree
    nodes via the shared ``make_*`` section builders below.
    """

    scheme: str = ""
    label: str = ""
    label_en: str = ""
    #: material implementation chosen by this scheme's default tree.
    MATERIAL_TYPE: str = ""
    #: class-name mapping used by the code generator
    BASES: dict = {}
    #: display title of the Geometry section (used by the model tree)
    geometry_title: str = "Geometry"

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
    def make_surface(self, surface_type: str, index: int = 0,
                     **overrides) -> SurfaceNode:
        """Build a fresh surface; name stays empty, index 0 = outer."""
        return SurfaceNode.create(surface_type, index=index, **overrides)

    def make_interface(self, interface_type: str, name: Optional[str] = None,
                       **overrides) -> InterfaceNode:
        """Build a fresh load interface from schema defaults."""
        return InterfaceNode.create(interface_type, name=name, **overrides)

    def make_material(self, **overrides) -> MaterialNode:
        """Build a fresh material of this scheme's concrete type."""
        mat = MaterialNode.create(self.material_type, **overrides)
        if self.scheme in ("simp", "codesign"):
            mat.set_field("_map_bsp_designfield", self.default_map_bsp_designfield())
        return mat

    @property
    def material_type(self) -> str:
        """Concrete material class used by this scheme."""
        if not self.MATERIAL_TYPE:
            raise NotImplementedError(
                f"{type(self).__name__} must declare MATERIAL_TYPE")
        return self.MATERIAL_TYPE

    # ------------------------------------------------------ section builders
    # Each ``make_*`` constructs ONE explicit top-level section of the task
    # tree.  Scheme templates only *assemble* these (never hand-roll dicts),
    # so all schemes share identical structure and default population.
    def make_geometry(self, **overrides) -> GeometryNode:
        """Geometry section: scheme defaults + ``overrides`` + BC code slot."""
        from ..model.schemas import GEOMETRY_SCHEMES, clone_defaults
        defaults = clone_defaults(list(GEOMETRY_SCHEMES.get(self.scheme, [])))
        defaults.update(overrides)
        geo = GeometryNode(name=self.geometry_title, params=defaults)
        return geo

    def make_loads(self) -> LoadsNode:
        """Loads section (empty container; add interfaces afterwards)."""
        return LoadsNode(name="Loads")

    def make_steps(self, num_steps: int, step_values: list) -> StepsNode:
        """Steps section: total count + per-interface amplitudes per step."""
        return StepsNode(name="Load steps", params={
            "num_steps": int(num_steps),
            "step_values": list(step_values),
        })

    def make_objective(self, objective: Optional[str] = None,
                       metrics: Optional[str] = None,
                       jacobian_needed: Optional[list] = None) -> ObjectiveNode:
        """Objective section: code slots + requested load Jacobian names."""
        return ObjectiveNode(name="Objective Function", params={
            "jacobian_needed": (list(jacobian_needed)
                                if jacobian_needed is not None
                                else self.default_jacobian_needed()),
            "_objective_function": objective or self.default_objective_slot(),
            "_get_metrics": metrics or self.default_metrics_slot(),
        })

    def make_solver(self, num_process: int = 1, gpus=None,
                    task_index_list=None) -> SolverNode:
        """Solver section: FEA process count, gpus and task partitioning."""
        return SolverNode(name="Solver", params={
            "num_process": int(num_process),
            "gpus": list(gpus or []),
            "task_index_list": list(task_index_list or []),
        })

    def make_updater(self, geometry: Optional[dict] = None,
                     materials: Optional[dict] = None) -> UpdaterNode:
        """Updater section; ``geometry``/``materials`` are sub-updater configs."""
        return UpdaterNode(name="Updater",
                           params={"geometry": geometry, "materials": materials})

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

    # -------------------------------------------------------- updater slots
    def default_updater_geometry_code(self) -> str:
        return ""

    def default_updater_material_code(self) -> str:
        return ""

    # ---------------------------------------------------------- code slots
    def default_apply_surface_constraints(self) -> str:
        return "pass\n"

    def default_map_bsp_designfield(self) -> str:
        return "return None\n"


#: registry name -> template instance (built lazily to avoid import cycles)
SCHEME_REGISTRY: dict[str, SchemeTemplate] = {}


def _build_registry() -> None:
    if SCHEME_REGISTRY:
        return
    from . import shapeopt as _so
    from . import simp as _sp
    from . import codesign as _cd

    for t in (_so.ShapeoptTemplate(), _sp.SIMPTemplate(), _cd.CodesignTemplate()):
        SCHEME_REGISTRY[t.scheme] = t


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
