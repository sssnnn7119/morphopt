# 11. UI 应用、模板与代码生成

返回 [设计导览](../README.md)。

## 应用服务层

源码目录：`ui/application/`。该层把领域模型、文件、生成器与运行进程组合成可由窗口调用的用例，并保持与 Qt 控件无关。

### `ProblemSession` 与 `ProblemLibrary`

源码：`application/definitions.py`。

| 类型 | 状态/公开方法 | 职责 |
|---|---|---|
| `ProblemSession` | 私有 `_problem`；`problem`、`replace()`、`synchronize()`、`source()`、`validate_for_run()`、`set_label()`、`set_result_folder()`、`set_device()`、`sync_imported_material_targets()` | 当前定义编辑会话，提供变更与运行前校验。 |
| `ProblemLibrary` | `templates()`、`create()`、`load()`、`save()`、`export_python()`、`save_result_copy()` | 模板发现、`.morph` 读写、Python 导出与结果目录备份。 |

`synchronize()` 调用领域模型的引用解析和一致性整理；窗口刷新前后可安全调用，作为将外部文件与当前对象树对齐的统一入口。

### 运行与结果会话

源码：`application/runs.py`、`application/results.py`。

| 类型 | 公开成员 | 职责 |
|---|---|---|
| `RunMode` | `FRESH`、`CONTINUE` | 新运行或继续运行的模式。 |
| `RunSourceKind` | 定义、Python、既有结果等来源枚举。 |
| `RunSource` | 来源类型、路径及相关元数据。 |
| `OptimizationRunSession` | `active`、`adopt()`、`start_definition()`、`start_python()`、`start_continue()`、`stop()`、`release_finished()` | 管理一个 `subprocess.Popen`，并保证单一活动任务。 |
| `ResultSession` | `bind(folder)`、`load_iteration(folder, iteration)`、`deformation_cases()`、`reset()` | 读取结果目录和历史，提供某一迭代的可视化数据。 |

运行会话将定义导出为结果目录内的 Python 副本后再启动 `morphopt`，因此运行过程使用的脚本可与用户当前编辑中的定义区分开来。

### 编辑路由

源码：`application/editor_routing.py`。`EditorKind` 枚举规定节点应由属性表单、代码编辑器、载荷步矩阵、求解器编辑器、更新器编辑器或 TorchFEA 模型编辑器处理；不可变 `EditorRoute` 将一个节点种类映射到对应编辑器。Workbench 只依据这份路由选择组件。

## 模板系统

源码：`ui/schemes/base.py` 与 `ui/templates/*.morph`。

```text
SchemeTemplate
└── MorphTemplate(path, data)
      └── ProblemDefinition
```

| `SchemeTemplate` 方法/属性 | 责任 |
|---|---|
| `create_problem(label)`、`build_root()` | 创建完整问题树。 |
| `make_surface/interface/material/materials` | 创建具有 schema 默认值的节点。 |
| `make_geometry/make_part_interface/make_geometry_with_body` | 生成几何与 Part。 |
| `make_loads/make_steps/make_objective/make_solver/make_updater` | 生成其余章节。 |
| `available_*_types`、`default_*` | 为 UI 菜单和默认编辑器提供类型与选项。 |
| `objective_code_snippets()` | 提供可参数化的目标函数片段。 |

`MorphTemplate` 从 `.morph` 文件读取模板数据。当前发行模板包含 `shapeopt.morph`、`simp.morph` 与多实体组合例 `multidesign.morph`；`cantilever_beam.npz` 是 SIMP 模板引用的 TorchFEA 模型资产。新增模板只需作为包数据放进 `ui/templates/` 并满足 `.morph` 结构。

## 代码生成

源码：`ui/codegen/generator.py`。生成器是 `ProblemDefinition → Python` 的纯投影：相同业务树产生相同文本，生成过程不修改问题树。

```text
ProblemDefinition
 ├─ GeometryNode / Part / Instance / Surface  → GeometryParams 子类
 ├─ LoadsNode / StepsNode                      → FEAParams 子类
 ├─ MaterialsNode                              → MaterialsParams 子类
 ├─ ObjectiveNode                              → ObjectiveFunction 子类
 ├─ SolverNode                                 → Solver 构造
 ├─ UpdaterNode                                → Updaters 子类
 ├─ CustomClassNode / MethodOverrideNode        → 自定义子类与方法重写
 └─ root                                       → ThisController
```

生成代码从顶层 `morphopt` 导入通用类型，从 `morphopt.shapeopt`、`morphopt.simp` 导入具体扩展类型。它通过 `add_interface()`、`add_instance()`、`add_geometry_updater()`、`add_material_updater()` 生成与内核一致的声明顺序；引用节点在输出时读取目标节点的当前名称。

用户代码位于目标函数、约束代码槽和 `MethodOverrideNode.body`。`ProblemDefinition.custom_classes` 保存顶层自定义类，`class_bindings` 保存模型节点选择的类名。`codegen/custom_classes.py` 从生成代码读取可配置的类位置，从框架父类读取方法签名与文档，不执行用户代码。自定义类在模块顶层继承框架类，例如 `CustomSolver(morphopt.Solver)`；模型节点选用后，其生成类改为 `Solver(CustomSolver)`。生成构造器通过 `super()` 传入 UI 配置；显式重写的声明方法替代相应生成方法。接口、材料及曲面的构造表达式直接使用条目选中的自定义类。未选用的自定义类仅被定义，不改变模型行为。同一框架父类可以有多个可选自定义类。

展示层的 `ModelClassSelector` 只服务根级配置。模型树以持久化问题根作为 Controller 节点，以临时 Params 导航节点归组几何、载荷、材料；Solver 和 Updater 同属 Controller。选中这些配置节点时使用编辑页的类选择控件；Params 的稳定导航键保证重建后仍能恢复选中项。此层级只用于展示，持久化章节结构保持不变。接口、曲面和优化目标在添加菜单中选择，`Node.custom_class` 随条目持久化；子优化目标/罚函数约束在添加列表中选择，类名随配置条目持久化。生成器按条目构造自定义对象，不替换同类型的其他条目。生成器检查名称冲突、缺失父类、缺失选择、类型兼容性、无效方法和方法语法。父类只接受框架类路径；根级选择只接受固定配置类路径。旧 Part 编号、深层别名绑定和隐式类替换不再支持。

## 验证与失败边界

运行前 `ProblemSession.validate_for_run()` 检查问题树、导入模型链接和必需引用。`MissingImportedModelError` 专门表示 TorchFEA 存档缺失或无法解析。生成完成后，运行子进程的标准输出/错误由展示层消费；结果目录中的定义副本使任何失败都可使用当次声明重现。
