# MorphOpt UI 代码设计规范

> 本文档定义 `src/morphopt/ui/` 的分层、任务树节点体系、变量/函数命名、复用、
> 运行时边界与代码生成契约。修改 UI 相关代码前请先读本文，保持整体风格一致。

---

## 1. 分层总览

```
src/morphopt/ui/
├── __init__.py             # 仅公开 run_app；不在导入时创建 Qt 对象
├── __main__.py             # `python -m morphopt.ui`；只委托给 app.main
├── app.py                  # QApplication 生命周期、进程环境与全局主题
├── mainwindow.py           # 应用组合根：在定义页与观察页之间导航
├── i18n.py                 # 无业务状态的中英文本选择与语言控件
├── model/                 # 数据模型（无 Qt 依赖，可单测）
│   ├── problem.py         # 任务树节点体系：Node + 显式类型化节点 + ProblemDefinition
│   ├── schemas.py         # 字段/控件/后端类型目录 + 默认字段值 + updater 项/配置工厂
│   └── loaders.py         # *.morph 存取（JSON 序列化）
├── schemes/               # 每种优化方案一个模板类（任务树“形状”的唯一来源）
│   ├── base.py            # SchemeTemplate + 共享 make_* 分区构建器
│   ├── snippets.py        # 与方案无关的 FEA 代码片段及参数声明
│   ├── shapeopt.py        # 形状优化模板
│   ├── simp.py            # 拓扑/材料场优化模板
│   └── codesign.py        # 协同设计优化模板
├── codegen/generator.py   # 由 ProblemDefinition 渲染可运行的 morphopt 模块
├── widgets/               # Qt 视图层：模型树 / 属性编辑器 / 步矩阵 / updater 编辑器 …
│   ├── observation_pages.py # 观察器的指标、几何与工况展示页（不管理进程）
│   └── template_insert_dialog.py # 代码片段参数选择
├── workbench.py            # 优化问题定义页：组合 widgets，发出意图信号
├── observe_panel.py        # 应用内观察/运行页：协调 launcher 与结果展示
└── launcher.py             # 无 Qt 的导出、启动、继续、停止和结果目录辅助函数
```

**依赖方向（禁止反向）**：`widgets` → `schemes`/`model`；`schemes` → `model`；
`codegen` → `schemes`/`model`；`workbench` → `widgets`/`model`；
`mainwindow` → `workbench`/`observe_panel`。`model/` 和 `launcher.py` 不 import
任何 Qt 视图模块。

### 1.1 `schemas.py` 与 `schemes/` 的边界

| 位置 | 回答的问题 | 应放内容 | 不应放内容 |
|------|------------|----------|------------|
| `model/schemas.py` | “一种节点/字段如何编辑和生成？” | surface、interface、material、geometry、solver、updater 的字段规格、默认字段值、控件类型、后端工厂/生成片段 | 某个优化方案的默认曲面/载荷树、方案名称、代码片段库 |
| `schemes/<name>.py` | “某种优化问题初始长什么样？” | `label` / `label_en` / `MATERIAL_TYPE`、后端 `BASES`、`build_root()`、该方案的默认代码槽 | 可由所有方案复用的字段定义或 FEA 数据提取代码 |
| `schemes/snippets.py` | “用户可插入哪些通用 FEA 数据访问代码？” | 不依赖单个方案的 `CodeSnippet`、`SnippetParameter`、渲染逻辑，以及所有 UI 名称的 `name_zh` / `name_en` | Qt 对话框、问题树默认值、具体论文的目标函数 |

判断方式：新增字段/控件先改 `schemas.py`；调整某方案初始树或后端类改对应
`schemes/<name>.py`；新增可组合的编辑器插入片段改 `schemes/snippets.py`。

### 1.2 应用壳层职责

- `app.main()` 是唯一创建 `QApplication`、设置全局样式、进入事件循环的入口；
  `__main__.py` 和 `run_app()` 只能委托给它，不能复制初始化逻辑。
- `MainWindow` 只负责装配、页面导航、文件对话框和用户确认。它通过 `Workbench` 的
  意图信号调用打开/导出/切换问题，不把表单编辑逻辑放进窗口类。
