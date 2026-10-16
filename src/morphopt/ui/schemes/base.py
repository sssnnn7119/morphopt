"""Python-defined optimization scheme policies."""

from __future__ import annotations

from ...constants import CONSTANT
from ..i18n import localized_message, localization, tr
from ..model import registry as R
from ..model.problem import (
    GeometryNode,
    FEAComponentNode,
    LoadsNode,
    MaterialNode,
    MaterialsNode,
    Node,
    ObjectiveNode,
    PartNode,
    ProblemDefinition,
    SolverNode,
    StepsNode,
    SurfaceNode,
    UpdaterNode,
)
from .snippets import CodeSnippet, shared_fea_snippets


class SchemeTemplate:
    """Describes shared factories and policies for one optimization scheme.

    Built-in schemes keep policy in Python and use typed task-tree nodes with
    the shared ``make_*`` factories.
    """

    scheme: str = ""
    label_key: str = ""
    #: material implementation chosen by this scheme's default tree.
    MATERIAL_TYPE: str = ""
    #: Internal section name; presentation supplies the localized title.
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

    def make_component(
        self, component_type: str, name: str | None = None, **overrides
    ) -> FEAComponentNode:
        """Build a fresh FEA component from schema defaults."""
        return FEAComponentNode.create(component_type, name=name, **overrides)

    def make_material(
        self, material_type: str | None = None, **overrides
    ) -> MaterialNode:
        """Build a fresh material definition."""
        selected_type = material_type or self.material_type
        if selected_type not in self.available_material_types():
            raise ValueError(
                localized_message("ui.errors.base.unknown_material_type_value", value_0=selected_type)
            )
        mat = MaterialNode.create(selected_type, **overrides)
        return mat

    def available_material_types(self) -> tuple[str, ...]:
        """Return every material type supported by the kernel."""
        return tuple(R.MATERIAL_TYPES)

    def make_materials(self, *materials: MaterialNode) -> MaterialsNode:
        """Build the material collection for the problem tree."""
        section = MaterialsNode(name="Materials")
        for material in materials:
            section.add_material(material)
        return section

    @property
    def material_type(self) -> str:
        """Concrete material class used by this scheme."""
        if not self.MATERIAL_TYPE:
            raise NotImplementedError(
                localized_message("ui.errors.base.value_must_declare_material_type", value_0=type(self).__name__)
            )
        return self.MATERIAL_TYPE

    # ------------------------------------------------------ section builders
    # Each ``make_*`` constructs ONE explicit top-level section of the task
    # tree.  Scheme policies only *assemble* these (never hand-roll dicts),
    # so all schemes share identical structure and default population.
    def make_geometry(self, name: str | None = None) -> GeometryNode:
        """Geometry section: an empty container for Part definitions."""
        return GeometryNode(name=name or self.geometry_title)

    def make_part(
        self, part_type: str | None = None, name: str | None = None, **overrides
    ) -> PartNode:
        """Build one Part (and its Instances) for this scheme."""
        selected = part_type or self.default_part_type()
        if selected not in self.available_geometry_types():
            raise ValueError(
                localized_message("ui.errors.base.unknown_part_type_value", value_0=selected)
            )
        return PartNode.create(selected, name=name or "", **overrides)

    def available_geometry_types(self) -> tuple[str, ...]:
        """Return every Part type enabled in the UI.

        Quickstart chooses an initial model only. The Part types that can be
        combined into that model are independent of the starter template.
        """
        return tuple(
            name
            for name, spec in R.PART_TYPES.items()
            if not spec.hidden and not spec.custom_only
        )

    def default_part_type(self) -> str:
        """Part type used by this scheme's default geometry."""
        types = self.available_geometry_types()
        if not types:
            raise NotImplementedError(
                localized_message("ui.errors.base.value_declares_no_geometry_parts", value_0=type(self).__name__)
            )
        return types[0]

    def make_geometry_with_body(self, **overrides):
        """Default geometry section holding one empty boundary part."""
        geometry = self.make_geometry()
        geometry.add_part(
            self.make_part(
                self.default_part_type(), name=self.body_name, **overrides
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
        """Loads section (empty container; add components afterwards)."""
        return LoadsNode(name="Loads")

    def make_steps(self, num_steps: int, step_values: list) -> StepsNode:
        """Steps section: total count + per-component amplitudes per step."""
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
        """Objective section with editable objective and metric terms."""
        return ObjectiveNode(
            name="Objective Function",
            params={
                "objective_terms": [{
                    "type": CONSTANT.UI.OBJECTIVE.TYPE_CUSTOM_LOSS,
                    "body": objective or self.default_objective_slot(),
                    "weight": CONSTANT.UI.OBJECTIVE.DEFAULT_WEIGHT,
                }],
                "metrics_terms": [{
                    "type": CONSTANT.UI.METRIC.TYPE_CUSTOM,
                    "body": metrics or self.default_metrics_slot(),
                }],
                "jacobian_needed": (
                    list(jacobian_needed)
                    if jacobian_needed is not None
                    else self.default_jacobian_needed()
                ),
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


class BuiltinSchemeTemplate(SchemeTemplate):
    """Python-defined scheme policy for an optimization method.

    Quickstart now owns starter-model construction. These built-ins provide
    the scheme-specific defaults still needed by editors and code generation.
    """

    def __init__(
        self,
        scheme: str,
        label_key: str,
        material_type: str,
        body_name: str = "body",
        quickstart_method: str | None = "shapeopt",
        objective_slot: str | None = None,
        metrics_slot: str | None = None,
    ) -> None:
        self.scheme = scheme
        self.label_key = label_key
        self.MATERIAL_TYPE = material_type
        self.BODY_NAME = body_name
        self._quickstart_method = quickstart_method
        self._objective_slot = objective_slot
        self._metrics_slot = metrics_slot

    @property
    def has_starter(self) -> bool:
        return self._quickstart_method is not None

    def create_problem(self, label: str) -> ProblemDefinition:
        """Create a starter definition through the current Quickstart builder."""
        if self._quickstart_method is None:
            raise ValueError(
                localized_message(
                    "ui.errors.base.no_builtin_starter_for_scheme_value",
                    value_0=self.scheme,
                )
            )
        from ..application.quickstart import QuickstartOptions, build_quickstart

        options = QuickstartOptions.for_method(self._quickstart_method)
        options.label = label
        problem = build_quickstart(options)
        problem.scheme = self.scheme
        return problem

    def build_root(self) -> Node:
        return self.create_problem(f"{self.scheme}_untitled").root

    def make_component(
        self, component_type: str, name: str | None = None, **overrides
    ) -> FEAComponentNode:
        """Keep target references empty until the user chooses a target."""
        blank_fields = {
            "instance_name",
            "instance_name1",
            "instance_name2",
            "surface_name",
            "surface_name1",
            "surface_name2",
            "set_nodes_name",
        }
        for field in R.LOAD_TYPES[component_type].fields:
            if field.key in blank_fields:
                overrides.setdefault(field.key, "")
        return super().make_component(component_type, name=name, **overrides)

    def default_objective_slot(self) -> str:
        return self._objective_slot or super().default_objective_slot()

    def default_metrics_slot(self) -> str:
        return self._metrics_slot or super().default_metrics_slot()


BUILTIN_SCHEMES = (
    BuiltinSchemeTemplate(
        scheme="shapeopt",
        label_key="ui.templates.shapeopt.label",
        material_type="HomogeneousMaterial",
        body_name="body",
        quickstart_method="shapeopt",
        objective_slot="return self.fe_results[0].GC[-2]\n",
        metrics_slot="return [self.fe_results[0].GC[-2]]\n",
    ),
    BuiltinSchemeTemplate(
        scheme="simp",
        label_key="ui.templates.simp.label",
        material_type="SIMP_BSPFieldMaterials",
        body_name="body",
        quickstart_method="simp",
        objective_slot=(
            "RGC = self.fe.assembly._GC2RGC(self.fe_results[0].GC)\n"
            "return sum(instance.potential_energy(RGC=RGC)\n"
            "           for instance in self.fe.assembly._instances.values())\n"
        ),
        metrics_slot="return [self.fe_results[0].GC[-2]]\n",
    ),
)

LEGACY_SCHEME_POLICIES = (
    BuiltinSchemeTemplate(
        scheme="multidesign",
        label_key="ui.templates.multidesign.label",
        material_type="HomogeneousMaterial",
        body_name="body",
        quickstart_method=None,
        objective_slot="return self.fe_results[0].GC[-2]\n",
        metrics_slot="return [self.fe_results[0].GC[-2]]\n",
    ),
)

# The registry is static Python data. User ``.morph`` files are problem
# definitions opened through the regular file workflow.
SCHEME_REGISTRY: dict[str, SchemeTemplate] = {
    template.scheme: template
    for template in (*BUILTIN_SCHEMES, *LEGACY_SCHEME_POLICIES)
}


def available_templates() -> tuple[SchemeTemplate, ...]:
    """Return built-in schemes that can create a starter definition."""
    return tuple(
        template
        for template in SCHEME_REGISTRY.values()
        if not isinstance(template, BuiltinSchemeTemplate) or template.has_starter
    )


def get_template(scheme: str) -> SchemeTemplate:
    if scheme not in SCHEME_REGISTRY:
        raise KeyError(localized_message("ui.errors.base.no_scheme_template_registered_for_value", value_0=scheme))
    return SCHEME_REGISTRY[scheme]


def scheme_label(scheme: str, *, english: bool | None = None) -> str:
    """Return a scheme-owned display name without consulting field schemas."""
    try:
        template = get_template(scheme)
    except KeyError:
        return scheme
    if english is None:
        return tr(template.label_key)
    return localization.load_locale("en-US" if english else "zh-CN")[template.label_key]
