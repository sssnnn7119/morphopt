"""Field schemas and type catalogs for the MorphOpt UI.

A schema is an ordered list of field specs::

    {"key": "r0", "label": "Outer radius", "type": "float",
     "default": 4.0, "doc": "..."}

Field ``type`` values understood by the schema-driven editors:
    int, float, str, bool, vec3, vec6, vecN, text (multiline),
    file (path picker), combo (fixed ``choices``), code (python slot).

The dictionaries below are the single source of truth for field defaults and
forms rendered in the property editor.  They do *not* choose an optimization
scheme's default problem tree, generated backend classes, display label, or
code snippets; those belong to :mod:`morphopt.ui.schemes`.
"""

from __future__ import annotations

from typing import Any, Optional

# --------------------------------------------------------------------------
# small builders
# --------------------------------------------------------------------------


_FIELD_LABELS_ZH = {
    "r0": "半径 r0",
    "length": "长度",
    "seed_size": "网格种子尺寸",
    "num_U_ratio": "U 方向控制网格比例",
    "num_V_ratio": "V 方向控制网格比例",
    "degree": "B 样条阶次",
    "init_location": "初始位置",
    "maxR": "最大半径变化",
    "maxC": "最大控制点变化",
    "MaxC": "最大控制点变化",
    "maxFF": "最大形状因子变化",
    "perturbation_L": "初始扰动波长",
    "path_stl": "STL 文件",
    "instance_name": "实体",
    "instance_name1": "实体 1",
    "instance_name2": "实体 2",
    "surface_name": "表面",
    "surface_name1": "表面 1",
    "surface_name2": "表面 2",
    "set_nodes_name": "节点集",
    "rp_name": "参考点",
    "rp_name1": "参考点 1",
    "rp_name2": "参考点 2",
    "rp_location": "参考点位置",
    "element_name": "单元类型",
    "elementname": "单元类型",
    "shell_elementname": "壳层单元类型",
    "obj_name": "对象",
    "s": "自由度",
    "obj_type": "对象类型",
    "penalty_threshold_h": "罚函数阈值 h",
    "mu": "剪切模量 μ",
    "kappa": "体积模量 κ",
    "density": "密度",
    "mumax": "最大剪切模量",
    "kappamax": "最大体积模量",
    "simp_ratio_min": "最小密度比例",
    "bounding_box": "设计域边界框",
    "simp_field_resolution": "密度场分辨率",
    "initial_ratio": "初始密度比例",
    "voidpenalfactor": "空域惩罚因子",
    "materialpenalty": "材料惩罚指数",
    "shell_mu": "壳层剪切模量",
    "shell_kappa": "壳层体积模量",
    "shell_density": "壳层密度",
    "fea_seed_size": "FEA 网格种子尺寸",
    "mesh_order": "网格阶次",
    "reinitialize_per_iter": "重新划分网格间隔",
    "thickness": "壳层厚度",
    "num_layers": "壳层层数",
    "part_name": "设计 Part",
    "model_directory": "TorchFEA 模型目录",
    "model_filename": "TorchFEA 模型文件",
    "num_process": "进程数",
    "gpus": "GPU 设备",
    "task_index_list": "工况任务分组",
    "normalize_gradient": "梯度归一化",
    "scale": "缩放系数",
    "min_distance": "表面间最小距离矩阵",
    "radius": "半径",
    "height": "高度",
    "bottom": "底部位置",
    "surf_idx": "表面索引",
    "weight": "权重",
    "margin": "边界余量",
    "margin_ratio": "边界余量比例",
    "p": "惩罚指数 p",
    "penalty_scale": "惩罚缩放系数",
    "volfrac_min": "最小体积分数",
    "volfrac_max": "最大体积分数",
    "penalty": "惩罚系数",
    "xmin": "最小值",
    "xmax": "最大值",
    "threshold": "阈值",
    "code": "等式约束代码",
}