- `Workbench` 只拥有定义页的短生命周期 UI 状态；`ProblemDefinition` 才是唯一的
  可保存业务状态。它将“进入观察器”的完整 definition 通过信号交给上层。
- `observe_panel.py` 负责运行时进程、轮询与展示；进程树的启动/停止和脚本导出必须
  走 `launcher.py`，不得在 Qt 槽函数里复制 `subprocess` 逻辑。
- 不保留独立 `monitor` 窗口或 `taskui` 兼容层。结果观察一律由
  `ObserverControls` / `ObserverPanel` 完成；指标、几何和工况视图放在
  `widgets/observation_pages.py`，只渲染已给定的结果，不管理进程或页面导航。

**核心约定**：任务树**只用显式类型节点构建**，禁止用手写 dict + 魔法 kind 字符串拼树；
dict 仅存在于“叶子参数”（字段值）和 updater 配置的内部结构。

---

## 2. 任务树节点体系（model/problem.py）

模型层保存的是一棵固定的、有序的树，根为 `ProblemNode`，直接子节点为七个分区：

```
problem (ProblemNode)
├── geometry  (GeometryNode)     children: SurfaceNode*（0 = 外表面, 1.. = 内腔）
├── loads     (LoadsNode)        children: InterfaceNode*（BC/RP/力/力矩/接触…）
├── steps     (StepsNode)
├── material  (MaterialNode)
├── objective (ObjectiveNode)
├── solver    (SolverNode)
└── updater   (UpdaterNode)      .geometry / .materials = 配置 dict
```

这是持久化模型的结构，不等同于左侧 Qt 任务树的视觉分组。任务树为了便于
理解和操作，会把 `loads` 与 `steps` 合并显示为：

```
载荷 (FEAParams)
├── 载荷定义 (define_interface)  -> LoadsNode / InterfaceNode*
└── 载荷工况 (define_steps)      -> StepsNode
```

同理，`ObjectiveNode` 在任务树中挂在 `优化问题定义 (Updater)` 下，和
`几何优化器 (UpdaterGeometries)`、`材料优化器 (UpdaterMaterials)` 并列。
唯一的等式约束、罚函数约束和子优化目标函数挂在对应的几何/材料优化器下面；优化器节点
本身只编辑最大迭代次数与曲面更新开关，子节点分别显示自己的内容。实际数据仍由
`ProblemDefinition.objective` 和 `ProblemDefinition.updater` 持有。

对应的视觉结构为：

```
优化问题定义 (Updater)
├── 优化目标 (ObjectiveFunction)
├── 几何优化器 (UpdaterGeometries)
│   ├── 子优化目标函数 (UpdaterGeometries)
│   ├── 几何等式约束（单个代码框）(UpdaterGeometries)
│   └── 几何罚函数约束 (UpdaterGeometries)
└── 材料优化器 (UpdaterMaterials)       # 仅 codesign 等启用材料更新的方案
    ├── 子优化目标函数 (UpdaterMaterials)
    └── 材料罚函数约束 (UpdaterMaterials)
```

任务树节点标题中的括号只保留生成代码的最后一级类名或方法名，例如
`GeometryParams`、`FEAParams`、`UpdaterGeometries`；括号不是英文翻译。临时的
视觉分组节点不得写回 `ProblemNode` 或 `.morph` 文件。

| 类型化类          | kind 常量        | 关键访问器 / 工厂                                        |
|-------------------|------------------|----------------------------------------------------------|
| `ProblemNode`     | `KIND_PROBLEM`   | `add_section()`, `section(kind)`, `sections()`           |
| `GeometryNode`    | `KIND_GEOMETRY`  | `add_surface()`, `surfaces()`, `surface_count()`, `index_of_surface()` |
| `SurfaceNode`     | `KIND_SURFACE`   | `SurfaceNode.create(type, index, **overrides)`; `.surface_type`, `.is_inner` |
| `LoadsNode`       | `KIND_LOADS`     | `add_interface()`, `interfaces()`                        |
| `InterfaceNode`   | `KIND_INTERFACE` | `InterfaceNode.create(type, name, **overrides)`; `.interface_type` |
| `StepsNode`       | `KIND_STEPS`     | `.num_steps`, `.step_values`                             |
| `MaterialNode`    | `KIND_MATERIAL`  | `MaterialNode.create(type, **overrides)`; `.material_type` |
| `ObjectiveNode`   | `KIND_OBJECTIVE` | `.objective_body`, `.metrics_body`, `.jacobian_needed`   |
| `SolverNode`      | `KIND_SOLVER`    | —                                                        |
| `UpdaterNode`     | `KIND_UPDATER`   | `.geometry_config()`, `.materials_config()`              |

