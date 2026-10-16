"""Explicit materials node types and their editable fields."""

from __future__ import annotations

from typing import ClassVar

from ....constants import CONSTANT
from ..base_nodes import MaterialNode
from ..fields import FieldSpec
from ..material_models import MATERIAL_MODEL_CHOICES


class HomogeneousMaterialNode(MaterialNode):
    """UI definition of HomogeneousMaterial."""

    type_name: ClassVar[str] = "HomogeneousMaterial"
    backend_class: ClassVar[str] = "HomogeneousMaterial"
    label_key: ClassVar[str] = "ui.schema.catalog.material.homogeneousmaterial.label"
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.MATERIALS.HOMOGENEOUSMATERIAL
    part_name: str
    material_model: str
    E: float | str
    nu: float | str
    mu: float | str
    kappa: float | str
    c10: float | str
    c01: float | str
    c1: float | str
    c2: float | str
    c3: float | str
    Jm: float | str
    N: float | str
    alpha: list[float] | str
    density: float | str
    elementname: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "part_name",
            "ui.schema.fields.part_name.label.part",
            "combo",
            Defaults.PART_NAME.DEFAULT,
            doc_key="ui.schema.fields.part_name.help.material_assignment_part",
            choices=Defaults.PART_NAME.CHOICES,
        ),
        FieldSpec(
            "material_model",
            "ui.schema.fields.material_model.label.material_model",
            "combo",
            Defaults.MATERIAL_MODEL.DEFAULT,
            doc_key="ui.schema.fields.material_model.help.torchfea_constitutive_model",
            choices=MATERIAL_MODEL_CHOICES,
        ),
        FieldSpec(
            "E",
            "ui.schema.fields.e.label.e",
            "float",
            Defaults.E.DEFAULT,
        ),
        FieldSpec(
            "nu",
            "ui.schema.fields.nu.label.nu",
            "float",
            Defaults.NU.DEFAULT,
        ),
        FieldSpec(
            "mu",
            "ui.schema.fields.mu.label.mu",
            "float",
            Defaults.MU.DEFAULT,
            doc_key="ui.schema.fields.mu.help.text",
        ),
        FieldSpec(
            "kappa",
            "ui.schema.fields.kappa.label.kappa",
            "float",
            Defaults.KAPPA.DEFAULT,
            doc_key="ui.schema.fields.kappa.help.text",
        ),
        FieldSpec(
            "c10",
            "ui.schema.fields.c10.label.c10",
            "float",
            Defaults.C10.DEFAULT,
        ),
        FieldSpec(
            "c01",
            "ui.schema.fields.c01.label.c01",
            "float",
            Defaults.C01.DEFAULT,
        ),
        FieldSpec(
            "c1",
            "ui.schema.fields.c1.label.c1",
            "float",
            Defaults.C1.DEFAULT,
        ),
        FieldSpec(
            "c2",
            "ui.schema.fields.c2.label.c2",
            "float",
            Defaults.C2.DEFAULT,
        ),
        FieldSpec(
            "c3",
            "ui.schema.fields.c3.label.c3",
            "float",
            Defaults.C3.DEFAULT,
        ),
        FieldSpec(
            "Jm",
            "ui.schema.fields.jm.label.jm",
            "float",
            Defaults.JM.DEFAULT,
        ),
        FieldSpec(
            "N",
            "ui.schema.fields.n.label.n",
            "float",
            Defaults.N.DEFAULT,
        ),
        FieldSpec(
            "alpha",
            "ui.schema.fields.alpha.label.alpha",
            "vecN",
            Defaults.ALPHA.DEFAULT,
        ),
        FieldSpec(
            "density",
            "ui.schema.fields.density.label.density",
            "float",
            Defaults.DENSITY.DEFAULT,
            doc_key="ui.schema.fields.density.help.mass_density",
        ),
        FieldSpec(
            "elementname",
            "ui.schema.fields.elementname.label.elems_name_empty_all",
            "combo",
            Defaults.ELEMENTNAME.DEFAULT,
            doc_key="ui.schema.fields.elementname.help.name_under_part_elems_empty_assigns_all_elems",
            choices=Defaults.ELEMENTNAME.CHOICES,
        ),
    )


