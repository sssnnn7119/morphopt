"""Build editable optimization definitions from design intent, independently of Qt."""
from __future__ import annotations
from copy import deepcopy
from ..i18n import localized_message

from ast import literal_eval
from dataclasses import asdict, dataclass, field
import math
from textwrap import dedent

from ...constants import CONSTANT
from ...optcore.quadrature import actuation_boundary_gauss_points
from ..model.chamberlayout import ChamberLayer, LayeredChambers
from ..model.problem import (
    CADOperationNode,
    GeometryNode, HelperFunctionNode, HelperVariableNode,
    FEAComponentNode, LoadsNode, MaterialNode, MaterialsNode,
    ObjectiveNode, PartNode, ProblemDefinition, SolverNode, StepsNode,
    SurfaceNode, UpdaterNode,
)

# key, localized label key, selected tip DOFs
GOALS = {
    "bend": ("ui.quickstart.goal.bend", (0,)),
    "extend": ("ui.quickstart.goal.extend", (2,)),
    "twist": ("ui.quickstart.goal.twist", (5,)),
    "workspace_plane": ("ui.quickstart.goal.workspace_plane", (0, 2)),
    "workspace_space": ("ui.quickstart.goal.workspace_space", (0, 1, 2)),
    "workspace_rotation": ("ui.quickstart.goal.workspace_rotation", (3, 4, 5)),
    "workspace_pose": ("ui.quickstart.goal.workspace_pose", (0, 2, 4)),
    "contact": ("ui.quickstart.goal.contact", (0,)),
    "stiffness": ("ui.quickstart.goal.stiffness", (2,)),
}


@dataclass
class QuickstartObjective:
    kind: str = "bend"
    weight: float = CONSTANT.UI.QUICKSTART.DEFAULT.OBJECTIVE_WEIGHT
    target: float = CONSTANT.UI.QUICKSTART.DEFAULT.OBJECTIVE_TARGET
    pressures_kpa: dict[int, float] = field(
        default_factory=lambda: dict(
            enumerate(CONSTANT.UI.QUICKSTART.DEFAULT.PRESSURES_KPA, start=1)
        )
    )
    workspace_channels: list[int] = field(
        default_factory=lambda: list(CONSTANT.UI.QUICKSTART.DEFAULT.WORKSPACE_CHANNELS)
    )
    workspace_pressure_kpa: float = CONSTANT.UI.QUICKSTART.DEFAULT.WORKSPACE_PRESSURE_KPA
    gauss_order: int = CONSTANT.UI.QUICKSTART.DEFAULT.GAUSS_ORDER
    force_n: float = CONSTANT.UI.QUICKSTART.DEFAULT.FORCE_N

    @property
    def is_workspace(self):
        return self.kind.startswith("workspace_")


