"""Build editable optimization definitions from design intent, independently of Qt."""
from __future__ import annotations
from ..i18n import localized_message

from ast import literal_eval
from dataclasses import asdict, dataclass, field
import math
from textwrap import dedent

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
    weight: float = 1.0
    target: float = 20.0
    pressures_kpa: dict[int, float] = field(default_factory=lambda: {1: 60.0, 2: 0.0})
    workspace_channels: list[int] = field(default_factory=lambda: [1, 2])
    workspace_pressure_kpa: float = 60.0
    gauss_order: int = 3
    force_n: float = 1.0

    @property
    def is_workspace(self):
        return self.kind.startswith("workspace_")


@dataclass
class QuickstartOptions:
    method: str = "shapeopt"
    label: str = "Quickstart"
    result_folder: str = ".results/"
    length: float = 80.0
    radius: float = 10.0
    layers: list[ChamberLayer] = field(default_factory=lambda: [ChamberLayer()])
    wall: float = 2.0
    objectives: list[QuickstartObjective] = field(default_factory=lambda: [QuickstartObjective()])
    mesh_size: float = 2.0
    mu: float = 0.482
    kappa: float = 4.8
    optimize_outer: bool = True
    height: float = 16.0
    depth: float = 8.0
    volume_fraction: float = 0.4

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
                method="simp", length=40.0, mu=10.0, kappa=100.0,
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
        if not 1 <= len(self.objectives) <= 8:
            raise ValueError(localized_message("ui.errors.quickstart.add_1_8_objective_terms"))
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
            if cells > 100000:
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
                if not isinstance(objective.gauss_order, int) or not 1 <= objective.gauss_order <= 8:
                    raise ValueError(localized_message("ui.errors.quickstart.select_1_8_gaussian_points_per_free_boundary_coordinate"))
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
        step_values, objective_code, metrics_code, jacobians, updater = _shape(
            problem, options, geometry, loads, materials
        )
    else:
        step_values, objective_code, metrics_code, jacobians, updater = _topology(
            options, geometry, loads, materials
        )
    problem.root.add_section(StepsNode(
        name="Load steps",
        params={"num_steps": len(step_values), "step_values": step_values},
    ))
    problem.root.add_section(materials)
    problem.root.add_section(ObjectiveNode(name="Objective Function", params={
        "_objective_function": objective_code,
        "_get_metrics": metrics_code,
        "jacobian_needed": jacobians,
    }))
    problem.root.add_section(SolverNode(name="Solver", params={
        "num_process": 1,
        "gpus": ["cpu"],
        "task_index_list": [list(range(len(step_values)))],
    }))
    problem.root.add_section(updater)
    problem.resolve_references()
    problem.align_surface_dependent_state()
    return problem