class SIMPFieldMaterialNode(MaterialNode):
    """UI definition of SIMP_BSPFieldMaterials."""

    type_name: ClassVar[str] = "SIMP_BSPFieldMaterials"
    backend_class: ClassVar[str] = "SIMP_BSPFieldMaterials"
    label_key: ClassVar[str] = "ui.schema.catalog.material.simp_bspfieldmaterials.label"
    is_updatable: ClassVar[bool] = True
    Defaults = CONSTANT.UI.SCHEMA_FIELDS.MATERIALS.SIMP_BSPFIELDMATERIALS
    part_name: str
    material_model: str
    mumax: float | str
    kappamax: float | str
    E: float | str
    nu: float | str
    mu: float | str
    kappa: float | str
    c10: float | str
    c01: float | str
    c1: float | str
    c2: float | str
    c3: float | str
    Jm: float | str
    N: float | str
    alpha: list[float] | str
    simp_ratio_min: float | str
    bounding_box: list[float] | str
    simp_field_resolution: float | str
    degree: int | str
    density: float | str
    initial_ratio: float | str
    voidpenalfactor: float | str
    materialpenalty: int | str
    elementname: str
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "part_name",
            "ui.schema.fields.part_name.label.design_part",
            "combo",
            Defaults.PART_NAME.DEFAULT,
            doc_key="ui.schema.fields.part_name.help.part_carrying_the_simp_design_field",
            choices=Defaults.PART_NAME.CHOICES,
        ),
        FieldSpec(
            "material_model",
            "ui.schema.fields.material_model.label.material_model",
            "combo",
            Defaults.MATERIAL_MODEL.DEFAULT,
            doc_key="ui.schema.fields.material_model.help.torchfea_constitutive_model",
            choices=MATERIAL_MODEL_CHOICES,
        ),
        FieldSpec(
            "mumax",
            "ui.schema.fields.mumax.label.mu_max",
            "float",
            Defaults.MUMAX.DEFAULT,
            doc_key="ui.schema.fields.mumax.help.text",
        ),
        FieldSpec(
            "kappamax",
            "ui.schema.fields.kappamax.label.kappa_max",
            "float",
            Defaults.KAPPAMAX.DEFAULT,
            doc_key="ui.schema.fields.kappamax.help.text",
        ),
        FieldSpec(
            "E",
            "ui.schema.fields.e.label.e",
            "float",
            Defaults.E.DEFAULT,
        ),
        FieldSpec(
            "nu",
            "ui.schema.fields.nu.label.nu",
            "float",
            Defaults.NU.DEFAULT,
        ),
        FieldSpec(
            "mu",
            "ui.schema.fields.mu.label.mu",
            "float",
            Defaults.MU.DEFAULT,
            doc_key="ui.schema.fields.mu.help.text",
        ),
        FieldSpec(
            "kappa",
            "ui.schema.fields.kappa.label.kappa",
            "float",
            Defaults.KAPPA.DEFAULT,
            doc_key="ui.schema.fields.kappa.help.text",
        ),
        FieldSpec(
            "c10",
            "ui.schema.fields.c10.label.c10",
            "float",
            Defaults.C10.DEFAULT,
        ),
        FieldSpec(
            "c01",
            "ui.schema.fields.c01.label.c01",
            "float",
            Defaults.C01.DEFAULT,
        ),
        FieldSpec(
            "c1",
            "ui.schema.fields.c1.label.c1",
            "float",
            Defaults.C1.DEFAULT,
        ),
        FieldSpec(
            "c2",
            "ui.schema.fields.c2.label.c2",
            "float",
            Defaults.C2.DEFAULT,
        ),
        FieldSpec(
            "c3",
            "ui.schema.fields.c3.label.c3",
            "float",
            Defaults.C3.DEFAULT,
        ),
        FieldSpec(
            "Jm",
            "ui.schema.fields.jm.label.jm",
            "float",
            Defaults.JM.DEFAULT,
        ),
        FieldSpec(
            "N",
            "ui.schema.fields.n.label.n",
            "float",
            Defaults.N.DEFAULT,
        ),
        FieldSpec(
            "alpha",
            "ui.schema.fields.alpha.label.alpha",
            "vecN",
            Defaults.ALPHA.DEFAULT,
        ),
        FieldSpec(
            "simp_ratio_min",
            "ui.schema.fields.simp_ratio_min.label.ratio_min",
            "float",
            Defaults.SIMP_RATIO_MIN.DEFAULT,
            doc_key="ui.schema.fields.simp_ratio_min.help.text",
        ),
        FieldSpec(
            "bounding_box",
            "ui.schema.fields.bounding_box.label.bounding_box",
            "vec6",
            Defaults.BOUNDING_BOX.DEFAULT,
            doc_key="ui.schema.fields.bounding_box.help.field_bounding_box_xmin_xmax_ymin_ymax_zmin_zmax",
        ),
        FieldSpec(
            "simp_field_resolution",
            "ui.schema.fields.simp_field_resolution.label.field_resolution",
            "float",
            Defaults.SIMP_FIELD_RESOLUTION.DEFAULT,
            doc_key="ui.schema.fields.simp_field_resolution.help.text",
        ),
        FieldSpec(
            "degree",
            "ui.schema.fields.degree.label.degree",
            "int",
            Defaults.DEGREE.DEFAULT,
            doc_key="ui.schema.fields.degree.help.b",
        ),
        FieldSpec(
            "density",
            "ui.schema.fields.density.label.density",
            "float",
            Defaults.DENSITY.DEFAULT,
            doc_key="ui.schema.fields.density.help.text",
        ),
        FieldSpec(
            "initial_ratio",
            "ui.schema.fields.initial_ratio.label.initial_ratio",
            "float",
            Defaults.INITIAL_RATIO.DEFAULT,
            doc_key="ui.schema.fields.initial_ratio.help.text",
        ),
        FieldSpec(
            "voidpenalfactor",
            "ui.schema.fields.voidpenalfactor.label.void_penal",
            "float",
            Defaults.VOIDPENALFACTOR.DEFAULT,
            doc_key="ui.schema.fields.voidpenalfactor.help.text",
        ),
        FieldSpec(
            "materialpenalty",
            "ui.schema.fields.materialpenalty.label.material_penalty",
            "int",
            Defaults.MATERIALPENALTY.DEFAULT,
            doc_key="ui.schema.fields.materialpenalty.help.text",
        ),
        FieldSpec(
            "elementname",
            "ui.schema.fields.elementname.label.elems_name_empty_all",
            "combo",
            Defaults.ELEMENTNAME.DEFAULT,
            doc_key="ui.schema.fields.elementname.help.name_under_part_elems_empty_assigns_all_elems",
            choices=Defaults.ELEMENTNAME.CHOICES,
        ),
    )
