"""Field schemas and type catalogs for the MorphOpt UI.

A schema is an ordered list of field specs::

    {"key": "r0", "label": "Outer radius", "type": "float",
     "default": 4.0, "doc": "..."}

Field ``type`` values understood by the schema-driven editors:
    int, float, str, bool, vec3, vec6, vecN, text (multiline),
    file (path picker), combo (fixed ``choices``), code (python slot).

The dictionaries below are the single source of truth for both the default
parameters assigned when a node is created and the forms rendered in the
property editor.  Keys match the backend constructor arguments.
"""

from __future__ import annotations

from typing import Any, Optional

# --------------------------------------------------------------------------
# small builders
# --------------------------------------------------------------------------


def fld(key: str, label: str, typ: str, default: Any = "",
        doc: str = "", choices: Optional[list] = None,
        size: Optional[int] = None, minimum: Optional[float] = None,
        maximum: Optional[float] = None, ints: Optional[bool] = None,
        label_en: Optional[str] = None, doc_en: Optional[str] = None) -> dict:
    """Build a field spec dict (see module docstring for types).

    ``label_en`` / ``doc_en`` provide the English variants of ``label`` /
    ``doc`` when they are localized (pick() selects them in English mode).
    ``ints=True`` marks index-like list fields (kept as int on parse).
    """
    spec = {
        "key": key, "label": label, "type": typ, "default": default,
        "doc": doc, "choices": choices, "size": size,
        "min": minimum, "max": maximum,
    }
    if label_en is not None:
        spec["label_en"] = label_en
    if doc_en is not None:
        spec["doc_en"] = doc_en
    if ints is not None:
        spec["ints"] = ints
    return spec


def fields_from_specs(*groups: list[dict]) -> list[dict]:
    """Concatenate groups of field specs."""
    out: list[dict] = []
    for g in groups:
        out.extend(g)
    return out


# --------------------------------------------------------------------------
# defaults helpers (typed)
# --------------------------------------------------------------------------

def clone_defaults(specs: list[dict]) -> dict:
    """Build a ``params`` dict from schema defaults (lists/tuples are copied)."""
    defaults: dict[str, Any] = {}
    for f in specs:
        d = f["default"]
        if isinstance(d, (list, tuple, dict)):
            d = list(d) if isinstance(d, (list, tuple)) else dict(d)
        defaults[f["key"]] = d
    return defaults