_FIELD_DOCS_ZH = {
    "r0": "初始构型的内/外半径。",
    "length": "圆柱沿 Z 轴的长度。",
    "seed_size": "该表面的网格种子尺寸。",
    "num_U_ratio": "U 方向控制网格比例。",
    "num_V_ratio": "V 方向控制网格比例。",
    "degree": "B 样条阶次。",
    "init_location": "表面的初始偏移位置。",
    "maxR": "每次迭代允许的最大半径变化。",
    "maxC": "每次迭代允许的最大控制点变化。",
    "MaxC": "每次迭代允许的最大控制点变化。",
    "maxFF": "每次迭代允许的最大形状因子变化。",
    "perturbation_L": "初始缺陷波长；小于等于 0 表示不添加缺陷。",
    "path_stl": "STL 曲面文件路径。",
    "instance_name": "载荷作用的实体名称。",
    "instance_name1": "第一个实体名称。",
    "instance_name2": "第二个实体名称。",
    "surface_name": "实体上的表面集名称。",
    "surface_name1": "第一个实体上的表面集名称。",
    "surface_name2": "第二个实体上的表面集名称。",
    "set_nodes_name": "实体上的节点集名称。",
    "rp_name": "由参考点接口创建的参考点名称。",
    "rp_name1": "第一个参考点名称。",
    "rp_name2": "第二个参考点名称。",
    "rp_location": "参考点坐标。",
    "element_name": "单元类型名称。",
    "elementname": "单元类型名称。",
    "shell_elementname": "壳层单元类型名称。",
    "obj_name": "被约束对象的名称。",
    "s": "自由度编号。",
    "obj_type": "被约束对象的类型。",
    "penalty_threshold_h": "罚函数阈值。",
    "mu": "剪切模量。",
    "kappa": "体积模量。",
    "density": "质量密度。",
    "mumax": "最大剪切模量。",
    "kappamax": "最大体积模量。",
    "simp_ratio_min": "密度场允许的最小比例。",
    "bounding_box": "设计域边界框 [xmin, xmax, ymin, ymax, zmin, zmax]。",
    "simp_field_resolution": "密度场分辨率。",
    "initial_ratio": "密度场初始比例。",
    "voidpenalfactor": "空域惩罚因子。",
    "materialpenalty": "材料惩罚指数。",
    "shell_mu": "壳层剪切模量。",
    "shell_kappa": "壳层体积模量。",
    "shell_density": "壳层质量密度。",
    "fea_seed_size": "全局 Gmsh 网格种子尺寸。",
    "mesh_order": "网格阶次。",
    "reinitialize_per_iter": "每隔多少次迭代重新生成网格。",
    "thickness": "内表面的偏置壳层厚度。",
    "num_layers": "壳层中的 C3D6 楔形单元层数。",
    "part_name": "承载 SIMP 设计材料场的 TorchFEA Part。",
    "model_directory": "监视 torchfea-ui 模型导出的目录。",
    "model_filename": "目录中当前链接的 TorchFEA .npz 模型。",
    "num_process": "FEA 求解进程数。",
    "gpus": "GPU 编号列表；为空时使用 CPU。",
    "task_index_list": "将载荷工况分配到进程的分组；为空时自动分配。",
    "normalize_gradient": "是否对材料梯度进行归一化。",
    "scale": "目标项的缩放系数。",
    "min_distance": "表面两两之间的最小距离矩阵。",
    "radius": "圆柱或半径约束的半径。",
    "height": "圆柱包络高度。",
    "bottom": "圆柱包络底部位置。",
    "surf_idx": "参与目标或约束的表面索引。",
    "weight": "目标项权重。",
    "margin": "曲率约束边界余量。",
    "margin_ratio": "曲率约束边界余量比例。",
    "p": "惩罚指数。",
    "penalty_scale": "惩罚项缩放系数。",
    "volfrac_min": "允许的最小体积分数。",
    "volfrac_max": "允许的最大体积分数。",
    "penalty": "体积分数偏差的惩罚系数。",
    "xmin": "允许的最小密度值。",
    "xmax": "允许的最大密度值。",
    "threshold": "密度阈值。",
    "code": "在每次几何变量更新后执行的曲面等式约束代码。",
}


