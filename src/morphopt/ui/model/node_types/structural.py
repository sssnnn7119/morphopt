"""Concrete problem structure and model-section nodes."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Any, ClassVar

from ....constants import CONSTANT
from ...i18n import localized_message
from ..base_nodes import (
    KIND_GEOMETRY,
    KIND_INSTANCE,
    KIND_LOADS,
    KIND_MATERIALS,
    KIND_OBJECTIVE,
    KIND_PROBLEM,
    KIND_SOLVER,
    KIND_STEPS,
    KIND_UPDATER,
    FEAComponentNode,
    MaterialNode,
    Node,
    PartNode,
    SurfaceNode,
)
from ..fields import FieldSpec

if TYPE_CHECKING:
    from .parts import BoundaryPartNode


class ProblemNode(Node):
    """Root of one problem-definition tree; holds the ordered sections."""

    kind = KIND_PROBLEM
    label_key: ClassVar[str] = "ui.widgets.model_tree.container.problem"
    backend_class: ClassVar[str] = "Controller"

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict[str, Any] | None = None,
        children: Sequence[Node] | None = None,
    ) -> None:
        self.geometry: GeometryNode | None = None
        self.loads: LoadsNode | None = None
        self.steps: StepsNode | None = None
        self.materials: MaterialsNode | None = None
        self.objective: ObjectiveNode | None = None
        self.solver: SolverNode | None = None
        self.updater: UpdaterNode | None = None
        super().__init__(kind=kind, name=name, params=params, children=children)

    @property
    def children(self) -> tuple[Node, ...]:
        return tuple(
            section
            for section in (
                self.geometry,
                self.loads,
                self.steps,
                self.materials,
                self.objective,
                self.solver,
                self.updater,
            )
            if section is not None
        )

    def add_child(self, node: Node, index: int | None = None) -> Node:
        if isinstance(node, GeometryNode):
            if self.geometry is not None:
                raise ValueError(
                    localized_message(
                        "ui.errors.nodes.duplicate_section", section=node.kind
                    )
                )
            self.geometry = node
        elif isinstance(node, LoadsNode):
            if self.loads is not None:
                raise ValueError(
                    localized_message(
                        "ui.errors.nodes.duplicate_section", section=node.kind
                    )
                )
            self.loads = node
        elif isinstance(node, StepsNode):
            if self.steps is not None:
                raise ValueError(
                    localized_message(
                        "ui.errors.nodes.duplicate_section", section=node.kind
                    )
                )
            self.steps = node
        elif isinstance(node, MaterialsNode):
            if self.materials is not None:
                raise ValueError(
                    localized_message(
                        "ui.errors.nodes.duplicate_section", section=node.kind
                    )
                )
            self.materials = node
        elif isinstance(node, ObjectiveNode):
            if self.objective is not None:
                raise ValueError(
                    localized_message(
                        "ui.errors.nodes.duplicate_section", section=node.kind
                    )
                )
            self.objective = node
        elif isinstance(node, SolverNode):
            if self.solver is not None:
                raise ValueError(
                    localized_message(
                        "ui.errors.nodes.duplicate_section", section=node.kind
                    )
                )
            self.solver = node
        elif isinstance(node, UpdaterNode):
            if self.updater is not None:
                raise ValueError(
                    localized_message(
                        "ui.errors.nodes.duplicate_section", section=node.kind
                    )
                )
            self.updater = node
        else:
            return super().add_child(node, index)
        return node

    def remove_child(self, node: Node) -> None:
        if node is self.geometry:
            self.geometry = None
        elif node is self.loads:
            self.loads = None
        elif node is self.steps:
            self.steps = None
        elif node is self.materials:
            self.materials = None
        elif node is self.objective:
            self.objective = None
        elif node is self.solver:
            self.solver = None
        elif node is self.updater:
            self.updater = None
        else:
            super().remove_child(node)

    def add_section(self, node: Node) -> Node:
        return self.add_child(node)

    def section(self, kind: str) -> Node | None:
        return {
            "geometry": self.geometry,
            "loads": self.loads,
            "steps": self.steps,
            "materials": self.materials,
            "objective": self.objective,
            "solver": self.solver,
            "updater": self.updater,
        }[kind]

    def sections(self) -> list[Node]:
        return list(self.children)


class GeometryNode(Node):
    """Initial-geometry section: an ordered set of Part definitions.

    Every :class:`PartNode` owns one Part plus its Instances;
    parameterised Parts additionally own their boundary surfaces as
    children (index 0 = outer boundary, 1.. = cavities).  The default
    Instance is ``<part>-1``; extra Instances are declared in the Part's
    ``define_instance`` method.

    Geometry-specific parameters belong to the child Parts. This node only
    owns and orders those Parts.
    """

    parts: list[PartNode]

    kind = KIND_GEOMETRY
    label_key: ClassVar[str] = "ui.widgets.model_tree.container.geometry"
    backend_class: ClassVar[str] = "GeometryParams"
    _FIELDS = ()

    @property
    def children(self) -> tuple[PartNode, ...]:
        return tuple(self.parts)

    def add_child(self, node: Node, index: int | None = None) -> Node:
        if not isinstance(node, PartNode):
            return super().add_child(node, index)
        if index is None:
            self.parts.append(node)
        else:
            self.parts.insert(index, node)
        return node

    def remove_child(self, node: Node) -> None:
        if not isinstance(node, PartNode):
            return super().remove_child(node)
        self.parts.remove(node)

    def __init__(
        self,
        kind: str | None = None,
        name: str = "Geometry",
        params: dict | None = None,
        children: Sequence[Node] | None = None,
    ) -> None:
        self.parts: list[PartNode] = []
        super().__init__(kind=kind, name=name, children=children)

    # --------------------------------------------------------------- Parts
    def add_part(self, part: PartNode, index: int | None = None) -> PartNode:
        """Attach one Part definition and return it."""
        self.add_child(part, index)
        return part

    def owner(self, surface: SurfaceNode) -> BoundaryPartNode | None:
        """Part holding ``surface`` (``None`` when it is detached)."""
        from .parts import BoundaryPartNode

        return next(
            (
                part
                for part in self.parts
                if isinstance(part, BoundaryPartNode) and surface in part.surfaces
            ),
            None,
        )

    # ------------------------------------------------------------- surfaces
    def surfaces(self) -> list[SurfaceNode]:
        """All boundary surfaces of every Part, in the canonical order."""
        from .parts import BoundaryPartNode

        return [
            surface
            for part in self.parts
            if isinstance(part, BoundaryPartNode)
            for surface in part.surfaces
        ]

    def surface_count(self) -> int:
        return len(self.surfaces())


class InstanceNode(Node):
    """One placement of a Part in the TorchFEA Assembly.

    ``translation`` and ``rotation`` are the three translational and three
    rotational exponential-coordinate components passed to TorchFEA as one
    ``[tx, ty, tz, rx, ry, rz]`` pose.
    """

    kind = KIND_INSTANCE
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "translation",
            "ui.schema.fields.translation.label.translation",
            "vec3",
            (0.0, 0.0, 0.0),
            doc_key="ui.schema.fields.translation.help.translation_tx_ty_tz_of_this_instance",
        ),
        FieldSpec(
            "rotation",
            "ui.schema.fields.rotation.label.rotation_exponential_coordinates",
            "vec3",
            (0.0, 0.0, 0.0),
            doc_key="ui.schema.fields.rotation.help.rotation_exponential_coordinates_rx_ry_rz",
        ),
    )

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict | None = None,
        children: Sequence[Node] | None = None,
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
            raise ValueError(
                localized_message(
                    "ui.errors.nodes.instance_value_must_have_exactly_3_components",
                    value_0=label,
                )
            )
        return values

    @property
    def pose(self) -> list[float]:
        """Return TorchFEA's six-component translation/rotation pose."""
        if isinstance(self.translation, str) or isinstance(self.rotation, str):
            raise ValueError(
                localized_message(
                    "ui.errors.nodes.a_helper_variable_pose_cannot_be_previewed_before_execution"
                )
            )
        return [*self.translation, *self.rotation]