规则：

1. `kind` 是**类属性常量**，不是随手传的字符串。定义新分区必须先在
   `problem.py` 加 `KIND_*` 常量 + 子类 + 注册进 `NODE_TYPES`。
2. **参数是构造函数里显式声明的真实成员变量**：每个节点类把它的每个参数在
   `__init__` 中逐个写成带类型注解的属性（如 `self.num_steps: int`、
   `self.fea_seed_size: Optional[float]`、`SurfaceNode.r0: Optional[float]`）。
   禁止用 dict / tuple / 动态 setattr 来“定义”属性——属性就是 `__init__` 里
   写出来的那几行，便于维护与自动补全。代码槽这类自由文本也存为私有属性，用公开
   property 暴露（如 `ObjectiveNode.objective_body` ↔ `_objective_function`）。
3. 除 `UpdaterNode.geometry/materials` 的**结构化 updater 配置**外，模型里没有 dict
   参数存储（没有 `params` / `_ParamsView` / raw 兜底）。
   每个类用类常量 `_FIELDS` 只“枚举字段名”用于：磁盘 `*.morph` 的 `params`
   映射（由 `to_dict()` → `field_items()` 生成；`from_dict` 把映射喂回 `__init__`
   还原属性）和动态表单/代码生成的按键访问 `get_field() / set_field()`。属性本身
   完全由 `__init__` 定义；`None` 视为未设置、不写盘。schema 叶节点（surface /
   interface / material）以“各类型字段的并集”形式在 `__init__` 中显式声明，只有
   该 `type` 用到的字段有值。
4. 类型化 `create()` 从 `schemas` 目录填充默认参数并对未知字段名**抛错**，
   拼写错误在构建时立刻暴露，不会静默进入生成代码。
5. 存取格式不变：`to_dict()`/`Node.from_dict()` 保留 kind，加载时按 kind 还原成对应
   类型化节点（round-trip lossless）。**老 `.morph` 文件无需迁移**。
6. `SurfaceNode` 不存 index：表面在 `GeometryNode.children` 中的**位置即索引**
   （0 = outer，flip 由 index>0 推导）。所有结构编辑必须走 `ProblemDefinition`：
   `add_surface()` / `clone_surface()` / `remove_surface()` / `move_surface()`，以及
   `add_interface()` / `clone_interface()` / `remove_interface()` /
   `rename_interface()` / `move_interface()`。这些方法是维护 `flip`、updater 的
   `if_update` / `Distance.min_distance`、步矩阵及 `jacobian_needed` 引用的唯一位置。`jacobian_needed`
   只能引用 `ProblemDefinition.amplitude_interfaces()` 返回的接口：即 schema 中 `num_values > 0`、会成为
   载荷工况矩阵列的参数载荷。目标编辑器应使用多选下拉展示该列表，不能要求用户手写名称。
   加载旧文件后调用 `align_surface_dependent_state()` 修复尺寸不一致的 updater 状态。

**读节点**：用 `ProblemDefinition` 的类型化访问器
`problem.geometry / .loads / .steps / .material / .objective / .solver / .updater`，
以及 `problem.surfaces()` / `problem.interfaces()`。不要在新增代码里用
`problem.node("geometry")` 这种魔法字符串查树（旧代码保留仅为兼容，逐步迁移）。

---

## 3. 方案模板规范（schemes/*）

- 每种优化方案 = `schemes/` 下一个继承 `SchemeTemplate` 的类（如
  `ShapeoptTemplate`）。这是该任务树“形状”的唯一来源。