def _contains_chinese(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


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
    # Most schemas are keyed by backend names.  Keep those names as the
    # English text, but provide a centralized Chinese label/tooltip whenever
    # a field declaration did not already supply localized text.
    label_zh = label if _contains_chinese(label) else _FIELD_LABELS_ZH.get(key, label)
    label_en_value = label_en if label_en is not None else (
        label if label_zh != label else None)
    doc_zh = doc if _contains_chinese(doc) else _FIELD_DOCS_ZH.get(key, doc)
    doc_en_value = doc_en if doc_en is not None else (
        doc if doc_zh != doc else None)
    spec = {
        "key": key, "label": label_zh, "type": typ, "default": default,
        "doc": doc_zh, "choices": choices, "size": size,
        "min": minimum, "max": maximum,
    }
    if label_en_value is not None:
        spec["label_en"] = label_en_value
    if doc_en_value is not None:
        spec["doc_en"] = doc_en_value
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
        "label": "初始构型：B样条圆柱面",
        "label_en": "Initial configuration: B-spline cylinder",
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
        "label": "初始构型参数化圆柱面（控制点模型）",
        "label_en": "Initial parametric cylinder (control-point model)",
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
        "label": "初始构型参数化球面（控制点模型）",
        "label_en": "Initial parametric sphere (control-point model)",
        "factory": "CPGEO.initialize_Sphere",
        "params": fields_from_specs([
            fld("r0", "Radius r0", "float", 7.0, "Initial radius.", minimum=0.0),
            fld("seed_size", "Seed size", "float", 1.5, "Mesh seed size.", minimum=1e-4),
            fld("init_location", "init_location", "vec3", v3(), "Center of the sphere."),
            fld("MaxC", "MaxC", "float", 1.0, "Max control change.", minimum=0.0),
        ]),
    },
    "fixed_stl": {
        "label": "初始构型：固定 STL 曲面",
        "label_en": "Initial configuration: fixed STL surface",
        "factory": None,  # FixedSurface.initialize_from_stl_file(path_stl)
        "params": fields_from_specs([
            fld("path_stl", "STL file", "file", "", "Path to an STL surface."),
        ]),
    },
}

# --------------------------------------------------------------------------
# loads / BC / contact: interface type -> schema
# num_values = number of per-step amplitude values the interface carries
# --------------------------------------------------------------------------

def _surf_interfacedoc() -> str:
    return "Surface set on the instance (auto: surface_0_All, surface_1_All, ...)."


