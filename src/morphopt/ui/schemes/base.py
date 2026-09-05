"""Base scheme template and registry."""

from __future__ import annotations

from ..model.problem import ProblemDefinition, Node
from ..model import schemas as S
from ..model.schemas import clone_defaults


class SchemeTemplate:
    """Describes one optimization scheme for the UI.

    Subclasses fill in the pieces needed to build a default problem and to
    generate runnable morphopt code (the generator lives in
    :mod:`morphopt.ui.codegen.generator` and asks the template for its
    ``BASES`` mapping and code-slot defaults).
    """

    scheme: str = ""
    label: str = ""
    #: class-name mapping used by the code generator
    BASES: dict = {}

    # ------------------------------------------------------------------ ui
    def create_problem(self, label: str) -> ProblemDefinition:
        """Build a fully-populated default problem tree for this scheme."""
        problem = ProblemDefinition(scheme=self.scheme, label=label)
        problem.root = self.build_root()
        problem.root.name = label
        return problem

    def build_root(self) -> Node:
        raise NotImplementedError

    # ---------------------------------------------------------- factories
    def new_surface_node(self, surface_type: str, index: int) -> Node:
        spec = S.surface_spec(surface_type)
        params = {"type": surface_type}
        params.update(clone_defaults(spec["params"]))
        params["flip"] = index > 0  # inner cavities flip their normals
        role = S.SURFACE_ROLE_NAMES.get(index, f"Surface {index}")
        return Node("surface", name=f"{spec['label']} · {role}", params=params)

    def new_interface_node(self, interface_type: str) -> Node:
        spec = S.interface_spec(interface_type)
        params = {"type": interface_type}
        params.update(clone_defaults(spec["params"]))
        return Node("interface", name=f"{spec['name_hint']}{interface_type}", params=params)

    def new_material_node(self) -> Node:
        mtype = S.MATERIAL_BY_SCHEME[self.scheme][0]
        spec = S.material_spec(mtype)
        params = {"type": mtype}
        params.update(clone_defaults(spec["params"]))
        return Node("material", name=spec["label"], params=params)

    # ----------------------------------------------------- objective slots
    def default_objective_slot(self) -> str:
        return "return self.fe_results[0].GC[-2]\n"

    def default_metrics_slot(self) -> str:
        return "return [self.fe_results[0].GC[-2]]\n"

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