def _common_loads(loads, length, fixed="surface_0_Bottom", tip="surface_0_Head", location=None):
    loads.add_interface(FEAComponentNode.create(
        "BoundaryCondition",
        name="base_fixed",
        instance_name="body-1",
        set_nodes_name=fixed,
        index_dof=[0, 1, 2],
    ))
    loads.add_interface(FEAComponentNode.create(
        "ReferencePoint",
        name="RP_tip",
        rp_location=location or [0., 0., length],
    ))
    loads.add_interface(FEAComponentNode.create(
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
    geometry.add_interface(part)
    seed = min(min(layer.radius for layer in options.layers)/2, options.total_length/12)
    part.add_surface(SurfaceNode.create(
        "bsp_cylinder", r0=options.radius, length=options.total_length,
        seed_size=seed, perturbation_L=-1.,
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
        part.add_surface(surface)
        loads.add_interface(FEAComponentNode.create(
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
            "part_name": "body", "max_step_iter": 50,
            "if_update": [options.optimize_outer]+[True]*options.chambers,
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

    step_values = []
    step_indices = {}

    def add_pressure_case(channel_values):
        amplitudes = {
            name: [float(channel_values.get(cavity.pressure_channel, 0.0))]
            for name, cavity in zip(pressure_names, cavities)
        }
        signature = tuple(amplitudes[name][0] for name in pressure_names)
        if signature not in step_indices:
            step_indices[signature] = len(step_values)
            step_values.append(amplitudes)
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
            for point in points:
                channel_values = {channel: float(point[axis]) for axis, channel in enumerate(active_channels)}
                workspace_steps.append(add_pressure_case(channel_values))
            groups = [
                [name for name, cavity in zip(pressure_names, cavities) if cavity.pressure_channel == channel]
                for channel in active_channels
            ]
            for group in groups:
                jacobian_names.extend(group)
            names = {
                "weights": f"workspace_{index}_weights",
                "axes": f"workspace_{index}_axes",
                "channels": f"workspace_{index}_channels",
                "tangents": f"workspace_{index}_tangents",
                "orientations": f"workspace_{index}_orientations",
            }
            for key, value in (
                ("weights", weights.tolist()),
                ("axes", list(GOALS[objective.kind][1])),
                ("channels", groups),
                ("tangents", tangents.tolist()),
                ("orientations", orientations.tolist()),
            ):
                p.helper_variables.append(HelperVariableNode(name=names[key], params={"value": repr(value)}))
            function_name = f"workspace_measure_{index}"
            _workspace_function(p, function_name, names)
            scale = options.total_length**sum(axis < 3 for axis in GOALS[objective.kind][1])
            measure = f"{function_name}(self, {workspace_steps!r})"
            objective_records.append({
                "objective": objective,
                "workspace_measure": measure,
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

    objective_lines, weighted, metrics = [], [], []
    for index, record in enumerate(objective_records):
        objective = record["objective"]
        if objective.is_workspace:
            measure = record["workspace_measure"]
            objective_lines.append(f"workspace_value_{index} = {measure}")
            objective_lines.append(f"loss_{index} = -workspace_value_{index}/{record['scale']!r}")
            metrics.append(record["metric"])
        else:
            motion_name = f"motion_{index}"
            step = record["step"]
            objective_lines.append(f"{motion_name} = tip_motion(self, {step})")
            loss, metric = _shape_objective_expression(objective, index, options, motion_name, step)
            objective_lines.append(loss)
            metrics.append(metric.replace(motion_name, f"tip_motion(self, {step})"))
        weighted.append(f"({objective.weight!r})*loss_{index}")
    objective_code = "\n".join(objective_lines+["return "+" + ".join(weighted)])+"\n"
    metrics_code = "return ["+", ".join(metrics)+"]\n"
    return step_values, objective_code, metrics_code, list(dict.fromkeys(jacobian_names)), updater


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
            f"loss_{index} = ((contact_force(self, {step})-{objective.target!r})/{objective.target!r}).square()"
            f" + 0.1*(({motion}[0]-{reach!r})/{reach!r}).square()"
        )
        metric = f"contact_force(self, {step})"
    else:
        raise ValueError(localized_message("ui.errors.quickstart.unsupported_shape_objective_value", value_0=objective.kind))
    return loss, metric


def _workspace_function(problem, function_name, names):
    _function(problem, function_name, "objective, step_indices", f'''
        assembly = objective.fe.assembly
        rp = assembly.get_reference_point("RP_tip")
        start = assembly._GC_list_indexStart[rp._RGC_index]
        volume = None
        for local, step in enumerate(step_indices):
            result = objective.fe_results[step]
            motion = tip_motion(objective, step)[{names["axes"]}]
            derivatives = [
                sum(result.jacobian[name][start:start+6, 0].to(motion.device) for name in channel)[{names["axes"]}]
                for channel in {names["channels"]}
            ]
            tangent_a, tangent_b = {names["tangents"]}[local]
            if len({names["axes"]}) == 2:
                tangent = derivatives[tangent_a]
                integrand = motion[1]*tangent[0] - motion[0]*tangent[1]
            else:
                jacobian_a = derivatives[tangent_a]
                jacobian_b = derivatives[tangent_b]
                integrand = torch.dot(motion, torch.linalg.cross(jacobian_a, jacobian_b))
            if volume is None:
                volume = motion.sum()*0
            volume = volume + {names["weights"]}[local]*{names["orientations"]}[local]*integrand
        if len({names["axes"]}) == 2:
            return volume.abs()/2
        factor = 1/24 if {names["axes"]} == [3, 4, 5] else 1/3
        return volume.abs()*factor
    ''')


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
            z=0.7 * options.total_length,
            dy=2 * options.radius,
            radius=options.radius,
        )
    )
    geometry.add_interface(object_part)
    loads.add_interface(FEAComponentNode.create(
        "BoundaryCondition", name="object_fixed", instance_name="object-1",
        set_nodes_name="all", index_dof=[0, 1, 2],
    ))
    loads.add_interface(FEAComponentNode.create(
        "Contact", name="object_contact", instance_name1="body-1", surface_name1="surface_0_All",
        instance_name2="object-1", surface_name2="extern",
        penalty_threshold_h=min(options.wall/2, options.mesh_size),
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
    geometry.add_interface(part)
    _common_loads(loads, options.total_length, fixed="nodes_xmin", tip="nodes_xmax",
                  location=[options.total_length, options.height/2, options.depth/2])
    loads.add_interface(FEAComponentNode.create("ConcentratedForce", name="tip_force", rp_name="RP_tip"))
    materials.add_material(MaterialNode.create(
        "SIMP_BSPFieldMaterials", name="density", part_name="body",
        elementname="design", material_model="NeoHookeanLnJ", mu=options.mu,
        kappa=options.kappa, mumax=options.mu, kappamax=options.kappa,
        bounding_box=[0., options.total_length, 0., options.height, 0., options.depth],
        degree=2,
        simp_field_resolution=min(options.mesh_size, min(options.total_length, options.height, options.depth)/2),
        initial_ratio=math.log(options.volume_fraction/(1-options.volume_fraction)),
        voidpenalfactor=.01,
    ))
    updater = UpdaterNode(name="Updater", params={
        "geometry": [],
        "materials": [{
            "interface_name": "density", "max_step_iter": 50, "if_update": True,
            "objective_functions": [{"type": "Sensitivity", "params": {"normalize_gradient": False}}],
            "constraints": [
                {"type": "MinValue", "params": {"xmin": -15.}},
                {"type": "MaxValue", "params": {"xmax": 15.}},
                {"type": "VolFrac", "params": {
                    "volfrac_min": options.volume_fraction, "volfrac_max": options.volume_fraction,
                    "penalty": 1e6, "elementname": "design",
                }},
            ],
        }],
    })
    steps, signatures = [], {}
    objective_steps = []
    for objective in options.objectives:
        signature = float(objective.force_n)
        if signature not in signatures:
            signatures[signature] = len(steps)
            steps.append({"tip_force": [0., 0., -signature]})
        objective_steps.append(signatures[signature])
    terms, metrics, objective_lines = [], [], []
    for index, (objective, step) in enumerate(zip(options.objectives, objective_steps)):
        motion = f"motion_{index}"
        terms.append(f"({objective.weight!r})*loss_{index}")
        metrics.append(f"tip_motion(self, {step})[2]")
        if objective.kind == "stiffness":
            lines = [f"{motion} = tip_motion(self, {step})", f"loss_{index} = -{motion}[2]/{options.total_length!r}"]
        else:
            lines = [f"{motion} = tip_motion(self, {step})", f"loss_{index} = (({motion}[2]+{objective.target!r})/{objective.target!r}).square()"]
        objective_lines.extend(lines)
    objective_code = "\n".join(objective_lines+["return "+" + ".join(terms)])+"\n"
    metrics_code = "return ["+", ".join(metrics)+"]\n"
    return steps, objective_code, metrics_code, [], updater


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
        if len(self.objectives) >= 8:
            raise ValueError(localized_message("ui.errors.quickstart.quickstart_supports_at_most_eight_objective_terms"))
        channels = sorted(self.members)
        self.objectives.append(QuickstartObjective(
            kind="bend" if self.method == "shapeopt" else "stiffness",
            pressures_kpa={channel: 60. if channel == 1 else 0. for channel in channels},
            workspace_channels=channels[:2],
        ))
        return len(self.objectives) - 1

    def remove(self, index: int) -> None:
        if len(self.objectives) <= 1:
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