- 类内用**声明式数据**描述差异，不要手写长 dict：

  ```python
  class SomeTemplate(SchemeTemplate):
      scheme = "some"
      label = "某种优化 (some)"
      label_en = "Some optimization (some)"
      MATERIAL_TYPE = "SomeMaterial"
      geometry_title = "Geometry (...)"          # 树里几何分区的显示标题
      BASES = {...}                              # 生成代码用的后端类名映射
      def default_apply_surface_constraints(self) -> str: ...  # MirrorSymmetry default
      def default_objective_slot(self) -> str: ...
      def default_metrics_slot(self) -> str: ...
      def default_map_bsp_designfield(self) -> str: ...
  ```

- `build_root()` 只做一件事：**按固定顺序用共享 `make_*` 组装分区并挂到 root**。
  分区内差异参数用“具名覆写”表达，禁止出现 `Node("...", params={...})` 或大段
  `node.params.update({...})` 手拼。

  ```python
  def build_root(self) -> Node:
      root = ProblemNode()
      geometry = self.make_geometry(fea_seed_size=1.0)
      geometry.add_surface(self.make_surface("bsp_cylinder", 0,
                                             r0=8.0, length=80.0, ...))
      root.add_section(geometry)
      loads = self.make_loads()
      loads.add_interface(self.make_interface("BoundaryCondition", "bc_fix",
                                              instance_name="final_model", ...))
      root.add_section(loads)
      root.add_section(self.make_steps(1, [{"pressure_1": [0.06]}]))
      root.add_section(self.make_material(mu=0.482, kappa=4.8, density=1.08e-9))
      root.add_section(self.make_objective())
      root.add_section(self.make_solver(num_process=4))
      root.add_section(self.make_updater(
          geometry=S.geometry_updater_config(...),
          materials=None,
      ))
      return root
  ```

- 新增一种方案 = 新增一个模板类并注册进 `base._build_registry()`；在类上声明
  `label` / `label_en` / `MATERIAL_TYPE`，并仅在需要新字段时补 `GEOMETRY_SCHEMES`。
  不要复制粘贴别的 scheme 的 `build_root`。

### 3.1 FEA 代码片段

- `schemes/snippets.py` 的 `CodeSnippet` / `SnippetParameter` 只描述所有方案都适用的
  FEA **数据提取片段**与可选参数；`SchemeTemplate.objective_code_snippets()` 仅负责公开
  该方案可用的片段。片段不得预设“尖端位移”“多工况平均值”等具体目标；用户应按问题含义
  在已插入的变量基础上自由组合、聚合并写出 `return`。
- 预设是**光标位置插入的代码片段**，绝不能通过“应用模板”清空或覆盖整个代码槽。点击按钮前
  最后聚焦的代码槽就是插入目标；若无光标则追加到 `objective_function()` 末尾。插入前由
  `TemplateInsertDialog` 从当前 `ProblemDefinition` 提供参数下拉（工况、Instance、Reference
  point、单元类型）；外部 FEA 代码新增的名称仍可手输。片段在访问 `self.fe.assembly` 前调用
  `morphopt.controller.params.feamodel.process_fea(self.fe, step_index=...)`，不依赖另一个代码槽的
  局部变量或初始化顺序。
- 共享预设只覆盖稳定的字段访问：Instance 节点位移、Reference point 位移/转角、两者的
  广义残量（参与力）、以及 Instance 某种单元在高斯点处的应变能密度和变形梯度。预设不应
  针对某个论文问题硬编码接触名称、节点集或几何常数。
- Instance 节点位移使用 `RGC = assembly._GC2RGC(GC)` 与
  `RGC[instance._RGC_index]`；该张量按节点排列，形状通常为 `[num_nodes, 3]`。Reference
  point 使用 `assembly.get_reference_point(name)`，其 RGC 段为 6 分量（平动 0..2、转角
  3..5）。广义残量/力则用 `_RGC_list_indexStart` 切出对应段；Instance 段可 `reshape(-1, 3)`，
  Reference point 段保留为 `[Fx, Fy, Fz, Mx, My, Mz]`，不要把两种量混用。
- 6×6 刚度/Jacobian 片段必须让用户选择参考点，再用
  `assembly._GC_list_indexStart[reference_point._RGC_index]` 和下一个边界定位该参考点的
  广义自由度行；禁止用 `[-6:, :]` 假设参考点恰好位于全局自由度末尾。集中力和集中力矩
  应施加在同一个参考点，并由用户手动勾选 `jacobian_needed`；插入前由对话框强制校验三者一致。