INTERFACE_TYPES: dict[str, dict] = {
    "Pressure": {
        "label": "气压 (Pressure)",
        "label_en": "Surface pressure (Pressure)",
        "num_values": 1,
        "name_hint": "pressure_",
        "params": [
            fld("instance_name", "Instance", "combo", "final_model", choices=[]),
            fld("surface_name", "Surface", "combo", "surface_1_All", _surf_interfacedoc(),
                choices=[]),  # choices filled dynamically by UI
        ],
    },
    "ConcentratedForce": {
        "label": "参考点集中力 (ConcentratedForce)",
        "label_en": "Concentrated force at RP (ConcentratedForce)",
        "num_values": 3,
        "name_hint": "force_",
        "params": [fld("rp_name", "Reference point", "combo", "", "RP created by a ReferencePoint interface.", choices=[])],
    },
    "ConcentratedMoment": {
        "label": "参考点集中力矩 (ConcentratedMoment)",
        "label_en": "Concentrated moment at RP (ConcentratedMoment)",
        "num_values": 3,
        "name_hint": "moment_",
        "params": [fld("rp_name", "Reference point", "combo", "", "RP created by a ReferencePoint interface.", choices=[])],
    },
    "Bodyforce": {
        "label": "体力 (Bodyforce)",
        "label_en": "Body force (Bodyforce)",
        "num_values": 3,
        "name_hint": "body_",
        "params": [
            fld("element_name", "Element", "combo", "C3D4", "", choices=["C3D4", "C3D8", "C3D10", "C3D6", "C3D20"]),
            fld("instance_name", "Instance", "combo", "final_model", choices=[]),
        ],
    },
    "SpringToGround": {
        "label": "接地弹簧 (SpringToGround)",
        "label_en": "Spring to ground (SpringToGround)",
        "num_values": 5,
        "name_hint": "spring_",
        "params": [fld("rp_name", "Reference point", "combo", "", "", choices=[])],
    },
    "SpringBetweenRPs": {
        "label": "参考点间弹簧 (SpringBetweenRPs)",
        "label_en": "Spring between RPs (SpringBetweenRPs)",
        "num_values": 2,
        "name_hint": "spring_",
        "params": [fld("rp_name1", "RP 1", "combo", "", "", choices=[]),
                  fld("rp_name2", "RP 2", "combo", "", "", choices=[])],
    },
    "PenaltyDoF": {
        "label": "自由度罚约束 (PenaltyDoF)",
        "label_en": "Penalty DOF constraint (PenaltyDoF)",
        "num_values": 2,
        "name_hint": "lock_",
        "params": [fld("obj_name", "Object", "str", ""),
                  fld("s", "DoF", "int", 0),
                  fld("obj_type", "obj_type", "combo", "auto", "", choices=["auto", "node", "element", "part"])],
    },
    "BoundaryCondition": {
        "label": "位移边界条件 (BoundaryCondition)",
        "label_en": "Displacement boundary condition (BoundaryCondition)",
        "num_values": 0,
        "name_hint": "bc_",
        "params": [
            fld("instance_name", "Instance", "combo", "final_model", choices=[]),
            fld("set_nodes_name", "Node set", "combo", "surface_0_Bottom", "", choices=[]),
            fld("index_dof", "固定自由度 index_dof", "dofs", [0, 1, 2],
                "勾选要固定的自由度 (X,Y,Z,Rx,Ry,Rz).", size=6,
                label_en="Fixed DOFs (index_dof)",
                doc_en="Check DOFs to fix (X, Y, Z, Rx, Ry, Rz)."),
        ],
    },
    "BoundaryConditionRP": {
        "label": "参考点边界条件 (BoundaryConditionRP)",
        "label_en": "Boundary condition at RP (BoundaryConditionRP)",
        "num_values": 0,
        "name_hint": "bc_rp_",
        "params": [fld("rp_name", "Reference point", "combo", "", "", choices=[]),
                  fld("index_dof", "固定自由度 index_dof", "dofs", [0, 1, 2],
                      "勾选要固定的自由度 (X,Y,Z,Rx,Ry,Rz).", size=6,
                      label_en="Fixed DOFs (index_dof)",
                      doc_en="Check DOFs to fix (X, Y, Z, Rx, Ry, Rz).")],
    },
    "Couple": {
        "label": "参考点-表面耦合 (Couple)",
        "label_en": "RP-surface coupling (Couple)",
        "num_values": 0,
        "name_hint": "couple_",
        "params": [
            fld("rp_name", "Reference point", "combo", "", "", choices=[]),
            fld("instance_name", "Instance", "combo", "final_model", choices=[]),
            fld("set_nodes_name", "Node set", "combo", "surface_0_Head", "", choices=[]),
        ],
    },
    "ReferencePoint": {
        "label": "参考点 (ReferencePoint)",
        "label_en": "Reference point (ReferencePoint)",
        "num_values": 0,
        "name_hint": "RP_",
        "params": [fld("rp_location", "RP location", "vec3", v3(), "Reference point position.")],
    },
    "Contact": {
        "label": "接触对 (Contact)",
        "label_en": "Contact pair (Contact)",
        "num_values": 0,
        "name_hint": "contact_",
        "params": [
            fld("instance_name1", "Instance 1", "combo", "final_model", choices=[]),
            fld("surface_name1", "Surface 1", "combo", "", "可下拉选择或手输另一部件的表面集。", choices=[],
                doc_en="Select or type a surface set of another part."),
            fld("instance_name2", "Instance 2", "combo", "", choices=[]),
            fld("surface_name2", "Surface 2", "combo", "", "可下拉选择或手输表面集。", choices=[],
                doc_en="Select or type a surface set."),
            fld("penalty_threshold_h", "penalty_threshold_h", "float", 3.0),
        ],
    },
    "ContactSelf": {
        "label": "自接触 (ContactSelf)",
        "label_en": "Self contact (ContactSelf)",
        "num_values": 0,
        "name_hint": "contact_self_",
        "params": [
            fld("instance_name", "Instance", "combo", "final_model", choices=[]),
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
        "label": "均质超弹性材料 (HomogeneousMaterial)",
        "label_en": "Homogeneous hyperelastic material (HomogeneousMaterial)",
        "params": [
            fld("mu", "mu", "float", 0.482, "Shear modulus."),
            fld("kappa", "kappa", "float", 4.8, "Bulk modulus."),
            fld("density", "density", "float", 1.08e-9, "Mass density."),
            fld("elementname", "Element", "combo", "C3D4", "", choices=["C3D4", "C3D8", "C3D10", "C3D20"]),
        ],
    },
    "SIMP_BSPFieldMaterials": {
        "label": "SIMP B样条密度场材料 (SIMP_BSPFieldMaterials)",
        "label_en": "SIMP B-spline density-field material (SIMP_BSPFieldMaterials)",
        "params": [
            fld("part_name", "Design Part", "combo", "", "Part carrying the SIMP design field.", choices=[]),
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
            fld("elementname", "Element", "combo", "C3D4", "", choices=["C3D4", "C3D8", "C3D10", "C3D20"]),
        ],
    },
    "CodesignMaterials": {
        "label": "协同设计材料 · SIMP 体+壳 (CodesignMaterials)",
        "label_en": "Co-design material · SIMP solid + shell (CodesignMaterials)",
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
            fld("elementname", "Solid element", "combo", "C3D4", "", choices=["C3D4", "C3D8", "C3D10", "C3D20"]),
            fld("shell_mu", "shell mu", "float", 0.48),
            fld("shell_kappa", "shell kappa", "float", 4.8),
            fld("shell_density", "shell density", "float", 1.08e-9),
            fld("shell_elementname", "Shell element", "combo", "C3D6", "", choices=["C3D6"]),
        ],
    },
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
    # SIMP uses its dedicated TorchFEA model-directory editor.
    "simp": [],
}

