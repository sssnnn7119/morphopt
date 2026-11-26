# MorphOpt documentation

[简体中文](../zh-CN/README.md)

The quick starts walk through a complete bending-actuator optimization. The references describe individual modules, fields and extension points. Both workflows use the same model.

| Workflow | Quick start | Module reference |
|---|---|---|
| Python | [Run the example script and inspect its results](script-quickstart.md) | [Define model classes, register interfaces and extend the solver or updater](script-reference.md) |
| Graphical UI | [Build and run the example in the UI](ui-quickstart.md) | [Look up model-tree entries, form fields, previews and custom classes](ui-reference.md) |

The example is available as a [Python script](../../examples/bending_actuator/bending_actuator.py) and an [editable UI definition](../../examples/bending_actuator/bending_actuator.morph). Part, instance, reference point, pressure and material names correspond across the two files. The [examples directory](../../examples/README.md) contains the runnable cases and their input assets.

<a id="section-阅读顺序"></a>

## 1 Reading order

Start with the quick start for your workflow. Use the reference when changing a component or interpreting a field.

| Definition | Python | UI |
|---|---|---|
| Task and output directory | `ThisController.__init__()` | Controller settings |
| Parts and instances | `Params.GeometryParams` | Model parameters → Geometry |
| Loads, boundary conditions and load cases | `Params.FEAParams` | Loads and boundary conditions → Load cases |
| Materials and assignments | `Params.MaterialsParams` | Materials |
| Objectives and metrics | `ObjectiveFunction` | Objective function |
| Compute devices and load-case groups | `Solver` | Solver |
| Geometry and material updates | `Updater` and its component updaters | Optimizer for the selected part or material |
| Custom implementations | Python subclasses | Helper code → Custom classes |

<a id="section-理论架构与示例"></a>

## 2 Theory, architecture and examples

- [Shape optimization](theory/morphdesign.md) covers geometry, nonlinear mechanics, objectives and adjoint sensitivities.
- [Shape and material co-design](theory/codesign.md) describes offset layers, SIMP fields and coupled updates.
- [Code structure](codestructure/README.md) describes the numerical kernel, UI, results and extension points.
- [Hybrid cylinder](../../examples/hybrid_cylinder/hybrid_cylinder.md) combines a STEP outer boundary with a B-spline cavity.
- [UI screenshots](images/README.md) explains the capture procedure. The [gallery](images/gallery.md) links each view to its counterpart in the other language.

<a id="section-章节编号与文档维护"></a>

## 3 Maintaining the documentation

The two language directories use identical relative paths. Place each new guide, reference page or illustration at the same location in both editions. The screenshots in `images/ui-quickstart/` follow the workflow from model definition to results. Those in `images/ui-reference/` illustrate individual modules. Pages can reference either collection.

Use one `#` for the page title. Start sections with `##` and increase the heading depth by one level at a time. Run the following commands from the repository root to update section numbers and tables of contents and check local links, images and Python snippets.

```bash
python scripts/docs/number_docs.py
python scripts/docs/check_docs.py
```

Use `python scripts/docs/number_docs.py --watch` to update the numbering as files change. Keep explicit anchors when renaming headings so existing links continue to work. The `docs:toc depth=1` and `/docs:toc` HTML comments delimit an automatic table of contents. The depth can range from 1 to 5.

<a id="section-当前能力与阅读入口"></a>

## 4 Topic index

| Topic | Where to look |
|---|---|
| First- and second-order models of the physical objective | [Design updates and physical surrogates](script-reference.md#section-有限元目标的历史梯度二阶代理) |
| Geometric integration and update strategy | [Barrier integrals and update policies](script-reference.md#section-几何更新策略与障碍积分) |
| Curvature and surface parameterization | [Fairness](ui-reference.md#updater_constraints-fairness) |
| Component fields, lists and expressions | [Input conventions](ui-reference.md#section-数值列表与表达式) |
| Named load cases and load amplitudes | [Load cases](ui-reference.md#steps) |
| Workspace objectives and quadrature cases | [Objectives and metrics](ui-reference.md#objectives) |
| Reference-point and nodal degrees of freedom | [PenaltyDoF](ui-reference.md#load_types-penaltydof) |
| Process devices and ordered load-case groups | [Solver](ui-reference.md#section-solver工况任务的组织) |
| Metrics, per-objective contributions and history fields | [Reading reference-point responses](script-reference.md#section-按名称提取参考点响应) |
| Run logs and exceptions | [Runtime](codestructure/runtime.md#section-首轮失败与日志归档) |
| Archived designs, deformations, GIF and geometry export | [Results](ui-reference.md#results) |
| Font roles, previews and application settings | [Fonts](ui-reference.md#section-字体设置与应用范围) |
| Importing editable definitions | [The .morph file boundary](codestructure/ui-model.md#section-morph-边界与兼容处理) |
| Geometry assets and script export | [Generated code and persistence](ui-reference.md#section-生成代码与持久化接口) |

The [capture manifest](images/current-capture-manifest.json) records the definition, dimensions and font settings for the screenshots.