class LoadsNode(Node):
    """Holds FEA components (loads, constraints, reference points, contacts)."""

    components: list[FEAComponentNode]

    kind = KIND_LOADS
    label_key: ClassVar[str] = "ui.widgets.model_tree.container.loads"
    backend_class: ClassVar[str] = ""

    @property
    def children(self) -> tuple[FEAComponentNode, ...]:
        return tuple(self.components)

    def add_child(self, node: Node, index: int | None = None) -> Node:
        if not isinstance(node, FEAComponentNode):
            return super().add_child(node, index)
        if index is None:
            self.components.append(node)
        else:
            self.components.insert(index, node)
        return node

    def remove_child(self, node: Node) -> None:
        if not isinstance(node, FEAComponentNode):
            return super().remove_child(node)
        self.components.remove(node)

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict[str, Any] | None = None,
        children: Sequence[Node] | None = None,
    ) -> None:
        self.components: list[FEAComponentNode] = []
        super().__init__(kind=kind, name=name, params=params, children=children)

    def add_component(
        self, component: FEAComponentNode, index: int | None = None
    ) -> FEAComponentNode:
        """Attach an FEA component and return it."""
        self.add_child(component, index)
        return component


class StepsNode(Node):
    """Load-step plan: total step count + per-component amplitudes per step.

    Canonical parameters are explicit, typed attributes assigned in
    ``__init__`` (``num_steps`` and ``step_values``).
    """

    kind = KIND_STEPS
    label_key: ClassVar[str] = "ui.widgets.model_tree.container.steps"
    backend_class: ClassVar[str] = ""
    _FIELDS = ("num_steps", "step_values")

    def __init__(
        self,
        kind: str | None = None,
        name: str = "Load steps",
        params: dict | None = None,
        children: Sequence[Node] | None = None,
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
        yield (
            "step_values",
            [
                {
                    key.name if isinstance(key, FEAComponentNode) else str(key): value
                    for key, value in step.items()
                }
                for step in self.step_values
            ],
        )


class MaterialsNode(Node):
    """Container for the ordered material definitions."""

    assignments: list[MaterialNode]

    kind = KIND_MATERIALS
    label_key: ClassVar[str] = "ui.widgets.model_tree.container.materials"
    backend_class: ClassVar[str] = "MaterialsParams"

    @property
    def children(self) -> tuple[MaterialNode, ...]:
        return tuple(self.assignments)

    def add_child(self, node: Node, index: int | None = None) -> Node:
        if not isinstance(node, MaterialNode):
            return super().add_child(node, index)
        if index is None:
            self.assignments.append(node)
        else:
            self.assignments.insert(index, node)
        return node

    def remove_child(self, node: Node) -> None:
        if not isinstance(node, MaterialNode):
            return super().remove_child(node)
        self.assignments.remove(node)

    def __init__(
        self,
        kind: str | None = None,
        name: str = "",
        params: dict[str, Any] | None = None,
        children: Sequence[Node] | None = None,
    ) -> None:
        self.assignments: list[MaterialNode] = []
        super().__init__(kind=kind, name=name, params=params, children=children)

    def add_material(
        self, material: MaterialNode, index: int | None = None
    ) -> MaterialNode:
        self.add_child(material, index=index)
        return material


class ObjectiveNode(Node):
    """Ordered objective and metric terms plus requested load Jacobians."""

    kind = KIND_OBJECTIVE
    label_key: ClassVar[str] = "ui.widgets.model_tree.container.objective"
    backend_class: ClassVar[str] = "ObjectiveFunction"
    _FIELDS = (
        "objective_terms",
        "metrics_terms",
        "jacobian_needed",
    )

    def __init__(
        self,
        kind: str | None = None,
        name: str = "Objective Function",
        params: dict | None = None,
        children: Sequence[Node] | None = None,
    ) -> None:
        super().__init__(kind=kind, name=name, children=children)
        data = dict(params or {})
        self.objective_terms: list[dict[str, Any]] = [
            dict(item) for item in data.get("objective_terms", ())
        ]
        self.metrics_terms: list[dict[str, Any]] = [
            dict(item) for item in data.get("metrics_terms", ())
        ]
        self.jacobian_needed: list[FEAComponentNode | str] = list(
            data.get("jacobian_needed") or []
        )

    def field_items(self) -> Iterator[tuple[str, object]]:
        """Serialize objective, metric, and Jacobian selections."""
        yield "objective_terms", self.objective_terms
        yield "metrics_terms", self.metrics_terms
        yield (
            "jacobian_needed",
            [
                item.name if isinstance(item, FEAComponentNode) else str(item)
                for item in self.jacobian_needed
            ],
        )


class SolverNode(Node):
    """FEA solver settings (process count, gpu devices, task partitioning).

    Canonical parameters are explicit, typed attributes assigned in
    ``__init__``.
    """

    kind = KIND_SOLVER
    label_key: ClassVar[str] = "ui.widgets.model_tree.container.solver"
    backend_class: ClassVar[str] = "Solver"
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "num_process",
            "ui.schema.fields.num_process.label.processes",
            "int",
            CONSTANT.KERNEL.SOLVER.NUM_PROCESS,
            doc_key="ui.schema.fields.num_process.help.number_of_fea_solver_processes",
            minimum=1,
        ),
        FieldSpec(
            "gpus",
            "ui.schema.fields.gpus.label.gpu_devices",
            "vecN",
            (),
            doc_key="ui.schema.fields.gpus.help.list_of_gpu_ids_e_g_cuda_0_or_empty_for_cpu",
        ),
        FieldSpec(
            "task_index_list",
            "ui.schema.fields.task_index_list.label.task_index_list",
            "vecN",
            (),
            doc_key="ui.schema.fields.task_index_list.help.partition_of_load_steps_over_processes_empty_auto",
        ),
    )

    def __init__(
        self,
        kind: str | None = None,
        name: str = "Solver",
        params: dict | None = None,
        children: Sequence[Node] | None = None,
    ) -> None:
        super().__init__(kind=kind, name=name, children=children)
        data = dict(params or {})
        # ---- explicit typed parameters ----------------------------------
        self.num_process: int | str = data.get(
            "num_process", CONSTANT.KERNEL.SOLVER.NUM_PROCESS
        )
        # CPU is represented by an empty GPU selection. Read older quickstart
        # definitions that explicitly stored ["cpu"] using the same convention.
        self.gpus: list = [
            device for device in (data.get("gpus") or []) if device != "cpu"
        ]
        self.task_index_list: list = list(data.get("task_index_list") or [])