# --------------------------------------------------------------------------
# solver / updater generic fields
# --------------------------------------------------------------------------

SOLVER_FIELDS: list[dict] = fields_from_specs([
    fld("num_process", "Processes", "int", 4, "Number of FEA solver processes.", minimum=1),
    fld("gpus", "GPU devices", "vecN", [], "List of gpu ids, e.g. ['cuda:0'] or empty for cpu."),
    fld("task_index_list", "task_index_list", "vecN", [], "Partition of load steps over processes (empty = auto)."),
])

# Code slots (Python fields) rendered with the code editor.  Surface equality
# is intentionally not a GeometryNode code slot; it is an updater equality
# item whose body is stored in ``params['code']``.
CODE_SLOT_KEYS = ("map_bsp_designfield", "objective_function", "get_metrics")

# --------------------------------------------------------------------------
# updater: structured objective / constraint catalogues (UI chooser, no code)
# group: which sub-optimizer the term belongs to; gen: code template using
# {param} placeholders replaced by repr() of the stored value.
# --------------------------------------------------------------------------

def _mat2d(d: Any) -> Any:
    """default for a 2-D python-literal matrix field"""
    return d


UPDATER_OBJECTIVES: dict[str, dict] = {
    "ShapeDerivative": {
        "label": "结构灵敏度 (ShapeDerivative)",
        "label_en": "Structural sensitivity (ShapeDerivative)",
        "group": "geometry", "schemes": ["shapeopt", "codesign"],
        "gen": "self.objectivefuncs.ShapeDerivative()", "params": [],
    },
    "Sensitivity": {
        "label": "材料灵敏度 (Sensitivity)",
        "label_en": "Sensitivity (linear material-sensitivity term)",
        "group": "materials", "schemes": ["simp", "codesign"],
        "gen": "self.objectivefuncs.Sensitivity(normalize_gradient={normalize_gradient})",
        "params": [fld("normalize_gradient", "normalize_gradient", "bool", False)],
    },
    "DensityFieldMinimize": {
        "label": "密度场正则化 (DensityFieldMinimize)",
        "label_en": "Density field regularization (DensityFieldMinimize)",
        "group": "materials", "schemes": ["simp", "codesign"],
        "gen": "self.objectivefuncs.DensityFieldMinimize(scale={scale})",
        "params": [fld("scale", "scale", "float", 1e-7)],
    },
}