- 高斯点字段从 `instance.elems[element_name]` 取得：
  `get_potential_energy_density(U=node_displacement)` 返回 `[num_gaussian, num_elements]`，
  `get_deformation_gradient(U=node_displacement)` 返回
  `[num_gaussian, num_elements, 3, 3]`。片段只提取完整张量；用户可直接基于
  `energy_density` 或 `deformation_gradient` 自行索引、聚合并写出目标。

### 3.2 共享 `make_*` 构建器（base.py，禁止重复实现）

`SchemeTemplate` 已提供所有分区构建器，子类**只覆写差异参数**：

| 方法 | 说明 |
|------|------|
| `make_surface(type, index, **ovr)` | 按 schema 默认建 `SurfaceNode`（flip 自动）|
| `make_interface(type, name, **ovr)` | 按 schema 默认建 `InterfaceNode` |
| `make_material(**ovr)` | 用 `material_type`（scheme 决定的具体类）建 `MaterialNode` |
| `make_geometry(**ovr)` | `GEOMETRY_SCHEMES[scheme]` 默认 + 覆写 + BC 代码槽 |
| `make_loads()` | 空载荷容器 |
| `make_steps(num_steps, step_values)` | 载荷步分区 |
| `make_objective(body, metrics, jacobian_needed)` | 目标函数分区（缺省用 default_*_slot）|
| `make_solver(num_process, gpus, task_index_list)` | 求解器分区 |
| `make_updater(geometry, materials)` | updater 分区（None = 该子优化器不激活）|

### 3.3 updater 配置工厂（schemas.py，单一事实来源）

目标/罚函数约束项全部来自目录 `UPDATER_OBJECTIVES` / `UPDATER_CONSTRAINTS`；
等式约束项来自 `EQUALITY_CONSTRAINTS`。方案里声明“项”
时用目录工厂，只写**偏离默认的覆写**，默认值由目录给出（不要重新硬编码一遍默认值）：

```python
objective_functions=(S.updater_objective("ShapeDerivative"),),
equality_constraints=(  # 每个几何优化器最多一个
    S.equality_constraint("MirrorSymmetry",
                          code=self.default_apply_surface_constraints()),
),
constraints=(
    S.updater_constraint("Fairness"),
    S.updater_constraint("Distance", min_distance=[[2.5, 2.5], [2.5, 2.5]]),
    S.updater_constraint("Cylinder", radius=10.0, height=80.0, bottom=0.0),
),
```

分区配置再用 `S.geometry_updater_config(...)` / `S.materials_updater_config(...)` 封装。
几何配置包含并列的 `equality_constraints` 与 `constraints`：前者最多保存一个等式/投影约束，
后者是可包含多个小项的罚函数约束；材料配置目前只有 `constraints` 罚函数约束。`MirrorSymmetry`
是内置的镜面对称模板，`SurfaceEquality` 保留为自定义/旧文件迁移入口。等式项代码存放在
`params["code"]`，生成器把它输出为 `GeometryParams.apply_surface_constraints()`，
不会作为 `add_constraints()` 的罚函数重复注册。

新增一种目标、罚函数约束或等式约束：**只改 `schemas.py` 的对应目录项**
（`UPDATER_OBJECTIVES`、`UPDATER_CONSTRAINTS` 或 `EQUALITY_CONSTRAINTS` 的
label/gen/params），编辑器与代码生成自动跟随，不要在模板/生成器里再复制一份。

---

## 4. 命名与风格

- **变量、函数要有明确含义**。宁可长，不缩写无歧义：
  `geometry`/`loads`/`objective_body`/`min_distance`，不用 `g`/`l`/`ob`。
- 同层命名一致：分区/节点统一 `make_*`（构建）、`*_section`/`*_config`（结构描述）。
  列表用复数（`surfaces`、`interfaces`、`constraints`）。
- 魔法字符串只允许出现在“目录值”（如 `SURFACE_TYPES` 里的 `"bsp_cylinder"`）或本地
  短生命周期内；**树结构、kind、分区访问**必须走常量/类型化访问器。