class UpdaterNode(Node):
    """Optimisation sub-updater configuration (geometry / materials section).

    Each section is a list of config dicts, one for every updated target.
    Geometry configs keep an ordered ``symmetry_constraints`` list and a
    separate penalty ``constraints`` list; materials currently keep penalty
    ``constraints``.
    """

    kind = KIND_UPDATER
    label_key: ClassVar[str] = "ui.widgets.model_tree.container.updater"
    backend_class: ClassVar[str] = "Updaters"
    _FIELDS = ("geometry", "materials")

    def __init__(
        self,
        kind: str | None = None,
        name: str = "Updater",
        params: dict | None = None,
        children: Sequence[Node] | None = None,
    ) -> None:
        super().__init__(kind=kind, name=name, children=children)
        data = dict(params or {})
        self.geometry: list[dict] = list(data.get("geometry") or [])
        self.materials: list[dict] = list(data.get("materials") or [])
        if any("code" in config for config in self.geometry + self.materials):
            raise ValueError(
                localized_message(
                    "ui.errors.nodes.raw_updater_code_is_unsupported_use_method_overrides"
                )
            )

    def field_items(self) -> Iterator[tuple[str, object]]:
        """Serialize object targets without retaining name references in memory."""
        yield (
            "geometry",
            [self._serialize_config(config, "part_name") for config in self.geometry],
        )
        yield (
            "materials",
            [
                self._serialize_config(config, "material_name")
                for config in self.materials
            ],
        )

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
        from ..configuration import geometry_updater_config

        config = config if config is not None else geometry_updater_config()
        self.geometry.append(config)
        return config

    def add_materials_config(self, config: dict | None = None) -> dict:
        """Append one material sub-updater config and return it."""
        from ..configuration import materials_updater_config

        config = config if config is not None else materials_updater_config()
        self.materials.append(config)
        return config