_EQUALITY_CODE_FIELD = fld(
    "code", "等式约束代码", "code", "",
    "每次几何变量更新后执行，用于投影/修正曲面控制点。",
    label_en="Equality-constraint code",
    doc_en="Runs after each geometry update to project or correct "
           "surface control points.")

EQUALITY_CONSTRAINTS: dict[str, dict] = {
    "MirrorSymmetry": {
        "label": "镜面对称",
        "label_en": "Mirror symmetry",
        "group": "geometry", "schemes": ["shapeopt", "codesign"],
        "special": "surface_equality",
        "params": [_EQUALITY_CODE_FIELD],
    },
    # Generic entry retained for custom/legacy definitions.  New templates
    # use the named MirrorSymmetry template above.
    "SurfaceEquality": {
        "label": "自定义曲面等式约束 (SurfaceEquality)",
        "label_en": "Custom surface equality constraint (SurfaceEquality)",
        "group": "geometry", "schemes": ["shapeopt", "codesign"],
        "special": "surface_equality",
        "params": [_EQUALITY_CODE_FIELD],
    },
}

UPDATER_CONSTRAINTS: dict[str, dict] = {
    "Fairness": {
        "label": "表面曲率正则化 (Fairness)",
        "label_en": "surface-curvature regularization (Fairness)",
        "group": "geometry", "schemes": ["shapeopt", "codesign"],
        "gen": "self.objectivefuncs.Fairness(surfaces=params.geometry)", "params": [],
    },
    "Distance": {
        "label": "表面间最小距离约束 (Distance)",
        "label_en": "minimum inter-surface distance constraint (Distance)",
        "group": "geometry", "schemes": ["shapeopt", "codesign"],
        "gen": "self.objectivefuncs.Distance(min_distance={min_distance})",
        "params": [fld("min_distance", "min_distance [[i][j]]", "mat",
                      [[2.5, 2.5], [2.5, 2.5]])],
    },
    "Cylinder": {
        "label": "最大圆柱包络约束 (Cylinder)",
        "label_en": "maximum cylindrical envelope constraint (Cylinder)",
        "group": "geometry", "schemes": ["shapeopt", "codesign"],
        "gen": "self.objectivefuncs.boundarys.Cylinder(radius={radius}, height={height}, bottom={bottom})",
        "params": [fld("radius", "radius", "float", 10.0),
                  fld("height", "height", "float", 80.0),
                  fld("bottom", "bottom", "float", 0.0)],
    },
    "MinRadius": {
        "label": "最小半径约束 (MinRadius)",
        "label_en": "minimum-radius constraint (MinRadius)",
        "group": "geometry", "schemes": ["shapeopt", "codesign"],
        "gen": "self.objectivefuncs.boundarys.MinRadius(radius={radius})",
        "params": [fld("radius", "radius", "float", 2.0)],
    },
    "VolumeMaximization": {
        "label": "腔体体积最大化 (VolumeMaximization)",
        "label_en": "cavity-volume maximization (VolumeMaximization)",
        "group": "geometry", "schemes": ["shapeopt", "codesign"],
        "gen": "self.objectivefuncs.VolumeMaximization(geometryparam=self.params_update, surf_idx={surf_idx}, weight={weight})",
        "params": [fld("surf_idx", "surf_idx", "int", 1, minimum=1),
                  fld("weight", "weight", "float", 1e-2)],
    },
    "InwardCurvatureRadius": {
        "label": "内曲率半径约束 (InwardCurvatureRadius)",
        "label_en": "inward curvature radius constraint (InwardCurvatureRadius)",
        "group": "geometry", "schemes": ["codesign"],
        "gen": ("morphopt.codesign.InwardCurvatureRadius(geometry=params.geometry, "
                "margin={margin}, margin_ratio={margin_ratio}, p={p}, penalty_scale={penalty_scale})"),
        "params": [fld("margin", "margin", "float", 0.4),
                  fld("margin_ratio", "margin_ratio", "float", 0.45),
                  fld("p", "p", "int", 8, minimum=1),
                  fld("penalty_scale", "penalty_scale", "float", 1e3)],
    },
    "OffsetSurfaceMinThickness": {
        "label": "偏置后表面最小厚度约束 (OffsetSurfaceMinThickness)",
        "label_en": "minimum thickness constraint for offset surfaces (OffsetSurfaceMinThickness)",
        "group": "geometry", "schemes": ["codesign"],
        "gen": "morphopt.codesign.OffsetSurfaceMinThickness(geometry=params.geometry, min_distance={min_distance})",
        "params": [fld("min_distance", "min_distance", "float", 2.0)],
    },
    "VolFrac": {
        "label": "体积分数约束 (VolFrac)",
        "label_en": "volume-fraction band constraint (VolFrac)",
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
        "label": "最小密度约束 (MinValue)",
        "label_en": "minimum density constraint (MinValue)",
        "group": "materials", "schemes": ["simp", "codesign"],
        "gen": "self.objectivefuncs.boundarys.MinValue(xmin={xmin}, threshold={threshold}, p={p})",
        "params": [fld("xmin", "xmin", "float", -15.0),
                  fld("threshold", "threshold", "float", 0.0),
                  fld("p", "p", "int", 2, minimum=1)],
    },
    "MaxValue": {
        "label": "最大密度约束 (MaxValue)",
        "label_en": "maximum density constraint (MaxValue)",
        "group": "materials", "schemes": ["simp", "codesign"],
        "gen": "self.objectivefuncs.boundarys.MaxValue(xmax={xmax}, threshold={threshold}, p={p})",
        "params": [fld("xmax", "xmax", "float", 15.0),
                  fld("threshold", "threshold", "float", 0.0),
                  fld("p", "p", "int", 2, minimum=1)],
    },
}