@dataclass
class QuickstartOptions:
    method: str = "shapeopt"
    label: str = "Quickstart"
    result_folder: str = ".results/"
    length: float = CONSTANT.UI.QUICKSTART.DEFAULT.LENGTH
    radius: float = CONSTANT.UI.QUICKSTART.DEFAULT.BODY_RADIUS
    layers: list[ChamberLayer] = field(default_factory=lambda: [ChamberLayer()])
    wall: float = CONSTANT.UI.QUICKSTART.DEFAULT.WALL
    objectives: list[QuickstartObjective] = field(default_factory=lambda: [QuickstartObjective()])
    mesh_size: float = CONSTANT.UI.QUICKSTART.DEFAULT.MESH_SIZE
    mu: float = CONSTANT.UI.QUICKSTART.DEFAULT.MATERIAL_MU
    kappa: float = CONSTANT.UI.QUICKSTART.DEFAULT.MATERIAL_KAPPA
    optimize_outer: bool = True
    height: float = CONSTANT.UI.QUICKSTART.DEFAULT.BOX_HEIGHT
    depth: float = CONSTANT.UI.QUICKSTART.DEFAULT.BOX_DEPTH
    volume_fraction: float = CONSTANT.UI.QUICKSTART.DEFAULT.VOLUME_FRACTION

    @property
    def total_length(self):
        return sum(layer.length for layer in self.layers) if self.method == "shapeopt" else self.length

    @property
    def chambers(self):
        return sum(layer.chambers for layer in self.layers)

    @property
    def channel_ids(self):
        return sorted({channel for layer in self.layers for channel in layer.pressure_channels})

    @property
    def channel_members(self):
        members = {}
        chamber_index = 1
        for layer in self.layers:
            for channel in layer.pressure_channels:
                members.setdefault(channel, []).append(chamber_index)
                chamber_index += 1
        return members

    @classmethod
    def for_method(cls, method):
        if method == "simp":
            return cls(
                method="simp",
                length=CONSTANT.UI.QUICKSTART.DEFAULT.SIMP_LENGTH,
                mu=CONSTANT.UI.QUICKSTART.DEFAULT.SIMP_MU,
                kappa=CONSTANT.UI.QUICKSTART.DEFAULT.SIMP_KAPPA,
                objectives=[QuickstartObjective(kind="stiffness")],
            )
        return cls()

    @classmethod
    def from_problem(cls, problem):
        for variable in problem.helper_variables:
            if variable.name == "quickstart_settings":
                data = literal_eval(variable.value)
                data["layers"] = [ChamberLayer(**layer) for layer in data["layers"]]
                data["objectives"] = [
                    QuickstartObjective(**objective)
                    for objective in data["objectives"]
                ]
                return cls(**data)
        return cls.for_method(problem.scheme)

    def geometry_layout(self):
        return LayeredChambers(self.layers, self.radius, self.wall)

    def validate(self):
        if self.method not in ("shapeopt", "simp"):
            raise ValueError(localized_message("ui.errors.quickstart.select_an_optimization_method"))
        if not self.label.strip() or not self.result_folder.strip():
            raise ValueError(localized_message("ui.errors.quickstart.enter_a_name_and_output_folder"))
        if not CONSTANT.UI.QUICKSTART.LIMITS.OBJECTIVE_MIN_COUNT <= len(self.objectives) <= CONSTANT.UI.QUICKSTART.LIMITS.OBJECTIVE_MAX_COUNT:
            raise ValueError(
                localized_message(
                    "ui.errors.quickstart.add_1_8_objective_terms",
                    value_0=CONSTANT.UI.QUICKSTART.LIMITS.OBJECTIVE_MIN_COUNT,
                    value_1=CONSTANT.UI.QUICKSTART.LIMITS.OBJECTIVE_MAX_COUNT,
                )
            )
        if any(not math.isfinite(obj.weight) or obj.weight < 0 for obj in self.objectives):
            raise ValueError(localized_message("ui.errors.quickstart.objective_weights_must_be_finite_and_nonnegative"))
        if sum(obj.weight for obj in self.objectives) <= 0:
            raise ValueError(localized_message("ui.errors.quickstart.at_least_one_objective_weight_must_be_positive"))
        allowed = (set(GOALS) - {"stiffness"}) if self.method == "shapeopt" else {"stiffness", "bend"}
        for objective in self.objectives:
            if objective.kind not in allowed:
                raise ValueError(localized_message("ui.errors.quickstart.objective_value_is_unavailable_for_this_method", value_0=objective.kind))
            if not math.isfinite(objective.weight) or objective.weight < 0:
                raise ValueError(localized_message("ui.errors.quickstart.objective_weights_must_be_finite_and_nonnegative"))
            if (not objective.is_workspace and objective.kind != "stiffness"
                    and (not math.isfinite(objective.target) or objective.target <= 0)):
                raise ValueError(localized_message("ui.errors.quickstart.target_values_must_be_positive"))

        for name in ("length", "mesh_size", "mu", "kappa", "height", "depth"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(localized_message("ui.errors.quickstart.value_must_be_positive", value_0=name))
        if not 0 < self.volume_fraction < 1:
            raise ValueError(localized_message("ui.errors.quickstart.material_fraction_must_be_between_0_and_1"))
        if self.method == "simp":
            cells = math.ceil(self.length/self.mesh_size)*math.ceil(self.height/self.mesh_size)*math.ceil(self.depth/self.mesh_size)
            if cells > CONSTANT.UI.QUICKSTART.LIMITS.SIMP_MAX_ELEMENT_COUNT:
                raise ValueError(localized_message("ui.errors.quickstart.increase_the_mesh_size"))
            for objective in self.objectives:
                if not math.isfinite(objective.force_n) or objective.force_n <= 0:
                    raise ValueError(localized_message("ui.errors.quickstart.topology_load_magnitudes_must_be_positive"))
            return

        if not math.isfinite(self.radius) or self.radius <= 0 or not math.isfinite(self.wall) or self.wall <= 0:
            raise ValueError(localized_message("ui.errors.quickstart.body_radius_and_wall_thickness_must_be_positive"))
        self.geometry_layout()
        for objective in self.objectives:
            if objective.is_workspace:
                dimensions = len(GOALS[objective.kind][1])
                selected = objective.workspace_channels
                if not math.isfinite(objective.workspace_pressure_kpa) or objective.workspace_pressure_kpa <= 0:
                    raise ValueError(localized_message("ui.errors.quickstart.workspace_pressure_limits_must_be_positive"))
                if not isinstance(objective.gauss_order, int) or not (
                    CONSTANT.UI.QUICKSTART.LIMITS.WORKSPACE_GAUSS_ORDER_MIN
                    <= objective.gauss_order
                    <= CONSTANT.UI.QUICKSTART.LIMITS.WORKSPACE_GAUSS_ORDER_MAX
                ):
                    raise ValueError(
                        localized_message(
                            "ui.errors.quickstart.select_1_8_gaussian_points_per_free_boundary_coordinate",
                            value_0=CONSTANT.UI.QUICKSTART.LIMITS.WORKSPACE_GAUSS_ORDER_MIN,
                            value_1=CONSTANT.UI.QUICKSTART.LIMITS.WORKSPACE_GAUSS_ORDER_MAX,
                        )
                    )
                if len(self.channel_ids) < dimensions:
                    raise ValueError(
                        localized_message("ui.errors.quickstart.this_workspace_needs_value_independent_inputs_but_the_design_has", value_0=dimensions, value_1=len(self.channel_ids))
                    )
                if (len(selected) != dimensions or len(set(selected)) != dimensions
                        or not set(selected).issubset(self.channel_ids)):
                    raise ValueError(
                        localized_message("ui.errors.quickstart.select_value_valid_distinct_pressure_channels_chambers_on_one_channel", value_0=dimensions)
                    )
            else:
                for channel, pressure in objective.pressures_kpa.items():
                    if channel not in self.channel_ids:
                        raise ValueError(localized_message("ui.errors.quickstart.load_case_references_unknown_channel_value", value_0=channel))
                    if not math.isfinite(pressure) or pressure < 0:
                        raise ValueError(localized_message("ui.errors.quickstart.load_pressures_must_be_finite_and_nonnegative"))


def _function(problem, name, parameters, body):
    problem.helper_functions.append(
        HelperFunctionNode(name=name, params={"parameters": parameters, "body": dedent(body).strip()+"\n"})
    )


def build_quickstart(options: QuickstartOptions) -> ProblemDefinition:
    options.validate()
    problem = ProblemDefinition(
        scheme=options.method, label=options.label.strip(), result_folder=options.result_folder.strip()
    )
    problem.helper_code = "import torch\n"
    problem.helper_variables.extend([
        HelperVariableNode(name="quickstart_settings", params={"value": repr(asdict(options))}),
        HelperVariableNode(name="design_length", params={"value": repr(options.total_length)}),
    ])
    geometry, loads, materials = GeometryNode(name="Geometry"), LoadsNode(name="Loads"), MaterialsNode(name="Materials")
    problem.root.add_section(geometry)
    problem.root.add_section(loads)
    _function(problem, "tip_motion", "objective, step", '''
        objective.set_step(step)
        assembly = objective.fe.assembly
        state = assembly._GC2RGC(objective.fe_results[step].GC.to(assembly.device))
        return state[assembly.get_reference_point("RP_tip")._RGC_index].reshape(-1)
    ''')
    if options.method == "shapeopt":
        step_values, objective_terms, metrics_code, jacobians, updater = _shape(
            problem, options, geometry, loads, materials
        )
    else:
        step_values, objective_terms, metrics_code, jacobians, updater = _topology(
            options, geometry, loads, materials
        )
    problem.root.add_section(StepsNode(
        name="Load steps",
        params={"step_values": step_values},
    ))
    problem.root.add_section(materials)
    problem.root.add_section(ObjectiveNode(name="Objective Function", params={
        "objective_terms": objective_terms,
        "metrics_terms": [{
            "type": CONSTANT.UI.METRIC.TYPE_CUSTOM,
            "body": metrics_code,
        }],
        "jacobian_needed": jacobians,
    }))
    problem.root.add_section(SolverNode(name="Solver", params={
        "num_process": CONSTANT.UI.QUICKSTART.DEFAULT.NUM_PROCESS,
        "gpus": [],
        "task_step_list": [],
    }))
    problem.root.add_section(updater)
    problem.resolve_references()
    problem.align_surface_dependent_state()
    from .load_cases import synchronize_workspaces
    import hashlib
    import json
    from uuid import uuid4
    for term in problem.objective.objective_terms:
        if term.get("type") == "workspace":
            term["id"] = uuid4().hex
            term["case_signature"] = hashlib.sha256(json.dumps([term["inputs"], term["gauss_order"]], sort_keys=True).encode()).hexdigest()
            for name in term["case_names"]:
                problem.steps.generated_by[name] = term["id"]
    synchronize_workspaces(problem)
    return problem


def _common_loads(loads, length, fixed="surface_0_Bottom", tip="surface_0_Head", location=None):
    loads.add_component(FEAComponentNode.create(
        "BoundaryCondition",
        name="base_fixed",
        instance_name="body-1",
        set_nodes_name=fixed,
        index_dof=[0, 1, 2],
    ))
    loads.add_component(FEAComponentNode.create(
        "ReferencePoint",
        name="RP_tip",
        rp_location=location or [0., 0., length],
    ))
    loads.add_component(FEAComponentNode.create(
        "Couple",
        name="tip_coupling",
        instance_name="body-1",
        set_nodes_name=tip,
        rp_name="RP_tip",
    ))


def _shape_geometry(options, geometry, loads, materials):
    part = PartNode.create(
        "BoundaryPart", name="body",
        fea_seed_size=options.mesh_size, mesh_order=2,
    )
    geometry.add_part(part)
    seed = min(
        min(layer.radius for layer in options.layers)
        / CONSTANT.UI.QUICKSTART.GENERATION.SHAPE_SEED_RADIUS_DIVISOR,
        options.total_length / CONSTANT.UI.QUICKSTART.GENERATION.SHAPE_SEED_LENGTH_DIVISOR,
    )
    part.add_surface(SurfaceNode.create(
        "bsp_cylinder", r0=options.radius, length=options.total_length,
        seed_size=seed, perturbation_L=-1., is_updatable=options.optimize_outer,
    ))
    cavities = options.geometry_layout().cavity_specs()
    for index, cavity in enumerate(cavities, 1):
        if cavity.shape == "sphere":
            surface = SurfaceNode.create(
                "cpgeo_sphere", index=index, r0=cavity.radius, seed_size=seed,
                init_location=[cavity.x, cavity.y, cavity.z+cavity.length/2],
            )
        else:
            surface = SurfaceNode.create(
                "bsp_cylinder", index=index, r0=cavity.radius, length=cavity.length,
                seed_size=seed, init_location=[cavity.x, cavity.y, cavity.z], perturbation_L=-1.,
            )
        surface.is_updatable = True
        part.add_surface(surface)
        loads.add_component(FEAComponentNode.create(
            "Pressure", name=f"pressure_{index}", instance_name="body-1",
            surface_name=f"surface_{index}_All",
        ))
    _common_loads(loads, options.total_length)
    materials.add_material(MaterialNode.create(
        "HomogeneousMaterial", name="body_material", part_name="body",
        material_model="NeoHookeanLnJ", mu=options.mu, kappa=options.kappa,
    ))
    count = options.chambers+1
    constraints = [
        {"type": "Fairness", "params": {}},
        {"type": "Distance", "params": {"min_distance": [[options.wall]*count for _ in range(count)]}},
        {"type": "Cylinder", "params": {"radius": options.radius, "height": options.total_length, "bottom": 0.}},
    ]
    updater = UpdaterNode(name="Updater", params={
        "geometry": [{
            "part_name": "body",
            "max_step_iter": CONSTANT.UI.QUICKSTART.DEFAULT.GEOMETRY_MAX_STEP_ITERATIONS,
            "objective_functions": [{"type": "ShapeDerivative", "params": {}}],
            "constraints": constraints,
        }],
        "materials": [],
    })
    return cavities, updater


def _shape(p, options, geometry, loads, materials):
    cavities, updater = _shape_geometry(options, geometry, loads, materials)
    pressure_names = [f"pressure_{index}" for index in range(1, options.chambers+1)]
    if any(objective.kind == "contact" for objective in options.objectives):
        _contact_setup(p, options, geometry, loads, materials)

    step_values = {}
    step_indices = {}

    def add_pressure_case(channel_values):
        amplitudes = {
            name: [float(channel_values.get(cavity.pressure_channel, 0.0))]
            for name, cavity in zip(pressure_names, cavities)
        }
        signature = tuple(amplitudes[name][0] for name in pressure_names)
        if signature not in step_indices:
            step_indices[signature] = f"load_case_{len(step_values) + 1}"
            step_values[step_indices[signature]] = amplitudes
        return step_indices[signature]

    objective_records, jacobian_names = [], []
    for index, objective in enumerate(options.objectives):
        if objective.is_workspace:
            active_channels = list(objective.workspace_channels)
            dimensions = len(active_channels)
            span = objective.workspace_pressure_kpa/1000
            points, weights, tangents, orientations = actuation_boundary_gauss_points(
                [(0., span)]*dimensions, objective.gauss_order
            )
            workspace_steps = []
            for point_index, point in enumerate(points, 1):
                channel_values = {channel: float(point[axis]) for axis, channel in enumerate(active_channels)}
                name = f"workspace_{index + 1}_case_{point_index}"
                step_values[name] = {
                    load: [float(channel_values.get(cavity.pressure_channel, 0.0))]
                    for load, cavity in zip(pressure_names, cavities)
                }
                workspace_steps.append(name)
            groups = [
                [name for name, cavity in zip(pressure_names, cavities) if cavity.pressure_channel == channel]
                for channel in active_channels
            ]
            for group in groups:
                jacobian_names.extend(group)
            inputs = [{"parameters": [[name, 0] for name in group], "upper": span} for group in groups]
            arguments = {
                "reference_point_name": "RP_tip", "axes": list(GOALS[objective.kind][1]),
                "inputs": inputs, "case_names": workspace_steps, "weights": weights.tolist(),
                "tangents": tangents.tolist(), "orientations": orientations.tolist(),
            }
            scale = options.total_length**sum(axis < 3 for axis in GOALS[objective.kind][1])
            measure = "self.workspace_measure(" + ", ".join(f"{key}={value!r}" for key, value in arguments.items()) + ")"
            objective_records.append({
                "objective": objective,
                "workspace_measure": measure,
                "case_names": workspace_steps,
                "inputs": [{"parameters": [[name, 0] for name in group], "upper": span} for group in groups],
                "scale": scale,
                "step": None,
            })
            # Metrics are evaluated separately from objective_function.
            objective_records[-1]["metric"] = measure
            continue

        channel_values = {
            channel: float(objective.pressures_kpa.get(channel, 0.0))/1000
            for channel in options.channel_ids
        }
        step = add_pressure_case(channel_values)
        objective_records.append({"objective": objective, "step": step})

    objective_terms, metrics = [], []
    for index, record in enumerate(objective_records):
        objective = record["objective"]
        if objective.is_workspace:
            measure = record["workspace_measure"]
            metrics.append(record["metric"])
            objective_terms.append({
                "type": "workspace", "kind": objective.kind,
                "reference_point_name": "RP_tip", "gauss_order": objective.gauss_order,
                "inputs": record["inputs"], "case_names": record["case_names"],
                "normalization": record["scale"], "weight": objective.weight,
            })
        else:
            step = record["step"]
            motion_name = f"motion_{index}"
            _loss, metric = _shape_objective_expression(
                objective, index, options, motion_name, step
            )
            metrics.append(metric.replace(motion_name, f"tip_motion(self, {step!r})"))
            target = objective.target
            if objective.kind == "bend":
                target = math.radians(target)
                objective_terms.append(_quickstart_displacement_term(
                    step, "ux", target, objective.weight / target**2
                ))
            elif objective.kind == "extend":
                scale = target**2
                for component in ("ux", "uy"):
                    objective_terms.append(_quickstart_displacement_term(
                        step, component, 0.0, objective.weight / scale
                    ))
                objective_terms.append(_quickstart_displacement_term(
                    step, "uz", target, objective.weight / scale
                ))
            elif objective.kind == "twist":
                target = math.radians(target)
                objective_terms.append(_quickstart_displacement_term(
                    step, "rz", target, objective.weight / target**2
                ))
            elif objective.kind == "contact":
                objective_terms.append({
                    "type": CONSTANT.UI.OBJECTIVE.TYPE_CUSTOM_LOSS,
                    "body": (
                        f"return (contact_force(self, {step!r}) "
                        f"- {objective.target!r}) ** 2"
                    ),
                    "weight": objective.weight / objective.target**2,
                })
                reach = 4 * options.wall
                objective_terms.append(_quickstart_displacement_term(
                    step, "ux", reach,
                    0.1 * objective.weight / reach**2,
                ))
    metrics_code = "return ["+", ".join(metrics)+"]\n"
    return step_values, objective_terms, metrics_code, list(dict.fromkeys(jacobian_names)), updater


def _quickstart_displacement_term(step: int, component: str, target: float, weight: float):
    return {
        "type": CONSTANT.UI.OBJECTIVE.TYPE_DISPLACEMENT,
        "step_name": step,
        "reference_point_name": "RP_tip",
        "component": component,
        "direction": CONSTANT.UI.OBJECTIVE.DEFAULT_DIRECTION,
        "target": target,
        "weight": weight,
    }


def _shape_objective_expression(objective, index, options, motion, step):
    target = math.radians(objective.target) if objective.kind == "twist" else objective.target
    if objective.kind == "bend":
        loss = f"loss_{index} = (({motion}[0]-{target!r})/{target!r}).square()"
        metric = f"{motion}[0]"
    elif objective.kind == "extend":
        loss = (
            f"loss_{index} = (({motion}[2]-{target!r})/{target!r}).square()"
            f" + ({motion}[:2]/{target!r}).square().sum()"
        )
        metric = f"{motion}[2]"
    elif objective.kind == "twist":
        loss = f"loss_{index} = (({motion}[5]-{target!r})/{target!r}).square()"
        metric = f"{motion}[5]"
    elif objective.kind == "contact":
        reach = 4*options.wall
        loss = (
            f"loss_{index} = ((contact_force(self, {step!r})-{objective.target!r})/{objective.target!r}).square()"
            f" + 0.1*(({motion}[0]-{reach!r})/{reach!r}).square()"
        )
        metric = f"contact_force(self, {step!r})"
    else:
        raise ValueError(localized_message("ui.errors.quickstart.unsupported_shape_objective_value", value_0=objective.kind))
    return loss, metric


def _contact_setup(problem, options, geometry, loads, materials):
    object_part = PartNode.create(
        "CADPart", name="object", exterior_surface="extern",
        mesh_size=options.mesh_size,
    )
    object_part.add_cad_operation(
        CADOperationNode.create(
            "Cylinder",
            "object-cylinder",
            x=2 * options.radius + options.wall,
            y=-options.radius,
            z=(
                CONSTANT.UI.QUICKSTART.GENERATION.CONTACT_OBJECT_Z_FRACTION
                * options.total_length
            ),
            dy=2 * options.radius,
            radius=options.radius,
        )
    )
    geometry.add_part(object_part)
    loads.add_component(FEAComponentNode.create(
        "BoundaryCondition", name="object_fixed", instance_name="object-1",
        set_nodes_name="all", index_dof=[0, 1, 2],
    ))
    loads.add_component(FEAComponentNode.create(
        "Contact", name="object_contact", instance_name1="body-1", surface_name1="surface_0_All",
        instance_name2="object-1", surface_name2="extern",
        penalty_threshold_h=min(
            options.wall
            / CONSTANT.UI.QUICKSTART.GENERATION.CONTACT_WALL_THRESHOLD_DIVISOR,
            options.mesh_size,
        ),
    ))
    materials.add_material(MaterialNode.create(
        "HomogeneousMaterial", name="object_material", part_name="object",
        material_model="NeoHookeanLnJ", mu=options.mu, kappa=options.kappa,
    ))
    _function(problem, "contact_force", "objective, step", '''
        objective.set_step(step)
        assembly = objective.fe.assembly
        force = assembly._assemble_generalized_Matrix(GC=objective.fe_results[step].GC.to(assembly.device))[0]
        instance = assembly.get_instance("object-1")
        start = assembly._RGC_list_indexStart[instance._RGC_index]
        end = assembly._RGC_list_indexStart[instance._RGC_index+1]
        return force[start:end].reshape(-1, 3)[:, 0].sum().abs()
    ''')


def _topology(options, geometry, loads, materials):
    part = PartNode.create(
        "BoxPart", name="body", exterior_surface="extern",
        length=options.total_length, height=options.height, depth=options.depth,
        mesh_size=options.mesh_size, mesh_order=2,
    )
    geometry.add_part(part)
    _common_loads(loads, options.total_length, fixed="nodes_xmin", tip="nodes_xmax",
                  location=[options.total_length, options.height/2, options.depth/2])
    loads.add_component(FEAComponentNode.create("ConcentratedForce", name="tip_force", rp_name="RP_tip"))
    materials.add_material(MaterialNode.create(
        "SIMP_BSPFieldMaterials", name="density", part_name="body",
        elementname="design", material_model="NeoHookeanLnJ", mu=options.mu,
        kappa=options.kappa, mumax=options.mu, kappamax=options.kappa,
        bounding_box=[0., options.total_length, 0., options.height, 0., options.depth],
        degree=CONSTANT.UI.QUICKSTART.GENERATION.SIMP_DEGREE,
        simp_field_resolution=min(
            options.mesh_size,
            min(options.total_length, options.height, options.depth)
            / CONSTANT.UI.QUICKSTART.GENERATION.SIMP_FIELD_RESOLUTION_DIVISOR,
        ),
        initial_ratio=math.log(options.volume_fraction/(1-options.volume_fraction)),
        voidpenalfactor=CONSTANT.KERNEL.SIMP.DEFAULT_VOID_PENALTY_FACTOR,
    ))
    updater = UpdaterNode(name="Updater", params={
        "geometry": [],
        "materials": [{
            "material_name": "density",
            "max_step_iter": CONSTANT.KERNEL.SIMP_UPDATE.MAX_STEP_ITERATIONS,
            "if_update": True,
            "objective_functions": [{"type": "Sensitivity", "params": {"normalize_gradient": False}}],
            "constraints": [
                {"type": "MinValue", "params": {"xmin": CONSTANT.UI.QUICKSTART.GENERATION.SIMP_VARIABLE_BOUNDS[0]}},
                {"type": "MaxValue", "params": {"xmax": CONSTANT.UI.QUICKSTART.GENERATION.SIMP_VARIABLE_BOUNDS[1]}},
                {"type": "VolFrac", "params": {
                    "volfrac_min": options.volume_fraction, "volfrac_max": options.volume_fraction,
                    "penalty": CONSTANT.UI.QUICKSTART.GENERATION.SIMP_VOLUME_FRACTION_PENALTY,
                    "elementname": "design",
                }},
            ],
        }],
    })
    steps, signatures = {}, {}
    objective_steps = []
    for objective in options.objectives:
        signature = float(objective.force_n)
        if signature not in signatures:
            signatures[signature] = f"load_case_{len(steps) + 1}"
            steps[signatures[signature]] = {"tip_force": [0., 0., -signature]}
        objective_steps.append(signatures[signature])
    objective_terms, metrics = [], []
    for objective, step in zip(options.objectives, objective_steps):
        metrics.append(f"tip_motion(self, {step!r})[2]")
        if objective.kind == "stiffness":
            body = (
                f"motion = tip_motion(self, {step!r})\n"
                f"return -motion[2]/{options.total_length!r}"
            )
            objective_terms.append({
                "type": CONSTANT.UI.OBJECTIVE.TYPE_CUSTOM_LOSS,
                "body": body,
                "weight": objective.weight,
            })
        else:
            objective_terms.append(_quickstart_displacement_term(
                step, "uz", -objective.target,
                objective.weight / objective.target**2,
            ))
    metrics_code = "return ["+", ".join(metrics)+"]\n"
    return steps, objective_terms, metrics_code, [], updater


def available_objectives(method: str) -> list[str]:
    return sorted(set(GOALS) - {"stiffness"}) if method == "shapeopt" else ["stiffness", "bend"]


def select_workspace_channels(members, selected, required: int) -> list[int]:
    chosen = [channel for channel in selected if channel in members][:required]
    for channel in sorted(members):
        if len(chosen) >= required:
            break
        if channel not in chosen:
            chosen.append(channel)
    return chosen


class ObjectiveDraft:
    """Editable Quickstart terms, with one policy for method/channel changes."""
    def __init__(self, objectives, method: str, members):
        self.method = method
        self.members = {key: list(value) for key, value in members.items()}
        self.objectives = [self.copy(item) for item in objectives]

    @staticmethod
    def copy(objective) -> QuickstartObjective:
        from dataclasses import replace
        item = QuickstartObjective(**objective) if isinstance(objective, dict) else objective
        return replace(
            item,
            pressures_kpa=dict(item.pressures_kpa),
            workspace_channels=list(item.workspace_channels),
        )

    def add(self) -> int:
        if len(self.objectives) >= CONSTANT.UI.QUICKSTART.LIMITS.OBJECTIVE_MAX_COUNT:
            raise ValueError(
                localized_message(
                    "ui.errors.quickstart.quickstart_supports_at_most_eight_objective_terms",
                    value_0=CONSTANT.UI.QUICKSTART.LIMITS.OBJECTIVE_MAX_COUNT,
                )
            )
        channels = sorted(self.members)
        configured_pressures = dict(
            enumerate(CONSTANT.UI.QUICKSTART.DEFAULT.PRESSURES_KPA, start=1)
        )
        self.objectives.append(QuickstartObjective(
            kind="bend" if self.method == "shapeopt" else "stiffness",
            pressures_kpa={
                channel: configured_pressures.get(channel, 0.0)
                for channel in channels
            },
            workspace_channels=channels[:2],
        ))
        return len(self.objectives) - 1

    def remove(self, index: int) -> None:
        if len(self.objectives) <= CONSTANT.UI.QUICKSTART.LIMITS.OBJECTIVE_MIN_COUNT:
            raise ValueError(localized_message("ui.errors.quickstart.keep_at_least_one_objective_term"))
        self.objectives.pop(index)

    def set_method(self, method: str) -> None:
        self.method = method
        allowed = available_objectives(method)
        for objective in self.objectives:
            if objective.kind not in allowed:
                objective.kind = "bend" if method == "shapeopt" else "stiffness"

    def set_channels(self, members) -> None:
        self.members = {key: list(value) for key, value in members.items()}
        for objective in self.objectives:
            objective.pressures_kpa = {channel: objective.pressures_kpa.get(
                channel,
                0.,
            ) for channel in sorted(members)}
            if objective.is_workspace:
                objective.workspace_channels = select_workspace_channels(
                    members,
                    objective.workspace_channels,
                    len(GOALS[objective.kind][1]),
                )

    def values(self) -> list[QuickstartObjective]:
        return [self.copy(objective) for objective in self.objectives]
