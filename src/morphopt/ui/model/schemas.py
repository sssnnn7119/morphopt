"""Field schemas and type catalogs for the MorphOpt UI.

A schema is an ordered list of field specs::

    {"key": "r0", "label_key": "ui.schema.fields.r0.label.radius_r0", "type": "float",
     "default": 4.0, "doc_key": "ui.schema.fields.r0.help.text"}

Field ``type`` values understood by the schema-driven editors:
    int, float, str, bool, vec3, vec6, vecN, text (multiline),
    file (path picker), combo (fixed ``choices``), code (python slot).

The dictionaries below declare field defaults, backend class names and
localization keys for the property editor and type menus. ``class_name`` is
the Python class identifier, kept separate from its translated description.
Scheme-specific initial definitions and code snippets belong to
:mod:`morphopt.ui.schemes`.
"""

from __future__ import annotations
from ..i18n import localized_message

from dataclasses import fields

from ...optcore.modelparams.materials import MaterialModels

# --------------------------------------------------------------------------
# small builders
# --------------------------------------------------------------------------


def fld(
    key: str,
    label_key: str,
    typ: str,
    default: object = "",
    doc_key: str = "",
    choices: list | None = None,
    size: int | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
    ints: bool | None = None,
) -> dict:
    """Declare field metadata using explicit label and help resource keys."""
    spec = {
        "key": key, "label_key": label_key, "type": typ, "default": default,
        "doc_key": doc_key, "choices": choices, "size": size,
        "min": minimum, "max": maximum,
    }
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
    defaults: dict[str, object] = {}
    for f in specs:
        d = f["default"]
        if isinstance(d, (list, tuple, dict)):
            d = list(d) if isinstance(d, (list, tuple)) else dict(d)
        defaults[f["key"]] = d
    return defaults