UPDATER_CATALOG = {"objectives": UPDATER_OBJECTIVES, "constraints": UPDATER_CONSTRAINTS}


def equality_constraint_specs(scheme: str) -> list[dict]:
    """Return equality-constraint templates available for a scheme."""
    out = []
    for name, spec in EQUALITY_CONSTRAINTS.items():
        if scheme in spec["schemes"]:
            item = dict(spec)
            item["_type"] = name
            out.append(item)
    return out


def equality_constraint_defaults(item_type: str) -> dict:
    """Return defaults for one equality-constraint template."""
    spec = EQUALITY_CONSTRAINTS.get(item_type)
    if spec is None:
        return {}
    return clone_defaults(spec["params"])


def equality_constraint(item_type: str, **overrides) -> dict:
    """Build one equality-constraint item from the template catalogue."""
    spec = EQUALITY_CONSTRAINTS[item_type]
    params = equality_constraint_defaults(item_type)
    params.update(overrides)
    return {"type": item_type, "params": params}


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


def geometry_updater_config(max_step_iter: int = 50,
                            if_update: Optional[list] = None,
                            objective_functions: tuple = (),
                            constraints: tuple = (),
                            code: str = "",
                            equality_constraints: tuple = ()) -> dict:
    """Config with one geometry equality item and penalty-constraint list."""
    return {
        "max_step_iter": int(max_step_iter),
        "if_update": list(if_update) if if_update is not None else [],
        "objective_functions": list(objective_functions),
        "constraints": list(constraints),
        "equality_constraints": list(equality_constraints),
        "code": code,
    }


def materials_updater_config(max_step_iter: int = 50,
                             if_update: Any = True,
                             objective_functions: tuple = (),
                             constraints: tuple = (),
                             code: str = "") -> dict:
    """Config dict of the material sub-updater (penalty constraints only)."""
    return {
        "max_step_iter": int(max_step_iter),
        "if_update": if_update,
        "objective_functions": list(objective_functions),
        "constraints": list(constraints),
        "code": code,
    }


def surface_spec(surface_type: str) -> dict:
    return SURFACE_TYPES[surface_type]


def interface_spec(interface_type: str) -> dict:
    return INTERFACE_TYPES[interface_type]


def material_spec(material_type: str) -> dict:
    return MATERIAL_TYPES[material_type]