def v3(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> list[float]:
    return [float(x), float(y), float(z)]


# --------------------------------------------------------------------------
# geometry: surface type -> factory schema
# (role 0 = outer boundary, role >= 1 = inner cavity, flip=True)
# --------------------------------------------------------------------------

#: name -> (display label, import factory string, field specs)
SURFACE_TYPES: dict[str, dict] = {
    "bsp_cylinder": {
        "label": "BSP cylinder (B-spline)",
        "factory": "BSP.initialize_cylinder",
        "params": fields_from_specs([
            fld("r0", "Radius r0", "float", 4.0, "Initial outer/inner radius.", minimum=0.0),
            fld("length", "Length", "float", 74.0, "Cylinder length along z.", minimum=0.0),
            fld("seed_size", "Seed size", "float", 1.0, "Mesh seed size of this surface.", minimum=1e-4),
            fld("num_U_ratio", "num_U_ratio", "int", 1, "Control grid U ratio.", minimum=1),
            fld("num_V_ratio", "num_V_ratio", "int", 1, "Control grid V ratio.", minimum=1),
            fld("degree", "Degree", "int", 3, "B-spline degree.", minimum=1),
            fld("init_location", "init_location", "vec3", v3(), "Offset of the surface."),
            fld("maxR", "maxR", "float", 0.2, "Max radius change step.", minimum=0.0),
            fld("maxC", "maxC", "float", 1.0, "Max control change.", minimum=0.0),
            fld("maxFF", "maxFF", "float", 0.2, "Max form-factor change.", minimum=0.0),
            fld("perturbation_L", "perturbation_L", "float", -1.0, "Wavelength of initial imperfection (<=0 none)."),
        ]),
    },
    "cpgeo_cylinder": {
        "label": "CPGEO cylinder",
        "factory": "CPGEO.initialize_cylinder",
        "params": fields_from_specs([
            fld("r0", "Radius r0", "float", 4.0, "Initial radius.", minimum=0.0),
            fld("length", "Length", "float", 74.0, "Cylinder length along z.", minimum=0.0),
            fld("seed_size", "Seed size", "float", 1.0, "Mesh seed size.", minimum=1e-4),
            fld("num_U_ratio", "num_U_ratio", "int", 1, "Control grid U ratio.", minimum=1),
            fld("num_V_ratio", "num_V_ratio", "int", 1, "Control grid V ratio.", minimum=1),
            fld("degree", "Degree", "int", 3, "B-spline degree.", minimum=1),
            fld("init_location", "init_location", "vec3", v3(), "Offset of the surface."),
            fld("maxR", "maxR", "float", 0.2, "Max radius change step.", minimum=0.0),
            fld("MaxC", "MaxC", "float", 1.0, "Max control change.", minimum=0.0),
            fld("maxFF", "maxFF", "float", 0.2, "Max form-factor change.", minimum=0.0),
            fld("perturbation_L", "perturbation_L", "float", -1.0, "Wavelength of initial imperfection (<=0 none)."),
        ]),
    },
    "cpgeo_sphere": {
        "label": "CPGEO sphere",
        "factory": "CPGEO.initialize_Sphere",
        "params": fields_from_specs([
            fld("r0", "Radius r0", "float", 7.0, "Initial radius.", minimum=0.0),
            fld("seed_size", "Seed size", "float", 1.5, "Mesh seed size.", minimum=1e-4),
            fld("init_location", "init_location", "vec3", v3(), "Center of the sphere."),
            fld("MaxC", "MaxC", "float", 1.0, "Max control change.", minimum=0.0),
        ]),
    },
    "fixed_stl": {
        "label": "Fixed surface (STL)",
        "factory": None,  # FixedSurface.initialize_from_stl_file(path_stl)
        "params": fields_from_specs([
            fld("path_stl", "STL file", "file", "", "Path to an STL surface."),
        ]),
    },
}

#: role labels shown in the tree (index 0 is special)
SURFACE_ROLE_NAMES = {0: "Outer boundary", 1: "Inner cavity 1", 2: "Inner cavity 2",
                      3: "Inner cavity 3", 4: "Inner cavity 4", 5: "Inner cavity 5"}

# --------------------------------------------------------------------------
# loads / BC / contact: interface type -> schema
# num_values = number of per-step amplitude values the interface carries
# --------------------------------------------------------------------------

def _surf_interfacedoc() -> str:
    return "Surface set on the instance (auto: surface_0_All, surface_1_All, ...)."


INTERFACE_TYPES: dict[str, dict] = {
    "Pressure": {
        "label": "Pressure",
        "num_values": 1,
        "name_hint": "pressure_",
        "params": [
            fld("instance_name", "Instance", "str", "final_model"),
            fld("surface_name", "Surface", "combo", "surface_1_All", _surf_interfacedoc(),
                choices=[]),  # choices filled dynamically by UI
        ],
    },
    "ConcentratedForce": {
        "label": "Concentrated force (on RP)",
        "num_values": 3,
        "name_hint": "force_",
        "params": [fld("rp_name", "Reference point", "combo", "", "RP created by a ReferencePoint interface.", choices=[])],
    },
    "ConcentratedMoment": {
        "label": "Concentrated moment (on RP)",
        "num_values": 3,
        "name_hint": "moment_",
        "params": [fld("rp_name", "Reference point", "combo", "", "RP created by a ReferencePoint interface.", choices=[])],
    },
    "Bodyforce": {
        "label": "Body force",
        "num_values": 3,
        "name_hint": "body_",
        "params": [
            fld("element_name", "Element", "combo", "C3D4", "", choices=["C3D4", "C3D8", "C3D10", "C3D6", "C3D20"]),
            fld("instance_name", "Instance", "str", "final_model"),
        ],
    },
    "SpringToGround": {
        "label": "Spring to ground (RP)",
        "num_values": 5,
        "name_hint": "spring_",
        "params": [fld("rp_name", "Reference point", "combo", "", "", choices=[])],
    },
    "SpringBetweenRPs": {
        "label": "Spring between RPs",
        "num_values": 2,
        "name_hint": "spring_",
        "params": [fld("rp_name1", "RP 1", "combo", "", "", choices=[]),
                  fld("rp_name2", "RP 2", "combo", "", "", choices=[])],
    },
    "PenaltyDoF": {
        "label": "Penalty DoF",
        "num_values": 2,
        "name_hint": "lock_",
        "params": [fld("obj_name", "Object", "str", ""),
                  fld("s", "DoF", "int", 0),
                  fld("obj_type", "obj_type", "combo", "auto", "", choices=["auto", "node", "element", "part"])],
    },
    "BoundaryCondition": {
        "label": "Boundary condition (surface nodes)",
        "num_values": 0,
        "name_hint": "bc_",
        "params": [
            fld("instance_name", "Instance", "str", "final_model"),
            fld("set_nodes_name", "Node set", "combo", "surface_0_Bottom", "", choices=[]),
            fld("index_dof", "固定自由度 index_dof", "dofs", [0, 1, 2],
                "勾选要固定的自由度 (X,Y,Z,Rx,Ry,Rz).", size=6,
                label_en="Fixed DOFs (index_dof)",
                doc_en="Check DOFs to fix (X, Y, Z, Rx, Ry, Rz)."),
        ],
    },
    "BoundaryConditionRP": {
        "label": "Boundary condition (RP)",
        "num_values": 0,
        "name_hint": "bc_rp_",
        "params": [fld("rp_name", "Reference point", "combo", "", "", choices=[]),
                  fld("index_dof", "固定自由度 index_dof", "dofs", [0, 1, 2],
                      "勾选要固定的自由度 (X,Y,Z,Rx,Ry,Rz).", size=6,
                      label_en="Fixed DOFs (index_dof)",
                      doc_en="Check DOFs to fix (X, Y, Z, Rx, Ry, Rz).")],
    },
    "Couple": {
        "label": "Couple (RP <-> surface nodes)",
        "num_values": 0,
        "name_hint": "couple_",
        "params": [
            fld("rp_name", "Reference point", "combo", "", "", choices=[]),
            fld("instance_name", "Instance", "str", "final_model"),
            fld("set_nodes_name", "Node set", "combo", "surface_0_Head", "", choices=[]),
        ],
    },
    "ReferencePoint": {
        "label": "Reference point",
        "num_values": 0,
        "name_hint": "RP_",
        "params": [fld("rp_location", "RP location", "vec3", v3(), "Reference point position.")],
    },
    "Contact": {
        "label": "Contact (surface pair)",
        "num_values": 0,
        "name_hint": "contact_",
        "params": [
            fld("instance_name1", "Instance 1", "str", "final_model"),
            fld("surface_name1", "Surface 1", "combo", "", "可下拉选择或手输另一部件的表面集。", choices=[],
                doc_en="Select or type a surface set of another part."),
            fld("instance_name2", "Instance 2", "str", ""),
            fld("surface_name2", "Surface 2", "combo", "", "可下拉选择或手输表面集。", choices=[],
                doc_en="Select or type a surface set."),
            fld("penalty_threshold_h", "penalty_threshold_h", "float", 3.0),
        ],
    },
    "ContactSelf": {
        "label": "Self contact",
        "num_values": 0,
        "name_hint": "contact_self_",
        "params": [
            fld("instance_name", "Instance", "str", "final_model"),
            fld("surface_name", "Surface", "combo", "", "可下拉选择或手输表面集。", choices=[],
                doc_en="Select or type a surface set."),
        ],
    },
}

# --------------------------------------------------------------------------
# materials
# --------------------------------------------------------------------------

MATERIAL_TYPES: dict[str, dict] = {
    "HomogeneousMaterial": {
        "label": "Homogeneous (NeoHookean)",
        "params": [
            fld("mu", "mu", "float", 0.482, "Shear modulus."),
            fld("kappa", "kappa", "float", 4.8, "Bulk modulus."),
            fld("density", "density", "float", 1.08e-9, "Mass density."),
            fld("elementname", "Element", "combo", "C3D4", "", choices=["C3D4", "C3D8", "C3D6"]),
        ],
    },
    "SIMP_BSPFieldMaterials": {
        "label": "SIMP BSP density field",
        "params": [
            fld("mumax", "mu max", "float", 10.0),
            fld("kappamax", "kappa max", "float", 100.0),
            fld("simp_ratio_min", "ratio min", "float", 1e-7),
            fld("bounding_box", "bounding_box", "vec6", [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], "Field bounding box [xmin,xmax,ymin,ymax,zmin,zmax]."),
            fld("simp_field_resolution", "field resolution", "float", 0.5),
            fld("degree", "degree", "int", 2),
            fld("density", "density", "float", 1.08e-9),
            fld("initial_ratio", "initial_ratio", "float", 0.5),
            fld("voidpenalfactor", "void penal", "float", 1e-2),
            fld("materialpenalty", "material penalty", "float", 8.0),
            fld("elementname", "Element", "combo", "C3D4", "", choices=["C3D4", "C3D8", "C3D10", "C3D6"]),
        ],
    },
    "CodesignMaterials": {
        "label": "Co-design (SIMP field + shell)",
        "params": [
            fld("mumax", "mu max", "float", 4.5),
            fld("kappamax", "kappa max", "float", 45.0),
            fld("simp_ratio_min", "ratio min", "float", 1e-4),
            fld("bounding_box", "bounding_box", "vec6", [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
            fld("simp_field_resolution", "field resolution", "float", 1.0),
            fld("degree", "degree", "int", 3),
            fld("density", "density", "float", 1.08e-9),
            fld("initial_ratio", "initial_ratio", "float", 0.5),
            fld("voidpenalfactor", "void penal", "float", 1e-1),
            fld("materialpenalty", "material penalty", "float", 8.0),
            fld("elementname", "Solid element", "combo", "C3D4", "", choices=["C3D4", "C3D8"]),
            fld("shell_mu", "shell mu", "float", 0.48),
            fld("shell_kappa", "shell kappa", "float", 4.8),
            fld("shell_density", "shell density", "float", 1.08e-9),
            fld("shell_elementname", "Shell element", "combo", "C3D6", "", choices=["C3D6"]),
        ],
    },
}

#: which material types may be used by each scheme
MATERIAL_BY_SCHEME: dict[str, list[str]] = {
    "simp": ["SIMP_BSPFieldMaterials"],
    "shapeopt": ["HomogeneousMaterial"],
    "codesign": ["CodesignMaterials"],
}

#: scheme -> kind of geometry params node ("geometry") extra field group
GEOMETRY_SCHEMES: dict[str, list[dict]] = {
    "shapeopt": fields_from_specs([
        fld("fea_seed_size", "FEA seed size", "float", 2.5, "Global Gmsh seed size.", minimum=1e-3),
        fld("mesh_order", "Mesh order", "combo", 1, "", choices=[1, 2]),
        fld("reinitialize_per_iter", "re-mesh every", "int", 5, "Regenerate mesh every N iterations.", minimum=1),
    ]),
    "codesign": fields_from_specs([
        fld("fea_seed_size", "FEA seed size", "float", 2.5, "Global Gmsh seed size.", minimum=1e-3),
        fld("mesh_order", "Mesh order", "combo", 2, "", choices=[1, 2]),
        fld("reinitialize_per_iter", "re-mesh every", "int", 10, "Regenerate mesh every N iterations.", minimum=1),
        fld("thickness", "Shell thickness", "float", 2.0, "Offset thickness of inner surfaces.", minimum=0.0),
        fld("num_layers", "Shell layers", "int", 1, "C3D6 wedge layers through the shell.", minimum=1),
    ]),
    "simp": fields_from_specs([
        fld("mesh_file", "Mesh (.inp)", "file", "", "Fixed mesh file read by FixedGeometryINP."),
    ]),
}

# --------------------------------------------------------------------------
# solver / updater generic fields
# --------------------------------------------------------------------------

SOLVER_FIELDS: list[dict] = fields_from_specs([
    fld("num_process", "Processes", "int", 4, "Number of FEA solver processes.", minimum=1),
    fld("gpus", "GPU devices", "vecN", [], "List of gpu ids, e.g. ['cuda:0'] or empty for cpu."),
    fld("task_index_list", "task_index_list", "vecN", [], "Partition of load steps over processes (empty = auto)."),
])

# code slots (python fields) rendered with the code editor
CODE_SLOT_KEYS = ("apply_surface_constraints", "map_bsp_designfield", "objective_function", "get_metrics")

SCHEME_LABELS = {
    "simp": "SIMP · topology / material field",
    "shapeopt": "Shape optimization",
    "codesign": "Co-design · shape + material",
}


# --------------------------------------------------------------------------
# updater: structured objective / constraint catalogue (UI chooser, no code)
# group: which sub-optimizer the term belongs to; gen: code template using
# {param} placeholders replaced by repr() of the stored value.
# --------------------------------------------------------------------------

def _mat2d(d: Any) -> Any:
    """default for a 2-D python-literal matrix field"""
    return d


UPDATER_OBJECTIVES: dict[str, dict] = {
    "ShapeDerivative": {
        "label": "ShapeDerivative (线性化形状灵敏度)",
        "label_en": "ShapeDerivative (linearized shape sensitivity)",
        "group": "geometry", "schemes": ["shapeopt", "codesign"],
        "gen": "self.objectivefuncs.ShapeDerivative()", "params": [],
    },
    "Sensitivity": {
        "label": "Sensitivity (材料灵敏度线性项)",
        "label_en": "Sensitivity (linear material-sensitivity term)",
        "group": "materials", "schemes": ["simp", "codesign"],
        "gen": "self.objectivefuncs.Sensitivity(normalize_gradient={normalize_gradient})",
        "params": [fld("normalize_gradient", "normalize_gradient", "bool", False)],
    },
    "DensityFieldMinimize": {
        "label": "DensityFieldMinimize (密度回归惩罚)",
        "label_en": "DensityFieldMinimize (density-regression penalty)",
        "group": "materials", "schemes": ["simp", "codesign"],
        "gen": "self.objectivefuncs.DensityFieldMinimize(scale={scale})",
        "params": [fld("scale", "scale", "float", 1e-7)],
    },
}

UPDATER_CONSTRAINTS: dict[str, dict] = {
    "Fairness": {
        "label": "Fairness (表面曲率正则)",
        "label_en": "Fairness (surface-curvature regularization)",
        "group": "geometry", "schemes": ["shapeopt", "codesign"],
        "gen": "self.objectivefuncs.Fairness(surfaces=params.geometry)", "params": [],
    },
    "Distance": {
        "label": "Distance (表面间最小距离)",
        "label_en": "Distance (minimum inter-surface distance)",
        "group": "geometry", "schemes": ["shapeopt", "codesign"],
        "gen": "self.objectivefuncs.Distance(min_distance={min_distance})",
        "params": [fld("min_distance", "min_distance [[i][j]]", "mat",
                      [[2.5, 2.5], [2.5, 2.5]])],
    },
    "Cylinder": {
        "label": "Cylinder boundary (柱面包络)",
        "label_en": "Cylinder boundary (cylindrical envelope)",
        "group": "geometry", "schemes": ["shapeopt", "codesign"],
        "gen": "self.objectivefuncs.boundarys.Cylinder(radius={radius}, height={height}, bottom={bottom})",
        "params": [fld("radius", "radius", "float", 10.0),
                  fld("height", "height", "float", 80.0),
                  fld("bottom", "bottom", "float", 0.0)],
    },
    "MinRadius": {
        "label": "MinRadius (最小半径约束)",
        "label_en": "MinRadius (minimum-radius constraint)",
        "group": "geometry", "schemes": ["shapeopt", "codesign"],
        "gen": "self.objectivefuncs.boundarys.MinRadius(radius={radius})",
        "params": [fld("radius", "radius", "float", 2.0)],
    },
    "VolumeMaximization": {
        "label": "VolumeMaximization (腔体体积最大化)",
        "label_en": "VolumeMaximization (cavity-volume maximization)",
        "group": "geometry", "schemes": ["shapeopt", "codesign"],
        "gen": "self.objectivefuncs.VolumeMaximization(geometryparam=self.params_update, surf_idx={surf_idx}, weight={weight})",
        "params": [fld("surf_idx", "surf_idx", "int", 1, minimum=1),
                  fld("weight", "weight", "float", 1e-2)],
    },
    "InwardCurvatureRadius": {
        "label": "InwardCurvatureRadius (codesign)",
        "group": "geometry", "schemes": ["codesign"],
        "gen": ("morphopt.codesign.InwardCurvatureRadius(geometry=params.geometry, "
                "margin={margin}, margin_ratio={margin_ratio}, p={p}, penalty_scale={penalty_scale})"),
        "params": [fld("margin", "margin", "float", 0.4),
                  fld("margin_ratio", "margin_ratio", "float", 0.45),
                  fld("p", "p", "int", 8, minimum=1),
                  fld("penalty_scale", "penalty_scale", "float", 1e3)],
    },
    "OffsetSurfaceMinThickness": {
        "label": "OffsetSurfaceMinThickness (codesign)",
        "group": "geometry", "schemes": ["codesign"],
        "gen": "morphopt.codesign.OffsetSurfaceMinThickness(geometry=params.geometry, min_distance={min_distance})",
        "params": [fld("min_distance", "min_distance", "float", 2.0)],
    },
    "VolFrac": {
        "label": "VolFrac (体积分数带约束)",
        "label_en": "VolFrac (volume-fraction band constraint)",
        "group": "materials", "schemes": ["simp", "codesign"],
        "gen": ("self.objectivefuncs.VolFrac(volfrac_min={volfrac_min}, volfrac_max={volfrac_max}, "
                "penalty={penalty}, element_name={element_name})"),
        "params": [fld("volfrac_min", "volfrac_min", "float", 0.0),
                  fld("volfrac_max", "volfrac_max", "float", 0.6),
                  fld("penalty", "penalty", "float", 1e4),
                  fld("element_name", "element_name", "combo", "C3D4",
                      "", choices=["C3D4", "C3D8", "C3D10", "C3D6"])],
    },
    "MinValue": {
        "label": "MinValue (控制点下界)",
        "label_en": "MinValue (control-point lower bound)",
        "group": "materials", "schemes": ["simp", "codesign"],
        "gen": "self.objectivefuncs.boundarys.MinValue(xmin={xmin}, threshold={threshold}, p={p})",
        "params": [fld("xmin", "xmin", "float", -15.0),
                  fld("threshold", "threshold", "float", 0.0),
                  fld("p", "p", "int", 2, minimum=1)],
    },
    "MaxValue": {
        "label": "MaxValue (控制点上界)",
        "label_en": "MaxValue (control-point upper bound)",
        "group": "materials", "schemes": ["simp", "codesign"],
        "gen": "self.objectivefuncs.boundarys.MaxValue(xmax={xmax}, threshold={threshold}, p={p})",
        "params": [fld("xmax", "xmax", "float", 15.0),
                  fld("threshold", "threshold", "float", 0.0),
                  fld("p", "p", "int", 2, minimum=1)],
    },
}

UPDATER_CATALOG = {"objectives": UPDATER_OBJECTIVES, "constraints": UPDATER_CONSTRAINTS}


def updater_item_specs(scheme: str, group: str, category: str) -> list[dict]:
    """Return the item specs (label/fields/gen) usable for scheme+group."""
    cat = UPDATER_CATALOG.get(category, {})
    return [spec for spec in cat.values()
            if spec["group"] == group and scheme in spec["schemes"]]


def updater_item_defaults(item_type: str, category: str) -> dict:
    spec = UPDATER_CATALOG.get(category, {}).get(item_type)
    if spec is None:
        return {}
    return clone_defaults(spec["params"])


def surface_spec(surface_type: str) -> dict:
    return SURFACE_TYPES[surface_type]


def interface_spec(interface_type: str) -> dict:
    return INTERFACE_TYPES[interface_type]


def material_spec(material_type: str) -> dict:
    return MATERIAL_TYPES[material_type]