- 注释用中文描述“为什么”，标识符保持英文语义化；docstring 至少说明参数与副作用。
- 重复逻辑一律提取成函数/方法（尤其跨 scheme 的默认填充与创建路径），禁止三份拷贝。
- 缩进 4 空格；行尾不留空白。

---

## 5. 代码生成契约（codegen/generator.py）

- `generate_source(problem)` 只**读取**类型化树（`problem.geometry/surfaces()/...`），
  从不修改模型；分区缺失时回退到对应的空类型节点。
- updater 的目标/约束通过目录 `gen` 模板渲染，参数值来自树上存的 `params`。
- **回归保障**：任何“把树上内容改成代码”的改动都必须保持三个默认模板生成的
  `.py` **逐字节不变**（三个 golden 基线）。验证方式：

  ```python
  from morphopt.ui.schemes.base import get_template
  from morphopt.ui.codegen.generator import generate_source
  for s in ("shapeopt", "simp", "codesign"):
      src = generate_source(get_template(s).create_problem("golden"))
      print(s, len(src), md5(src)[:10])   # 与基线对比
  ```

---

## 6. 视图层约定（widgets / workbench）

- `editor.fields_for_node(node)` 按 `node.kind` 分派渲染哪种字段/代码槽；字段列表来自
  `schemas` 目录，视图层不持有第二份字段定义。
- `ModelTree` 是结构编辑的 Qt 入口，但不直接修改 `children`、`flip`、updater dict
  或跨节点引用；它只调用 `ProblemDefinition` 的聚合操作（见第 2 节）。其他入口
  （批处理、导入器、未来的命令面板）也必须复用这些操作。
- 目标函数编辑器通过 `get_template(scheme).objective_code_snippets()` 获取 `CodeSnippet`；
  片段定义只放在 `schemes/snippets.py`，不放进 widget 或单个方案类。
- `CodeEditor` 提供零依赖基础补全：`Ctrl+Space` 手动触发，成员访问后自动触发。
  补全目录由 `widgets/code_completion.py` 集中维护；新增代码槽时传入其 model
  storage key 和当前 `ProblemDefinition`，不要在单个 editor 中硬编码候选词。
- i18n：界面文案一律 `T(zh, en)` / `pick(zh, en)`；节点名/载荷名等数据不翻译。
  字段编辑器的参数名称和提示统一由 `model/schemas.py::fld()` 生成：新字段必须
  在 `_FIELD_LABELS_ZH` / `_FIELD_DOCS_ZH` 中补齐中文，英文保留在 `label_en` /
  `doc_en`；目录项（表面、载荷、材料、updater 目标/约束）必须同时声明 `label`
  和 `label_en`。表格标题、弹窗、按钮、下拉选项等运行时文案不能直接写单语
  英文；切换语言时由各页面的 `apply_language()` 原地刷新，不能丢失当前编辑状态。

---

## 7. 改动 Checklist

改模型层：加 `KIND_*` + 子类 + `NODE_TYPES`，再决定是否暴露 `ProblemDefinition`
类型化访问器。

改方案层：加/改 template 类的声明式数据与 `default_*_slot`；用 `make_*` 重写
`build_root`；跑第 5 节 golden 回归。

改目录层（新表面/载荷/材料/约束字段）：只改 `schemas.py` 对应目录与默认值；其余层自动
跟随。改 FEA 代码片段只改 `schemes/snippets.py`；改某种优化问题的默认树、后端类或材料类型
只改对应 `schemes/<name>.py`，不要跨层复制。

改结构编辑：只扩展 `ProblemDefinition` 的聚合操作并覆盖其模型层回归；跑一次 UI
冒烟导入（`QT_QPA_PLATFORM=offscreen` 导入 `workbench/mainwindow/model_tree/...`）。

改应用壳层：确认页面间通信仍使用信号；启动/停止进程必须委托 `launcher.py`；不让
`MainWindow`、`Workbench` 或 widget 直接承担第二份运行状态。

提交前至少执行模型层回归和离屏导入检查（项目当前不要求 pytest）：

```bash
PYTHONPATH=src python -m unittest tests/ui/test_problem_definition.py -v
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python -c \
  "from morphopt.ui.mainwindow import MainWindow; from morphopt.ui.workbench import Workbench"
```
