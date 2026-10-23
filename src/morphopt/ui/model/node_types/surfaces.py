"""Explicit surfaces node types and their editable fields."""

from __future__ import annotations

from typing import ClassVar

from ....constants import CONSTANT
from ..base_nodes import SurfaceNode
from ..fields import FieldSpec


class BspCylinderSurfaceNode(SurfaceNode):
    """UI definition of BspSurface."""

    type_name: ClassVar[str] = "bsp_cylinder"
    is_updatable = True
    end_node_set_names = ("Bottom", "Head")
    backend_class: ClassVar[str] = "BspSurface"
    label_key: ClassVar[str] = "ui.schema.catalog.surface.bsp_cylinder.label"
    factory: ClassVar[str] = "BSP.initialize_cylinder"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.SURFACES.BSP_CYLINDER
    r0: float | str
    length: float | str
    seed_size: float | str
    num_U_ratio: int | str
    num_V_ratio: int | str
    degree: int | str
    init_location: list[float] | str
    maxR: float | str
    maxC: float | str
    maxFF: float | str
    perturbation_L: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "r0",
            "ui.schema.fields.r0.label.radius_r0",
            "float",
            Defaults.R0.DEFAULT,
            doc_key="ui.schema.fields.r0.help.initial_outer_inner_radius",
            minimum=Defaults.R0.MIN,
        ),
        FieldSpec(
            "length",
            "ui.schema.fields.length.label.length",
            "float",
            Defaults.LENGTH.DEFAULT,
            doc_key="ui.schema.fields.length.help.cylinder_length_along_z",
            minimum=Defaults.LENGTH.MIN,
        ),
        FieldSpec(
            "seed_size",
            "ui.schema.fields.seed_size.label.seed_size",
            "float",
            Defaults.SEED_SIZE.DEFAULT,
            doc_key="ui.schema.fields.seed_size.help.mesh_seed_size_of_this_surface",
            minimum=Defaults.SEED_SIZE.MIN,
        ),
        FieldSpec(
            "num_U_ratio",
            "ui.schema.fields.num_u_ratio.label.num_u_ratio",
            "int",
            Defaults.NUM_U_RATIO.DEFAULT,
            doc_key="ui.schema.fields.num_u_ratio.help.control_grid_u_ratio",
            minimum=Defaults.NUM_U_RATIO.MIN,
        ),
        FieldSpec(
            "num_V_ratio",
            "ui.schema.fields.num_v_ratio.label.num_v_ratio",
            "int",
            Defaults.NUM_V_RATIO.DEFAULT,
            doc_key="ui.schema.fields.num_v_ratio.help.control_grid_v_ratio",
            minimum=Defaults.NUM_V_RATIO.MIN,
        ),
        FieldSpec(
            "degree",
            "ui.schema.fields.degree.label.degree",
            "int",
            Defaults.DEGREE.DEFAULT,
            doc_key="ui.schema.fields.degree.help.b_spline_degree",
            minimum=Defaults.DEGREE.MIN,
        ),
        FieldSpec(
            "init_location",
            "ui.schema.fields.init_location.label.init_location",
            "vec3",
            Defaults.INIT_LOCATION.DEFAULT,
            doc_key="ui.schema.fields.init_location.help.offset_of_the_surface",
        ),
        FieldSpec(
            "maxR",
            "ui.schema.fields.maxr.label.maxr",
            "float",
            Defaults.MAXR.DEFAULT,
            doc_key="ui.schema.fields.maxr.help.metric_variation_penalty",
            minimum=Defaults.MAXR.MIN,
        ),
        FieldSpec(
            "maxC",
            "ui.schema.fields.maxc.label.maxc",
            "float",
            Defaults.MAXC.DEFAULT,
            doc_key="ui.schema.fields.maxc.help.curvature_squared_penalty",
            minimum=Defaults.MAXC.MIN,
        ),
        FieldSpec(
            "maxFF",
            "ui.schema.fields.maxff.label.maxff",
            "float",
            Defaults.MAXFF.DEFAULT,
            doc_key="ui.schema.fields.maxff.help.nonorthogonality_penalty",
            minimum=Defaults.MAXFF.MIN,
        ),
        FieldSpec(
            "perturbation_L",
            "ui.schema.fields.perturbation_l.label.perturbation_l",
            "float",
            Defaults.PERTURBATION_L.DEFAULT,
            doc_key="ui.schema.fields.perturbation_l.help.wavelength_of_initial_imperfection_0_none",
        ),
    )