def v3(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> list[float]:
    return [float(x), float(y), float(z)]


# --------------------------------------------------------------------------
# CAD feature operations
# --------------------------------------------------------------------------

def _cad_position() -> list[dict]:
    return [
        fld("x", "ui.schema.fields.x.label.x", "float", 0.0),
        fld("y", "ui.schema.fields.y.label.y", "float", 0.0),
        fld("z", "ui.schema.fields.z.label.z", "float", 0.0),
    ]


CAD_OPERATION_TYPES: dict[str, dict] = {
    "Box": {
        "class_name": "Box",
        "group": "primitive",
        "kind": "box",
        "label_key": "ui.schema.catalog.cad_operation.box.label",
        "params": [
            *_cad_position(),
            fld("dx", "ui.schema.fields.dx.label.dx", "float", 20.0),
            fld("dy", "ui.schema.fields.dy.label.dy", "float", 10.0),
            fld("dz", "ui.schema.fields.dz.label.dz", "float", 5.0),
        ],
    },
    "Wedge": {
        "class_name": "Wedge",
        "group": "primitive",
        "kind": "wedge",
        "label_key": "ui.schema.catalog.cad_operation.wedge.label",
        "params": [
            *_cad_position(),
            fld("dx", "ui.schema.fields.dx.label.dx", "float", 20.0),
            fld("dy", "ui.schema.fields.dy.label.dy", "float", 10.0),
            fld("dz", "ui.schema.fields.dz.label.dz", "float", 5.0),
            fld("ltx", "ui.schema.fields.ltx.label.ltx", "float", 0.0),
        ],
    },
    "Cylinder": {
        "class_name": "Cylinder",
        "group": "primitive",
        "kind": "cylinder",
        "label_key": "ui.schema.catalog.cad_operation.cylinder.label",
        "params": [
            *_cad_position(),
            fld("dx", "ui.schema.fields.dx.label.dx", "float", 0.0),
            fld("dy", "ui.schema.fields.dy.label.dy", "float", 0.0),
            fld("dz", "ui.schema.fields.dz.label.dz", "float", 20.0),
            fld(
                "radius", "ui.schema.fields.radius.label.radius", "float", 5.0,
                doc_key="ui.schema.fields.radius.help.text",
            ),
        ],
    },
    "Sphere": {
        "class_name": "Sphere",
        "group": "primitive",
        "kind": "sphere",
        "label_key": "ui.schema.catalog.cad_operation.sphere.label",
        "params": [*_cad_position(), fld(
            "radius", "ui.schema.fields.radius.label.radius", "float", 5.0,
            doc_key="ui.schema.fields.radius.help.text",
        )],
    },
    "Cone": {
        "class_name": "Cone",
        "group": "primitive",
        "kind": "cone",
        "label_key": "ui.schema.catalog.cad_operation.cone.label",
        "params": [
            *_cad_position(),
            fld("dx", "ui.schema.fields.dx.label.dx", "float", 0.0),
            fld("dy", "ui.schema.fields.dy.label.dy", "float", 0.0),
            fld("dz", "ui.schema.fields.dz.label.dz", "float", 20.0),
            fld("radius1", "ui.schema.fields.radius1.label.radius1", "float", 5.0),
            fld("radius2", "ui.schema.fields.radius2.label.radius2", "float", 1.0),
        ],
    },
    "Torus": {
        "class_name": "Torus",
        "group": "primitive",
        "kind": "torus",
        "label_key": "ui.schema.catalog.cad_operation.torus.label",
        "params": [
            *_cad_position(),
            fld("major_radius", "ui.schema.fields.major_radius.label.major_radius", "float", 8.0),
            fld("minor_radius", "ui.schema.fields.minor_radius.label.minor_radius", "float", 2.0),
        ],
    },
    "StepImport": {
        "class_name": "StepImport",
        "group": "import",
        "kind": "step_import",
        "label_key": "ui.schema.catalog.cad_operation.stepimport.label",
        "params": [
            fld(
                "filename", "ui.schema.fields.filename.label.step_file", "str", "",
                doc_key="ui.schema.fields.filename.help.the_step_geometry_is_embedded_in_the_model",
            )
            | {"read_only": True},
            fld("data", "ui.schema.fields.data.label.step_data", "str", "")
            | {"hidden": True},
        ],
    },
    "Fuse": {
        "class_name": "Fuse",
        "group": "boolean",
        "kind": "fuse",
        "label_key": "ui.schema.catalog.cad_operation.fuse.label",
        "params": [
            fld("object_id", "ui.schema.fields.object_id.label.object_id", "combo", ""),
            fld("tool_id", "ui.schema.fields.tool_id.label.tool_id", "combo", ""),
        ],
    },
    "Cut": {
        "class_name": "Cut",
        "group": "boolean",
        "kind": "cut",
        "label_key": "ui.schema.catalog.cad_operation.cut.label",
        "params": [
            fld("object_id", "ui.schema.fields.object_id.label.object_id", "combo", ""),
            fld("tool_id", "ui.schema.fields.tool_id.label.tool_id", "combo", ""),
        ],
    },
    "Intersect": {
        "class_name": "Intersect",
        "group": "boolean",
        "kind": "intersect",
        "label_key": "ui.schema.catalog.cad_operation.intersect.label",
        "params": [
            fld("object_id", "ui.schema.fields.object_id.label.object_id", "combo", ""),
            fld("tool_id", "ui.schema.fields.tool_id.label.tool_id", "combo", ""),
        ],
    },
    "Fragment": {
        "class_name": "Fragment",
        "group": "boolean",
        "kind": "fragment",
        "label_key": "ui.schema.catalog.cad_operation.fragment.label",
        "params": [
            fld("object_id", "ui.schema.fields.object_id.label.object_id", "combo", ""),
            fld("tool_id", "ui.schema.fields.tool_id.label.tool_id", "combo", ""),
        ],
    },
    "Translate": {
        "class_name": "Translate",
        "group": "transform",
        "kind": "translate",
        "label_key": "ui.schema.catalog.cad_operation.translate.label",
        "params": [
            fld("input_id", "ui.schema.fields.input_id.label.input_id", "combo", ""),
            fld("dx", "ui.schema.fields.dx.label.dx", "float", 5.0),
            fld("dy", "ui.schema.fields.dy.label.dy", "float", 0.0),
            fld("dz", "ui.schema.fields.dz.label.dz", "float", 0.0),
        ],
    },
    "Rotate": {
        "class_name": "Rotate",
        "group": "transform",
        "kind": "rotate",
        "label_key": "ui.schema.catalog.cad_operation.rotate.label",
        "params": [
            fld("input_id", "ui.schema.fields.input_id.label.input_id", "combo", ""),
            *_cad_position(),
            fld("ax", "ui.schema.fields.ax.label.ax", "float", 0.0),
            fld("ay", "ui.schema.fields.ay.label.ay", "float", 0.0),
            fld("az", "ui.schema.fields.az.label.az", "float", 1.0),
            fld("angle", "ui.schema.fields.angle.label.angle", "float", 1.5707963267948966),
        ],
    },
    "Dilate": {
        "class_name": "Dilate",
        "group": "transform",
        "kind": "dilate",
        "label_key": "ui.schema.catalog.cad_operation.dilate.label",
        "params": [
            fld("input_id", "ui.schema.fields.input_id.label.input_id", "combo", ""),
            *_cad_position(),
            fld("sx", "ui.schema.fields.sx.label.sx", "float", 1.0),
            fld("sy", "ui.schema.fields.sy.label.sy", "float", 1.0),
            fld("sz", "ui.schema.fields.sz.label.sz", "float", 1.0),
        ],
    },
    "Mirror": {
        "class_name": "Mirror",
        "group": "transform",
        "kind": "mirror",
        "label_key": "ui.schema.catalog.cad_operation.mirror.label",
        "params": [
            fld("input_id", "ui.schema.fields.input_id.label.input_id", "combo", ""),
            fld("a", "ui.schema.fields.a.label.a", "float", 1.0),
            fld("b", "ui.schema.fields.b.label.b", "float", 0.0),
            fld("c", "ui.schema.fields.c.label.c", "float", 0.0),
            fld("d", "ui.schema.fields.d.label.d", "float", 0.0),
        ],
    },
}


# --------------------------------------------------------------------------
# geometry: surface type -> factory schema
# (role 0 = outer boundary, role >= 1 = inner cavity, flip=True)
# --------------------------------------------------------------------------

#: name -> (display label, import factory string, field specs)
SURFACE_TYPES: dict[str, dict] = {
    "bsp_cylinder": {
        "class_name": "BspSurface",
        "label_key": "ui.schema.catalog.surface.bsp_cylinder.label",
        "factory": "BSP.initialize_cylinder",
        "params": fields_from_specs(
            [
                fld(
                    "r0", "ui.schema.fields.r0.label.radius_r0", "float", 4.0,
                    doc_key="ui.schema.fields.r0.help.initial_outer_inner_radius",
                    minimum=0.0,
                ),
                fld(
                    "length", "ui.schema.fields.length.label.length", "float", 74.0,
                    doc_key="ui.schema.fields.length.help.cylinder_length_along_z",
                    minimum=0.0,
                ),
                fld(
                    "seed_size", "ui.schema.fields.seed_size.label.seed_size", "float", 1.0,
                    doc_key="ui.schema.fields.seed_size.help.mesh_seed_size_of_this_surface",
                    minimum=0.0001,
                ),
                fld(
                    "num_U_ratio", "ui.schema.fields.num_u_ratio.label.num_u_ratio", "int", 1,
                    doc_key="ui.schema.fields.num_u_ratio.help.control_grid_u_ratio",
                    minimum=1,
                ),
                fld(
                    "num_V_ratio", "ui.schema.fields.num_v_ratio.label.num_v_ratio", "int", 1,
                    doc_key="ui.schema.fields.num_v_ratio.help.control_grid_v_ratio",
                    minimum=1,
                ),
                fld(
                    "degree", "ui.schema.fields.degree.label.degree", "int", 3,
                    doc_key="ui.schema.fields.degree.help.b_spline_degree",
                    minimum=1,
                ),
                fld(
                    "init_location", "ui.schema.fields.init_location.label.init_location", "vec3", v3(),
                    doc_key="ui.schema.fields.init_location.help.offset_of_the_surface",
                ),
                fld(
                    "maxR", "ui.schema.fields.maxr.label.maxr", "float", 0.2,
                    doc_key="ui.schema.fields.maxr.help.metric_variation_penalty",
                    minimum=0.0,
                ),
                fld(
                    "maxC", "ui.schema.fields.maxc.label.maxc", "float", 1.0,
                    doc_key="ui.schema.fields.maxc.help.curvature_squared_penalty",
                    minimum=0.0,
                ),
                fld(
                    "maxFF", "ui.schema.fields.maxff.label.maxff", "float", 0.2,
                    doc_key="ui.schema.fields.maxff.help.nonorthogonality_penalty",
                    minimum=0.0,
                ),
                fld(
                    "perturbation_L", "ui.schema.fields.perturbation_l.label.perturbation_l", "float", -1.0,
                    doc_key="ui.schema.fields.perturbation_l.help.wavelength_of_initial_imperfection_0_none",
                ),
            ]
        ),
    },
    "cpgeo_cylinder": {
        "class_name": "CPGEOSurface",
        "label_key": "ui.schema.catalog.surface.cpgeo_cylinder.label",
        "factory": "CPGEO.initialize_cylinder",
        "params": fields_from_specs(
            [
                fld(
                    "r0", "ui.schema.fields.r0.label.radius_r0", "float", 4.0,
                    doc_key="ui.schema.fields.r0.help.initial_radius",
                    minimum=0.0,
                ),
                fld(
                    "length", "ui.schema.fields.length.label.length", "float", 74.0,
                    doc_key="ui.schema.fields.length.help.cylinder_length_along_z",
                    minimum=0.0,
                ),
                fld(
                    "seed_size", "ui.schema.fields.seed_size.label.seed_size", "float", 1.0,
                    doc_key="ui.schema.fields.seed_size.help.mesh_seed_size",
                    minimum=0.0001,
                ),
                fld(
                    "num_U_ratio", "ui.schema.fields.num_u_ratio.label.num_u_ratio", "int", 1,
                    doc_key="ui.schema.fields.num_u_ratio.help.control_grid_u_ratio",
                    minimum=1,
                ),
                fld(
                    "num_V_ratio", "ui.schema.fields.num_v_ratio.label.num_v_ratio", "int", 1,
                    doc_key="ui.schema.fields.num_v_ratio.help.control_grid_v_ratio",
                    minimum=1,
                ),
                fld(
                    "init_location", "ui.schema.fields.init_location.label.init_location", "vec3", v3(),
                    doc_key="ui.schema.fields.init_location.help.offset_of_the_surface",
                ),
                fld(
                    "maxC", "ui.schema.fields.maxc.label.maxc", "float", 1.0,
                    doc_key="ui.schema.fields.maxc.help.curvature_squared_penalty",
                    minimum=0.0,
                ),
                fld(
                    "perturbation_L", "ui.schema.fields.perturbation_l.label.perturbation_l", "float", -1.0,
                    doc_key="ui.schema.fields.perturbation_l.help.wavelength_of_initial_imperfection_0_none",
                ),
            ]
        ),
    },
    "cpgeo_sphere": {
        "class_name": "CPGEOSurface",
        "label_key": "ui.schema.catalog.surface.cpgeo_sphere.label",
        "factory": "CPGEO.initialize_Sphere",
        "params": fields_from_specs(
            [
                fld(
                    "r0", "ui.schema.fields.r0.label.radius_r0", "float", 7.0,
                    doc_key="ui.schema.fields.r0.help.initial_radius",
                    minimum=0.0,
                ),
                fld(
                    "seed_size", "ui.schema.fields.seed_size.label.seed_size", "float", 1.5,
                    doc_key="ui.schema.fields.seed_size.help.mesh_seed_size",
                    minimum=0.0001,
                ),
                fld(
                    "init_location", "ui.schema.fields.init_location.label.init_location", "vec3", v3(),
                    doc_key="ui.schema.fields.init_location.help.center_of_the_sphere",
                ),
                fld(
                    "MaxC", "ui.schema.fields.maxc.label.maxc", "float", 1.0,
                    doc_key="ui.schema.fields.maxc.help.curvature_squared_penalty",
                    minimum=0.0,
                ),
            ]
        ),
    },
    "fixed_stl": {
        "class_name": "FixedSurface",
        "label_key": "ui.schema.catalog.surface.fixed_stl.label",
        "factory": None,  # FixedSurface.initialize_from_stl_file(path_stl)
        "params": fields_from_specs(
            [
                fld(
                    "path_stl", "ui.schema.fields.path_stl.label.stl_file", "file", "",
                    doc_key="ui.schema.fields.path_stl.help.path_to_an_stl_surface",
                ),
            ]
        ),
    },
}

# --------------------------------------------------------------------------
# loads / BC / contact: interface type -> schema
# num_values = number of per-step amplitude values the interface carries
# --------------------------------------------------------------------------


INTERFACE_TYPES: dict[str, dict] = {
    "Pressure": {
        "class_name": "Pressure",
        "label_key": "ui.schema.catalog.interface.pressure.label",
        "num_values": 1,
        "name_hint": "pressure_",
        "params": [
            fld(
                "instance_name", "ui.schema.fields.instance_name.label.instance", "combo", "",
                doc_key="ui.schema.fields.instance_name.help.torchfea_instance",
                choices=[],
            ),
            fld(
                "surface_name", "ui.schema.fields.surface_name.label.surface", "combo", "",
                doc_key="ui.schema.fields.surface_name.help.surface_set_on_the_instance_auto_surface_0_all_surface_1_all",
                choices=[],
            ),  # choices filled dynamically by UI
        ],
    },
    "ConcentratedForce": {
        "class_name": "ConcentratedForce",
        "label_key": "ui.schema.catalog.interface.concentratedforce.label",
        "num_values": 3,
        "name_hint": "force_",
        "params": [
            fld(
                "rp_name", "ui.schema.fields.rp_name.label.reference_point", "combo", "",
                doc_key="ui.schema.fields.rp_name.help.rp_created_by_a_referencepoint_interface",
                choices=[],
            )
        ],
    },
    "ConcentratedMoment": {
        "class_name": "ConcentratedMoment",
        "label_key": "ui.schema.catalog.interface.concentratedmoment.label",
        "num_values": 3,
        "name_hint": "moment_",
        "params": [
            fld(
                "rp_name", "ui.schema.fields.rp_name.label.reference_point", "combo", "",
                doc_key="ui.schema.fields.rp_name.help.rp_created_by_a_referencepoint_interface",
                choices=[],
            )
        ],
    },
    "Bodyforce": {
        "class_name": "BodyForce",
        "label_key": "ui.schema.catalog.interface.bodyforce.label",
        "num_values": 3,
        "name_hint": "body_",
        "params": [
            fld(
                "element_name", "ui.schema.fields.element_name.label.element", "combo", "",
                doc_key="ui.schema.fields.element_name.help.text",
                choices=[],
            ),
            fld(
                "instance_name", "ui.schema.fields.instance_name.label.instance", "combo", "",
                doc_key="ui.schema.fields.instance_name.help.torchfea_instance",
                choices=[],
            ),
        ],
    },
    "SpringToGround": {
        "class_name": "SpringToGround",
        "label_key": "ui.schema.catalog.interface.springtoground.label",
        "num_values": 5,
        "name_hint": "spring_",
        "params": [fld(
            "rp_name", "ui.schema.fields.rp_name.label.reference_point", "combo", "",
            doc_key="ui.schema.fields.rp_name.help.text",
            choices=[],
        )],
    },
    "SpringBetweenRPs": {
        "class_name": "SpringBetweenRPs",
        "label_key": "ui.schema.catalog.interface.springbetweenrps.label",
        "num_values": 2,
        "name_hint": "spring_",
        "params": [
            fld(
                "rp_name1", "ui.schema.fields.rp_name1.label.rp_1", "combo", "",
                doc_key="ui.schema.fields.rp_name1.help.text",
                choices=[],
            ),
            fld(
                "rp_name2", "ui.schema.fields.rp_name2.label.rp_2", "combo", "",
                doc_key="ui.schema.fields.rp_name2.help.text",
                choices=[],
            ),
        ],
    },
    "PenaltyDoF": {
        "class_name": "PenaltyDoF",
        "label_key": "ui.schema.catalog.interface.penaltydof.label",
        "num_values": 2,
        "name_hint": "lock_",
        "params": [
            fld(
                "obj_name", "ui.schema.fields.obj_name.label.object", "str", "",
                doc_key="ui.schema.fields.obj_name.help.text",
            ),
            fld("s", "ui.schema.fields.s.label.dof", "int", 0, doc_key="ui.schema.fields.s.help.text"),
            fld(
                "obj_type", "ui.schema.fields.obj_type.label.obj_type", "combo", "auto",
                doc_key="ui.schema.fields.obj_type.help.text",
                choices=['auto', 'instance', 'rp', 'load', 'constraint', 'boundary'],
            ),
        ],
    },
    "BoundaryCondition": {
        "class_name": "BoundaryCondition",
        "label_key": "ui.schema.catalog.interface.boundarycondition.label",
        "num_values": 0,
        "name_hint": "bc_",
        "params": [
            fld(
                "instance_name", "ui.schema.fields.instance_name.label.instance", "combo", "",
                doc_key="ui.schema.fields.instance_name.help.torchfea_instance",
                choices=[],
            ),
            fld(
                "set_nodes_name", "ui.schema.fields.set_nodes_name.label.node_set",
                "combo", "",
                doc_key="ui.schema.fields.set_nodes_name.help.text",
                choices=[],
            ),
            fld(
                "index_dof", "ui.schema.fields.index_dof.label.fixed_dofs_index_dof", "dofs", [0, 1, 2],
                doc_key="ui.schema.fields.index_dof.help.check_dofs_to_fix_x_y_z_rx_ry_rz",
                size=6,
            ),
        ],
    },
    "BoundaryConditionRP": {
        "class_name": "ReferencePointBoundaryCondition",
        "label_key": "ui.schema.catalog.interface.boundaryconditionrp.label",
        "num_values": 0,
        "name_hint": "bc_rp_",
        "params": [
            fld(
                "rp_name", "ui.schema.fields.rp_name.label.reference_point", "combo", "",
                doc_key="ui.schema.fields.rp_name.help.text",
                choices=[],
            ),
            fld(
                "index_dof", "ui.schema.fields.index_dof.label.fixed_dofs_index_dof", "dofs", [0, 1, 2],
                doc_key="ui.schema.fields.index_dof.help.check_dofs_to_fix_x_y_z_rx_ry_rz",
                size=6,
            ),
        ],
    },
    "Couple": {
        "class_name": "Couple",
        "label_key": "ui.schema.catalog.interface.couple.label",
        "num_values": 0,
        "name_hint": "couple_",
        "params": [
            fld(
                "rp_name", "ui.schema.fields.rp_name.label.reference_point", "combo", "",
                doc_key="ui.schema.fields.rp_name.help.text",
                choices=[],
            ),
            fld(
                "instance_name", "ui.schema.fields.instance_name.label.instance", "combo", "",
                doc_key="ui.schema.fields.instance_name.help.torchfea_instance",
                choices=[],
            ),
            fld(
                "set_nodes_name", "ui.schema.fields.set_nodes_name.label.node_set", "combo", "",
                doc_key="ui.schema.fields.set_nodes_name.help.text",
                choices=[],
            ),
        ],
    },
    "ReferencePoint": {
        "class_name": "ReferencePoint",
        "label_key": "ui.schema.catalog.interface.referencepoint.label",
        "num_values": 0,
        "name_hint": "RP_",
        "params": [
            fld(
                "rp_location", "ui.schema.fields.rp_location.label.rp_location", "vec3", v3(),
                doc_key="ui.schema.fields.rp_location.help.reference_point_position",
            )
        ],
    },
    "Contact": {
        "class_name": "Contact",
        "label_key": "ui.schema.catalog.interface.contact.label",
        "num_values": 0,
        "name_hint": "contact_",
        "params": [
            fld(
                "instance_name1", "ui.schema.fields.instance_name1.label.instance_1", "combo", "",
                doc_key="ui.schema.fields.instance_name1.help.text",
                choices=[],
            ),
            fld(
                "surface_name1", "ui.schema.fields.surface_name1.label.surface_1", "combo", "",
                doc_key="ui.schema.fields.surface_name1.help.select_or_type_a_surface_set_of_another_part",
                choices=[],
            ),
            fld(
                "instance_name2", "ui.schema.fields.instance_name2.label.instance_2", "combo", "",
                doc_key="ui.schema.fields.instance_name2.help.text",
                choices=[],
            ),
            fld(
                "surface_name2", "ui.schema.fields.surface_name2.label.surface_2", "combo", "",
                doc_key="ui.schema.fields.surface_name2.help.select_or_type_a_surface_set",
                choices=[],
            ),
            fld(
                "penalty_threshold_h", "ui.schema.fields.penalty_threshold_h.label.penalty_threshold_h",
                "float", 3.0,
                doc_key="ui.schema.fields.penalty_threshold_h.help.text",
            ),
        ],
    },
    "ContactSelf": {
        "class_name": "SelfContact",
        "label_key": "ui.schema.catalog.interface.contactself.label",
        "num_values": 0,
        "name_hint": "contact_self_",
        "params": [
            fld(
                "instance_name", "ui.schema.fields.instance_name.label.instance", "combo", "",
                doc_key="ui.schema.fields.instance_name.help.torchfea_instance",
                choices=[],
            ),
            fld(
                "surface_name", "ui.schema.fields.surface_name.label.surface", "combo", "",
                doc_key="ui.schema.fields.surface_name.help.select_or_type_a_surface_set",
                choices=[],
            ),
        ],
    },
}

# --------------------------------------------------------------------------
# materials
# --------------------------------------------------------------------------

MATERIAL_MODEL_CHOICES: list[str] = [
    name.removesuffix("Params")
    for name in vars(MaterialModels)
    if name.endswith("Params")
]
MATERIAL_MODEL_PARAMETERS: dict[str, tuple[str, ...]] = {
    name.removesuffix("Params"): tuple(field.name for field in fields(parameter_class))
    for name, parameter_class in vars(MaterialModels).items()
    if name.endswith("Params")
}

MATERIAL_MODEL_DEFAULTS: dict[str, object] = {
    "E": 1.0,
    "nu": 0.45,
    "mu": 0.482,
    "kappa": 4.8,
    "c10": 0.241,
    "c01": 0.241,
    "c1": 0.482,
    "c2": 0.0,
    "c3": 0.0,
    "Jm": 100.0,
    "N": 10.0,
    "alpha": [2.0],
}

_MATERIAL_PARAMETER_FIELDS: dict[str, dict[str, object]] = {
    "E": fld("E", "ui.schema.fields.e.label.e", "float", MATERIAL_MODEL_DEFAULTS['E']),
    "nu": fld("nu", "ui.schema.fields.nu.label.nu", "float", MATERIAL_MODEL_DEFAULTS['nu']),
    "mu": fld(
        "mu", "ui.schema.fields.mu.label.mu", "float", MATERIAL_MODEL_DEFAULTS['mu'],
        doc_key="ui.schema.fields.mu.help.text",
    ),
    "kappa": fld(
        "kappa", "ui.schema.fields.kappa.label.kappa", "float", MATERIAL_MODEL_DEFAULTS['kappa'],
        doc_key="ui.schema.fields.kappa.help.text",
    ),
    "c10": fld("c10", "ui.schema.fields.c10.label.c10", "float", MATERIAL_MODEL_DEFAULTS['c10']),
    "c01": fld("c01", "ui.schema.fields.c01.label.c01", "float", MATERIAL_MODEL_DEFAULTS['c01']),
    "c1": fld("c1", "ui.schema.fields.c1.label.c1", "float", MATERIAL_MODEL_DEFAULTS['c1']),
    "c2": fld("c2", "ui.schema.fields.c2.label.c2", "float", MATERIAL_MODEL_DEFAULTS['c2']),
    "c3": fld("c3", "ui.schema.fields.c3.label.c3", "float", MATERIAL_MODEL_DEFAULTS['c3']),
    "Jm": fld("Jm", "ui.schema.fields.jm.label.jm", "float", MATERIAL_MODEL_DEFAULTS['Jm']),
    "N": fld("N", "ui.schema.fields.n.label.n", "float", MATERIAL_MODEL_DEFAULTS['N']),
    "alpha": fld("alpha", "ui.schema.fields.alpha.label.alpha", "vecN", MATERIAL_MODEL_DEFAULTS['alpha']),
}

_ALL_MATERIAL_PARAMETER_FIELDS: list[dict] = [
    _MATERIAL_PARAMETER_FIELDS[key]
    for key in (
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
    )
]

MATERIAL_TYPES: dict[str, dict] = {
    "HomogeneousMaterial": {
        "class_name": "HomogeneousMaterial",
        "label_key": "ui.schema.catalog.material.homogeneousmaterial.label",
        "params": [
            fld(
                "part_name", "ui.schema.fields.part_name.label.part", "combo", "",
                doc_key="ui.schema.fields.part_name.help.material_assignment_part",
                choices=[],
            ),
            fld(
                "material_model", "ui.schema.fields.material_model.label.material_model",
                "combo", "NeoHookeanLnJ",
                doc_key="ui.schema.fields.material_model.help.torchfea_constitutive_model",
                choices=MATERIAL_MODEL_CHOICES,
            ),
            *_ALL_MATERIAL_PARAMETER_FIELDS,
            fld(
                "density", "ui.schema.fields.density.label.density", "float", 1.08e-09,
                doc_key="ui.schema.fields.density.help.mass_density",
            ),
            fld(
                "elementname", "ui.schema.fields.elementname.label.elems_name_empty_all", "combo", "",
                doc_key="ui.schema.fields.elementname.help.name_under_part_elems_empty_assigns_all_elems",
                choices=[''],
            ),
        ],
    },
    "SIMP_BSPFieldMaterials": {
        "class_name": "SIMP_BSPFieldMaterials",
        "label_key": "ui.schema.catalog.material.simp_bspfieldmaterials.label",
        "design": True,
        "params": [
            fld(
                "part_name", "ui.schema.fields.part_name.label.design_part", "combo", "",
                doc_key="ui.schema.fields.part_name.help.part_carrying_the_simp_design_field",
                choices=[],
            ),
            fld(
                "material_model", "ui.schema.fields.material_model.label.material_model",
                "combo", "NeoHookeanLnJ",
                doc_key="ui.schema.fields.material_model.help.torchfea_constitutive_model",
                choices=MATERIAL_MODEL_CHOICES,
            ),
            fld(
                "mumax", "ui.schema.fields.mumax.label.mu_max", "float", 10.0,
                doc_key="ui.schema.fields.mumax.help.text",
            ),
            fld(
                "kappamax", "ui.schema.fields.kappamax.label.kappa_max", "float", 100.0,
                doc_key="ui.schema.fields.kappamax.help.text",
            ),
            *_ALL_MATERIAL_PARAMETER_FIELDS,
            fld(
                "simp_ratio_min", "ui.schema.fields.simp_ratio_min.label.ratio_min", "float", 1e-07,
                doc_key="ui.schema.fields.simp_ratio_min.help.text",
            ),
            fld(
                "bounding_box", "ui.schema.fields.bounding_box.label.bounding_box",
                "vec6", [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                doc_key="ui.schema.fields.bounding_box.help.field_bounding_box_xmin_xmax_ymin_ymax_zmin_zmax",
            ),
            fld(
                "simp_field_resolution", "ui.schema.fields.simp_field_resolution.label.field_resolution",
                "float", 0.5,
                doc_key="ui.schema.fields.simp_field_resolution.help.text",
            ),
            fld(
                "degree", "ui.schema.fields.degree.label.degree", "int", 2,
                doc_key="ui.schema.fields.degree.help.b",
            ),
            fld(
                "density", "ui.schema.fields.density.label.density", "float", 1.08e-09,
                doc_key="ui.schema.fields.density.help.text",
            ),
            fld(
                "initial_ratio", "ui.schema.fields.initial_ratio.label.initial_ratio", "float", 0.5,
                doc_key="ui.schema.fields.initial_ratio.help.text",
            ),
            fld(
                "voidpenalfactor", "ui.schema.fields.voidpenalfactor.label.void_penal", "float", 0.01,
                doc_key="ui.schema.fields.voidpenalfactor.help.text",
            ),
            fld(
                "materialpenalty", "ui.schema.fields.materialpenalty.label.material_penalty", "int", 8,
                doc_key="ui.schema.fields.materialpenalty.help.text",
            ),
            fld(
                "elementname", "ui.schema.fields.elementname.label.elems_name_empty_all", "combo", "",
                doc_key="ui.schema.fields.elementname.help.name_under_part_elems_empty_assigns_all_elems",
                choices=[''],
            ),
        ],
    },
}

# --------------------------------------------------------------------------
# part interface type -> schema
# A part interface owns ONE Part plus its Instances.  The default Instance is
# ``<part>-1`` in UI-generated models; additional Instances are declared in
# ``define_instance``.
# Only boundary part
# interfaces own SurfaceNode children (index 0 = outer boundary, 1.. =
# cavities); imported/INP parts have no surfaces.
# --------------------------------------------------------------------------

_COMMON_PART_FIELDS: list[dict] = [
    fld(
        "part_name", "ui.schema.fields.part_name.label.assembly_part_name", "str", "",
        doc_key="ui.schema.fields.part_name.help.part_name_inside_the_assembly_empty_uses_the_interface_name",
    ),
]


def _exterior_surface_field(default: str) -> dict:
    return fld(
        "exterior_surface", "ui.schema.fields.exterior_surface.label.exterior_surface", "str", default,
        doc_key="ui.schema.fields.exterior_surface.help.surface_set_used_as_the_part_exterior_surface_empty_none",
    )


PART_INTERFACE_TYPES: dict[str, dict] = {
    "BoundaryPart": {
        "class_name": "BoundaryPart",
        "design": True,
        "label_key": "ui.schema.catalog.part_interface.boundarypartinterface.label",
        "surfaces": True,
        "params": fields_from_specs(
            [
                fld(
                    "fea_seed_size", "ui.schema.fields.fea_seed_size.label.fea_seed_size", "float", 2.5,
                    doc_key="ui.schema.fields.fea_seed_size.help.gmsh_volume_mesh_seed_size",
                    minimum=0.001,
                ),
                fld(
                    "mesh_order", "ui.schema.fields.mesh_order.label.mesh_order", "combo", 1,
                    doc_key="ui.schema.fields.mesh_order.help.element_order_of_the_generated_mesh",
                    choices=[1, 2],
                ),
                _exterior_surface_field("surface_0_All"),
                *_COMMON_PART_FIELDS,
            ]
        ),
    },
    "INPPart": {
        "class_name": "INPPart",
        "label_key": "ui.schema.catalog.part_interface.inppartinterface.label",
        "surfaces": False,
        "params": fields_from_specs(
            [
                fld(
                    "mesh_file", "ui.schema.fields.mesh_file.label.inp_file", "file", "",
                    doc_key="ui.schema.fields.mesh_file.help.abaqus_inp_mesh_file_holding_the_part",
                ),
                fld(
                    "inp_part_name", "ui.schema.fields.inp_part_name.label.part_in_file", "str", "",
                    doc_key="ui.schema.fields.inp_part_name.help.part_name_inside_the_inp_empty_selects_the_only_part",
                ),
                _exterior_surface_field(""),
                *_COMMON_PART_FIELDS,
            ]
        ),
    },
    "TorchFEAPart": {
        "class_name": "TorchFEAPart",
        "label_key": "ui.schema.catalog.part_interface.torchfeapartinterface.label",
        "surfaces": False,
        "params": fields_from_specs(
            [
                fld(
                    "model_directory", "ui.schema.fields.model_directory.label.model_directory", "dir", "",
                    doc_key="ui.schema.fields.model_directory.help.folder_containing_the_exported_npz_model",
                ),
                fld(
                    "model_filename", "ui.schema.fields.model_filename.label.model_file", "str", "",
                    doc_key="ui.schema.fields.model_filename.help.exported_npz_name_empty_uses_the_newest_file_in_the_folder",
                ),
                fld(
                    "model_part_name", "ui.schema.fields.model_part_name.label.part_in_model", "str", "",
                    doc_key="ui.schema.fields.model_part_name.help.part_to_import_from_the_archive_empty_selects_the_only_part",
                ),
                _exterior_surface_field(""),
                *_COMMON_PART_FIELDS,
            ]
        ),
    },
    "BasePart": {
        "class_name": "BasePart",
        "label_key": "ui.schema.catalog.part_interface.basepartinterface.label",
        "surfaces": False,
        "custom_only": True,
        "params": fields_from_specs(
            [_exterior_surface_field(""), *_COMMON_PART_FIELDS]
        ),
    },
}


PART_INTERFACE_TYPES["BoxPart"] = {
    "class_name": "BoxPart",
    "label_key": "ui.schema.catalog.part_interface.boxpartinterface.label",
    "surfaces": False,
    "params": [
        fld(
            "length", "ui.schema.fields.length.label.text", "float", 40.0,
            doc_key="ui.schema.fields.length.help.z",
            minimum=0.001,
        ),
        fld(
            "height", "ui.schema.fields.height.label.text", "float", 16.0,
            doc_key="ui.schema.fields.height.help.text",
            minimum=0.001,
        ),
        fld(
            "depth", "ui.schema.fields.depth.label.text", "float", 8.0,
            doc_key="ui.schema.fields.depth.help.text", minimum=0.001,
        ),
        fld("mesh_size", "ui.schema.fields.mesh_size.label.text", "float", 2.0, minimum=0.001),
        fld(
            "mesh_order", "ui.schema.fields.mesh_order.label.mesh_order", "combo", 2,
            doc_key="ui.schema.fields.mesh_order.help.text",
            choices=[1, 2],
        ),
        _exterior_surface_field("extern"), *_COMMON_PART_FIELDS,
    ],
}
PART_INTERFACE_TYPES["CADPart"] = {
    "class_name": "CADPart",
    "label_key": "ui.schema.catalog.part_interface.cadpartinterface.label",
    "surfaces": False,
    "params": [
        fld("mesh_size", "ui.schema.fields.mesh_size.label.text", "float", 2.0, minimum=0.001),
        fld(
            "mesh_order", "ui.schema.fields.mesh_order.label.mesh_order", "combo", 1,
            doc_key="ui.schema.fields.mesh_order.help.text",
            choices=[1, 2],
        ),
        _exterior_surface_field("extern"), *_COMMON_PART_FIELDS,
    ],
}


PART_INTERFACE_TYPES["OffsetBoundaryPart"] = {
    "class_name": "OffsetBoundaryPart",
    "design": True,
    "label_key": "ui.schema.catalog.part_interface.offsetboundarypartinterface.label",
    "surfaces": True,
    "params": [
        *PART_INTERFACE_TYPES["BoundaryPart"]["params"],
        fld(
            "shell_thickness", "ui.schema.fields.shell_thickness.label.offset_thickness", "float", 0.5,
            minimum=0.001,
        ),
        fld("num_layers", "ui.schema.fields.num_layers.label.offset_layers", "int", 1, minimum=1),
    ],
}


def part_interface_spec(interface_type: str) -> dict:
    """Return the schema entry of one geometry-interface type."""
    try:
        return PART_INTERFACE_TYPES[interface_type]
    except KeyError as exc:
        raise KeyError(localized_message("ui.errors.schemas.unknown_geometry_interface_type_value", value_0=interface_type)) from exc


# --------------------------------------------------------------------------
# solver / updater generic fields
# --------------------------------------------------------------------------

SOLVER_FIELDS: list[dict] = fields_from_specs(
    [
        fld(
            "num_process", "ui.schema.fields.num_process.label.processes", "int", 4,
            doc_key="ui.schema.fields.num_process.help.number_of_fea_solver_processes",
            minimum=1,
        ),
        fld(
            "gpus", "ui.schema.fields.gpus.label.gpu_devices", "vecN", [],
            doc_key="ui.schema.fields.gpus.help.list_of_gpu_ids_e_g_cuda_0_or_empty_for_cpu",
        ),
        fld(
            "task_index_list", "ui.schema.fields.task_index_list.label.task_index_list", "vecN", [],
            doc_key="ui.schema.fields.task_index_list.help.partition_of_load_steps_over_processes_empty_auto",
        ),
    ]
)

# Code slots (Python fields) rendered with the code editor. Custom geometry
# symmetry code is an updater item emitted on the selected Part subclass.
CODE_SLOT_KEYS = ("objective_function", "get_metrics")

# --------------------------------------------------------------------------
# updater: structured objective / constraint catalogues (UI chooser, no code)
# group: which sub-optimizer the term belongs to; gen: code template using
# {param} placeholders replaced by repr() of the stored value.
# --------------------------------------------------------------------------

UPDATER_OBJECTIVES: dict[str, dict] = {
    "ShapeDerivative": {
        "class_name": "ShapeDerivative",
        "label_key": "ui.schema.catalog.updater_objective.shapederivative.label",
        "group": "geometry",
        "gen": "self.objectivefuncs.ShapeDerivative()",
        "params": [],
    },
    "Sensitivity": {
        "class_name": "Sensitivity",
        "label_key": "ui.schema.catalog.updater_objective.sensitivity.label",
        "group": "materials",
        "gen": "self.objectivefuncs.Sensitivity(normalize_gradient={normalize_gradient})",
        "params": [fld(
            "normalize_gradient", "ui.schema.fields.normalize_gradient.label.normalize_gradient",
            "bool", False,
            doc_key="ui.schema.fields.normalize_gradient.help.text",
        )],
    },
    "DensityFieldMinimize": {
        "class_name": "DensityFieldMinimize",
        "label_key": "ui.schema.catalog.updater_objective.densityfieldminimize.label",
        "group": "materials",
        "gen": "self.objectivefuncs.DensityFieldMinimize(scale={scale})",
        "params": [fld(
            "scale", "ui.schema.fields.scale.label.scale", "float", 1e-07,
            doc_key="ui.schema.fields.scale.help.text",
        )],
    },
}

_CUSTOM_SYMMETRY_CODE_FIELD = fld(
    "code", "ui.schema.fields.code.label.constraint_function_body", "code", "",
    doc_key="ui.schema.fields.code.help.custom_code_executed_by_apply_surface_constraints",
)

SURFACE_SYMMETRY_CONSTRAINTS: dict[str, dict] = {
    "BspMirror": {
        "class_name": "BspMirrorConstraint",
        "label_key": "ui.schema.catalog.symmetry_constraint.bspmirror.label",
        "factory": "BSP",
        "method": "mirror",
        "params": [
            fld(
                "plane", "ui.schema.fields.plane.label.text", "combo", "xz",
                doc_key="ui.schema.fields.plane.help.xz_y_0_xy_z_offset",
                choices=['xz', 'xy'],
            ),
            fld(
                "offset", "ui.schema.fields.offset.label.text", "float", 0.0,
                doc_key="ui.schema.fields.offset.help.xy_xz_0",
            ),
        ],
    },
    "CPGEOMirror": {
        "class_name": "CPGEOMirrorConstraint",
        "label_key": "ui.schema.catalog.symmetry_constraint.cpgeomirror.label",
        "factory": "CPGEO",
        "method": "mirror",
        "params": [
            fld(
                "plane", "ui.schema.fields.plane.label.text", "combo", "xz",
                doc_key="ui.schema.fields.plane.help.offset",
                choices=['xy', 'xz', 'yz'],
            ),
            fld("offset", "ui.schema.fields.offset.label.text", "float", 0.0),
        ],
    },
    "CPGEORotation": {
        "class_name": "CPGEORotationalSymmetryConstraint",
        "label_key": "ui.schema.catalog.symmetry_constraint.cpgeorotation.label",
        "factory": "CPGEO",
        "method": "rotate",
        "params": [
            fld(
                "axis", "ui.schema.fields.axis.label.text", "combo", "z",
                doc_key="ui.schema.fields.axis.help.text",
                choices=['x', 'y', 'z'],
            ),
            fld("order", "ui.schema.fields.order.label.text", "int", 2, minimum=2),
            fld("center", "ui.schema.fields.center.label.text", "vec3", v3()),
        ],
    },
    "BspRelation": {
        "class_name": "BspSurfaceRelationConstraint",
        "label_key": "ui.schema.catalog.symmetry_constraint.bsprelation.label",
        "factory": "BSP",
        "method": "relate",
        "related_surface": True,
        "params": [fld("pose", "ui.schema.fields.pose.label.tx_ty_tz_rx_ry_rz", "vec6", [0.0] * 6)],
    },
    "CPGEORelation": {
        "class_name": "CPGEOSurfaceRelationConstraint",
        "label_key": "ui.schema.catalog.symmetry_constraint.cpgeorelation.label",
        "factory": "CPGEO",
        "method": "relate",
        "related_surface": True,
        "params": [fld("pose", "ui.schema.fields.pose.label.tx_ty_tz_rx_ry_rz", "vec6", [0.0] * 6)],
    },
    "Custom": {
        "class_name": "",
        "label_key": "ui.schema.catalog.symmetry_constraint.custom.label",
        "factory": None,
        "method": None,
        "params": [_CUSTOM_SYMMETRY_CODE_FIELD],
    },
}

UPDATER_CONSTRAINTS: dict[str, dict] = {
    "Fairness": {
        "class_name": "Fairness",
        "label_key": "ui.schema.catalog.updater_constraint.fairness.label",
        "group": "geometry",
        "gen": "self.objectivefuncs.Fairness()",
        "params": [],
    },
    "Distance": {
        "class_name": "Distance",
        "label_key": "ui.schema.catalog.updater_constraint.distance.label",
        "group": "geometry",
        "gen": "self.objectivefuncs.Distance(min_distance={min_distance})",
        "params": [
            fld(
                "min_distance", "ui.schema.fields.min_distance.label.min_distance_i_j",
                "mat", [[2.5, 2.5], [2.5, 2.5]],
                doc_key="ui.schema.fields.min_distance.help.text",
            )
        ],
    },
    "Cylinder": {
        "class_name": "Cylinder",
        "label_key": "ui.schema.catalog.updater_constraint.cylinder.label",
        "group": "geometry",
        "gen": "self.objectivefuncs.boundarys.Cylinder(radius={radius}, height={height}, bottom={bottom})",
        "params": [
            fld(
                "radius", "ui.schema.fields.radius.label.radius", "float", 10.0,
                doc_key="ui.schema.fields.radius.help.text",
            ),
            fld(
                "height", "ui.schema.fields.height.label.height", "float", 80.0,
                doc_key="ui.schema.fields.height.help.envelope_top_z",
            ),
            fld(
                "bottom", "ui.schema.fields.bottom.label.bottom", "float", 0.0,
                doc_key="ui.schema.fields.bottom.help.text",
            ),
        ],
    },
    "MinRadius": {
        "class_name": "MinRadius",
        "label_key": "ui.schema.catalog.updater_constraint.minradius.label",
        "group": "geometry",
        "gen": "self.objectivefuncs.boundarys.MinRadius(radius={radius})",
        "params": [fld(
            "radius", "ui.schema.fields.radius.label.radius", "float", 2.0,
            doc_key="ui.schema.fields.radius.help.text",
        )],
    },
    "VolumeMaximization": {
        "class_name": "VolumeMaximization",
        "label_key": "ui.schema.catalog.updater_constraint.volumemaximization.label",
        "group": "geometry",
        "gen": "self.objectivefuncs.VolumeMaximization(surf_idx={surf_idx}, weight={weight})",
        "params": [
            fld(
                "surf_idx", "ui.schema.fields.surf_idx.label.surf_idx", "int", 1,
                doc_key="ui.schema.fields.surf_idx.help.text",
                minimum=1,
            ),
            fld(
                "weight", "ui.schema.fields.weight.label.weight", "float", 0.01,
                doc_key="ui.schema.fields.weight.help.text",
            ),
        ],
    },
    "InwardCurvatureRadius": {
        "class_name": "InwardCurvatureRadius",
        "label_key": "ui.schema.catalog.updater_constraint.inwardcurvatureradius.label",
        "group": "geometry",
        "hidden": True,
        "gen": (
            "morphopt.codesign.InwardCurvatureRadius("
            "margin={margin}, margin_ratio={margin_ratio}, p={p}, penalty_scale={penalty_scale})"
        ),
        "params": [
            fld(
                "margin", "ui.schema.fields.margin.label.margin", "float", 0.4,
                doc_key="ui.schema.fields.margin.help.text",
            ),
            fld(
                "margin_ratio", "ui.schema.fields.margin_ratio.label.margin_ratio", "float", 0.45,
                doc_key="ui.schema.fields.margin_ratio.help.text",
            ),
            fld(
                "p", "ui.schema.fields.p.label.p", "int", 8,
                doc_key="ui.schema.fields.p.help.text",
                minimum=1,
            ),
            fld(
                "penalty_scale", "ui.schema.fields.penalty_scale.label.penalty_scale", "float", 1000.0,
                doc_key="ui.schema.fields.penalty_scale.help.text",
            ),
        ],
    },
    "OffsetSurfaceMinThickness": {
        "class_name": "OffsetSurfaceMinThickness",
        "label_key": "ui.schema.catalog.updater_constraint.offsetsurfaceminthickness.label",
        "group": "geometry",
        "hidden": True,
        "gen": "morphopt.codesign.OffsetSurfaceMinThickness(min_distance={min_distance})",
        "params": [fld(
            "min_distance", "ui.schema.fields.min_distance.label.min_distance", "float", 2.0,
            doc_key="ui.schema.fields.min_distance.help.text",
        )],
    },
    "VolFrac": {
        "class_name": "VolFrac",
        "label_key": "ui.schema.catalog.updater_constraint.volfrac.label",
        "group": "materials",
        "gen": (
            "self.objectivefuncs.VolFrac(volfrac_min={volfrac_min}, volfrac_max={volfrac_max}, "
            "penalty={penalty}, elementname={elementname})"
        ),
        "params": [
            fld(
                "volfrac_min", "ui.schema.fields.volfrac_min.label.volfrac_min", "float", 0.0,
                doc_key="ui.schema.fields.volfrac_min.help.text",
            ),
            fld(
                "volfrac_max", "ui.schema.fields.volfrac_max.label.volfrac_max", "float", 0.6,
                doc_key="ui.schema.fields.volfrac_max.help.text",
            ),
            fld(
                "penalty", "ui.schema.fields.penalty.label.penalty", "float", 10000.0,
                doc_key="ui.schema.fields.penalty.help.text",
            ),
            fld(
                "elementname", "ui.schema.fields.elementname.label.elems_name", "combo", "",
                doc_key="ui.schema.fields.elementname.help.part_elems",
                choices=[],
            ),
        ],
    },
    "MinValue": {
        "class_name": "MinValue",
        "label_key": "ui.schema.catalog.updater_constraint.minvalue.label",
        "group": "materials",
        "gen": "self.objectivefuncs.boundarys.MinValue(xmin={xmin}, threshold={threshold}, p={p})",
        "params": [
            fld(
                "xmin", "ui.schema.fields.xmin.label.xmin", "float", -15.0,
                doc_key="ui.schema.fields.xmin.help.text",
            ),
            fld(
                "threshold", "ui.schema.fields.threshold.label.threshold", "float", 0.0,
                doc_key="ui.schema.fields.threshold.help.text",
            ),
            fld(
                "p", "ui.schema.fields.p.label.p", "int", 2,
                doc_key="ui.schema.fields.p.help.text",
                minimum=1,
            ),
        ],
    },
    "MaxValue": {
        "class_name": "MaxValue",
        "label_key": "ui.schema.catalog.updater_constraint.maxvalue.label",
        "group": "materials",
        "gen": "self.objectivefuncs.boundarys.MaxValue(xmax={xmax}, threshold={threshold}, p={p})",
        "params": [
            fld(
                "xmax", "ui.schema.fields.xmax.label.xmax", "float", 15.0,
                doc_key="ui.schema.fields.xmax.help.text",
            ),
            fld(
                "threshold", "ui.schema.fields.threshold.label.threshold", "float", 0.0,
                doc_key="ui.schema.fields.threshold.help.text",
            ),
            fld(
                "p", "ui.schema.fields.p.label.p", "int", 2,
                doc_key="ui.schema.fields.p.help.text",
                minimum=1,
            ),
        ],
    },
}

UPDATER_CATALOG = {"objectives": UPDATER_OBJECTIVES, "constraints": UPDATER_CONSTRAINTS}


def symmetry_constraint_defaults(item_type: str) -> dict:
    """Return defaults for one geometry-symmetry constraint."""
    spec = SURFACE_SYMMETRY_CONSTRAINTS.get(item_type)
    if spec is None:
        return {}
    return clone_defaults(spec["params"])


def symmetry_constraint(item_type: str, **overrides) -> dict:
    """Build one geometry-symmetry constraint from its schema defaults."""
    params = symmetry_constraint_defaults(item_type)
    params.update(overrides)
    item = {"type": item_type, "params": params}
    if item_type != "Custom":
        item["surface_index"] = None
    return item


def surface_factory_for_type(surface_type: str) -> str | None:
    """Backend surface family (BSP / CPGEO) for a registered surface type."""
    factory = SURFACE_TYPES.get(surface_type, {}).get("factory")
    return factory.split(".", 1)[0] if factory else None


def available_surface_symmetry_types(surface_types) -> list[str]:
    """List built-in symmetry constraints supported by the given surface types."""
    counts: dict[str, int] = {}
    for surface_type in surface_types:
        factory = surface_factory_for_type(surface_type)
        if factory:
            counts[factory] = counts.get(factory, 0) + 1
    return [
        item_type
        for item_type, spec in SURFACE_SYMMETRY_CONSTRAINTS.items()
        if counts.get(spec["factory"], 0) >= (2 if spec.get("related_surface") else 1)
    ]


def updater_item_defaults(item_type: str, category: str) -> dict:
    spec = UPDATER_CATALOG.get(category, {}).get(item_type)
    if spec is None:
        return {}
    return clone_defaults(spec["params"])


# --------------------------------------------------------------------------
# updater term / section factories
#
# These build the plain config dicts that live on the ``UpdaterNode`` from
# the catalogued defaults, so scheme templates declare only the *deviations*
# (``Distance(min_distance=...)`` instead of a full hand-written dict).  The
# code generator keeps reading the very same ``{"type", "params"}`` layout.
# --------------------------------------------------------------------------


def updater_objective(item_type: str, **overrides) -> dict:
    """One objective term: schema defaults + ``overrides`` for item ``type``."""
    spec = UPDATER_OBJECTIVES[item_type]
    params = clone_defaults(spec["params"])
    params.update(overrides)
    return {"type": item_type, "params": params}


def updater_constraint(item_type: str, **overrides) -> dict:
    """One constraint term: schema defaults + ``overrides`` for item ``type``."""
    spec = UPDATER_CONSTRAINTS[item_type]
    params = clone_defaults(spec["params"])
    params.update(overrides)
    return {"type": item_type, "params": params}


def geometry_updater_config(
    part_name: str = "",
    max_step_iter: int = 50,
    if_update: list | None = None,
    objective_functions: tuple | None = None,
    constraints: tuple | None = None,
    symmetry_constraints: tuple = (),
) -> dict:
    """Config of one geometry sub-optimizer.

    ``part_name`` is the boundary part interface it updates; an empty name
    means "the only boundary part of the model".
    New configs include ShapeDerivative and Fairness, Distance, Cylinder
    penalties. Explicitly empty collections remain empty.
    """
    return {
        "part_name": str(part_name or ""),
        "max_step_iter": int(max_step_iter),
        "if_update": list(if_update) if if_update is not None else [],
        "objective_functions": list(objective_functions) if objective_functions is not None else [
            updater_objective("ShapeDerivative"),
        ],
        "constraints": list(constraints) if constraints is not None else [
            updater_constraint("Fairness"),
            updater_constraint("Distance"),
            updater_constraint("Cylinder"),
        ],
        "symmetry_constraints": list(symmetry_constraints),
    }


def materials_updater_config(
    interface_name: str = "",
    max_step_iter: int = 50,
    if_update: bool | list[bool] = True,
    objective_functions: tuple = (),
    constraints: tuple = (),
) -> dict:
    """Config of one material sub-optimizer.

    ``interface_name`` is the material interface it updates; an empty name
    means "the only design-carrying material interface of the model".
    """
    return {
        "interface_name": str(interface_name or ""),
        "max_step_iter": int(max_step_iter),
        "if_update": if_update,
        "objective_functions": list(objective_functions),
        "constraints": list(constraints),
    }


def surface_spec(surface_type: str) -> dict:
    return SURFACE_TYPES[surface_type]


def interface_spec(interface_type: str) -> dict:
    return INTERFACE_TYPES[interface_type]


def material_spec(material_type: str) -> dict:
    return MATERIAL_TYPES[material_type]