class CPGEOCylinderSurfaceNode(SurfaceNode):
    """UI definition of CPGEOSurface."""

    type_name: ClassVar[str] = "cpgeo_cylinder"
    is_updatable = True
    backend_class: ClassVar[str] = "CPGEOSurface"
    label_key: ClassVar[str] = "ui.schema.catalog.surface.cpgeo_cylinder.label"
    factory: ClassVar[str] = "CPGEO.initialize_cylinder"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.SURFACES.CPGEO_CYLINDER
    r0: float | str
    length: float | str
    seed_size: float | str
    num_U_ratio: int | str
    num_V_ratio: int | str
    init_location: list[float] | str
    maxC: float | str
    perturbation_L: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "r0",
            "ui.schema.fields.r0.label.radius_r0",
            "float",
            Defaults.R0.DEFAULT,
            doc_key="ui.schema.fields.r0.help.initial_radius",
            minimum=Defaults.R0.MIN,
        ),
        FieldSpec(
            "length",
            "ui.schema.fields.length.label.length",
            "float",
            Defaults.LENGTH.DEFAULT,
            doc_key="ui.schema.fields.length.help.cylinder_length_along_z",
            minimum=Defaults.LENGTH.MIN,
        ),
        FieldSpec(
            "seed_size",
            "ui.schema.fields.seed_size.label.seed_size",
            "float",
            Defaults.SEED_SIZE.DEFAULT,
            doc_key="ui.schema.fields.seed_size.help.mesh_seed_size",
            minimum=Defaults.SEED_SIZE.MIN,
        ),
        FieldSpec(
            "num_U_ratio",
            "ui.schema.fields.num_u_ratio.label.num_u_ratio",
            "int",
            Defaults.NUM_U_RATIO.DEFAULT,
            doc_key="ui.schema.fields.num_u_ratio.help.control_grid_u_ratio",
            minimum=Defaults.NUM_U_RATIO.MIN,
        ),
        FieldSpec(
            "num_V_ratio",
            "ui.schema.fields.num_v_ratio.label.num_v_ratio",
            "int",
            Defaults.NUM_V_RATIO.DEFAULT,
            doc_key="ui.schema.fields.num_v_ratio.help.control_grid_v_ratio",
            minimum=Defaults.NUM_V_RATIO.MIN,
        ),
        FieldSpec(
            "init_location",
            "ui.schema.fields.init_location.label.init_location",
            "vec3",
            Defaults.INIT_LOCATION.DEFAULT,
            doc_key="ui.schema.fields.init_location.help.offset_of_the_surface",
        ),
        FieldSpec(
            "maxC",
            "ui.schema.fields.maxc.label.maxc",
            "float",
            Defaults.MAXC.DEFAULT,
            doc_key="ui.schema.fields.maxc.help.curvature_squared_penalty",
            minimum=Defaults.MAXC.MIN,
        ),
        FieldSpec(
            "perturbation_L",
            "ui.schema.fields.perturbation_l.label.perturbation_l",
            "float",
            Defaults.PERTURBATION_L.DEFAULT,
            doc_key="ui.schema.fields.perturbation_l.help.wavelength_of_initial_imperfection_0_none",
        ),
    )


class CPGEOSphereSurfaceNode(SurfaceNode):
    """UI definition of CPGEOSurface."""

    type_name: ClassVar[str] = "cpgeo_sphere"
    is_updatable = True
    backend_class: ClassVar[str] = "CPGEOSurface"
    label_key: ClassVar[str] = "ui.schema.catalog.surface.cpgeo_sphere.label"
    factory: ClassVar[str] = "CPGEO.initialize_Sphere"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.SURFACES.CPGEO_SPHERE
    r0: float | str
    seed_size: float | str
    init_location: list[float] | str
    MaxC: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "r0",
            "ui.schema.fields.r0.label.radius_r0",
            "float",
            Defaults.R0.DEFAULT,
            doc_key="ui.schema.fields.r0.help.initial_radius",
            minimum=Defaults.R0.MIN,
        ),
        FieldSpec(
            "seed_size",
            "ui.schema.fields.seed_size.label.seed_size",
            "float",
            Defaults.SEED_SIZE.DEFAULT,
            doc_key="ui.schema.fields.seed_size.help.mesh_seed_size",
            minimum=Defaults.SEED_SIZE.MIN,
        ),
        FieldSpec(
            "init_location",
            "ui.schema.fields.init_location.label.init_location",
            "vec3",
            Defaults.INIT_LOCATION.DEFAULT,
            doc_key="ui.schema.fields.init_location.help.center_of_the_sphere",
        ),
        FieldSpec(
            "MaxC",
            "ui.schema.fields.maxc.label.maxc",
            "float",
            Defaults.MAXC.DEFAULT,
            doc_key="ui.schema.fields.maxc.help.curvature_squared_penalty",
            minimum=Defaults.MAXC.MIN,
        ),
    )


class MeshSurfaceNode(SurfaceNode):
    """A triangular mesh boundary imported from an STL file."""

    type_name: ClassVar[str] = "mesh_surface"
    backend_class: ClassVar[str] = "MeshSurface"
    label_key: ClassVar[str] = "ui.schema.catalog.surface.mesh_surface.label"
    factory: ClassVar[str | None] = None
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.SURFACES.MESH_SURFACE
    path_stl: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "path_stl",
            "ui.schema.fields.path_stl.label.stl_file",
            "file",
            Defaults.PATH_STL.DEFAULT,
            doc_key="ui.schema.fields.path_stl.help.path_to_an_stl_surface",
        ),
    )


class BREPSurfaceNode(SurfaceNode):
    """A BREP boundary embedded as STEP data and exported as a geometry asset."""

    type_name: ClassVar[str] = "brep_surface"
    backend_class: ClassVar[str] = "BREPSurface"
    label_key: ClassVar[str] = "ui.schema.catalog.surface.brep_surface.label"
    factory: ClassVar[str | None] = None
    filename: str
    data: str
    brep_metadata: str
    design_faces: list[str]
    control_point_spacing: float | str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "filename", "ui.schema.fields.filename.label.step_file", "str", "",
            doc_key="ui.schema.fields.filename.help.the_step_geometry_is_embedded_in_the_model",
            read_only=True,
        ),
        FieldSpec("data", "ui.schema.fields.data.label.step_data", "str", "", hidden=True),
        FieldSpec("brep_metadata", "ui.assets.brep_metadata", "str", "{}", hidden=True),
        FieldSpec("design_faces", "ui.schema.fields.design_faces.label", "vecN", ()),
        FieldSpec("control_point_spacing", "ui.schema.fields.control_point_spacing.label", "float", 1.0, minimum=1e-9),
    )
