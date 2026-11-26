# Extension and maintenance

[简体中文](../../zh-CN/codestructure/development.md)

[Code structure overview](README.md)  ·  [Model](model.md)  ·  [UI applications](ui-application.md)  ·  [Result analysis](results.md)

## Contents

<!-- docs:toc depth=1 -->

- [1 Function attribution](#section-功能归属)
- [2 Implementation paths for new model types](#section-新模型类型的实现路径)
- [3 Parameter and numerical semantic contract](#section-参数与数值语义契约)
- [4 Visualized extension contract](#section-可视化扩展契约)
- [5 Existing inspection tools and locations to be covered](#section-现有检查工具与覆盖位置)
- [6 Naming, resource management, and document maintenance](#section-命名资源与文档维护)

<!-- /docs:toc -->

<a id="section-功能归属"></a>

## 1 Function attribution

| Change | Define positions | Access location |
|---|---|---|
| New model fields | `ui/model/node_types/` and `FieldSpec` | Field services, persistence mechanisms, generators, and backend parameters |
| New cross-object rules | `ProblemDefinition` | Apply commands, allowing trees and cards to share them together. |
| New editing workflows | `ui/application/` | `DefinitionActions` or custom pages |
| New Rapid Start Model | `application/quickstart.py` | Combining existing node types to generate a standard problem definition. |
| New backend part | `BasePart` subclass | Parameters collection, UI nodes, preview, and collection provider |
| Newly designed objects | Upgradable protocols and their specific subclasses | Gradient layout, sub-optimizers, saving and display functions |
| New preview types | Part/Surface/Load visitor | Node class registration and necessary rendering elements |
| New editing page | widget | `route_editor()`, `EditorPages`, and refreshing registrations |
| Newly obtained results/quantities | `postprocess.fields.ResultField` | `RESULT_FIELDS` and the necessary components of the cloud diagram |
| New export format | `TableWriter` | `TABLE_WRITERS`, do not copy the physical extraction logic. |
| New one-time background tasks | `ui/worker.py` | `processes.start_worker()`. Data is delivered through request and response files. |
| New operating mode | `OptimizationRunSession` | Identify the source of the issue, the current state of the process, and a snapshot of the progress. |

The domain identity is expressed by the object and the stable key, while the displayed text is localized at the presentation layer. Files, processes, physical calculations, and rendering are all processed at their respective layers.

<a id="section-新模型类型的实现路径"></a>

## 2 Implementation paths for new model types

1. In the kernel, parameters, lifecycle, and model construction behaviors are defined clearly. Additionally, aspects related to caching and geometric variability are also specified.
2. The designed types can be used to implement variable extraction, sensitivity projection, writing back, and saving of contracts. This ensures that the order of operations remains consistent.
3. Declare specific types and fields in the corresponding node family of the UI, and add `registry.py` to them.
4. At the application layer, additional target queries, dynamic options, and parameter mappings need to be added.
5. The preview adapter corresponding to the registered node class and the necessary `PartSetCatalog` provider.
6. Use existing fields and collection actions; special interactions are handled through routes and unified refreshing mechanisms.
7. For references on how to synchronize the script/UI interface, please refer to the topics within this directory.

This path is used to determine the implementation of responsibilities. For a complete example of how to construct it, see [Script module reference](../script-reference.md). Do not copy another set of task definitions in the architecture document.

When reusing the existing Part construction process, the subclass overrides the corresponding methods at each stage, and the parent class calls the scheduling methods through instance methods. The closed surfaces that need to be exported can inherit from `BaseSurface.prepare_geometry()`; the `BREPSurface` of the existing STEP assets can be used directly from the original file. The surface calls the corresponding loading method of CADPart in `load_geometry(part, context)`, without holding the source CAD operation history. Discrete surfaces declare their geometric kernel requirements through `is_discrete`. The preparation, assembly, and aggregation definitions specific to each type are placed in the corresponding subclasses, while the common construction methods remain unchanged.

<a id="section-参数与数值语义契约"></a>

## 3 Parameter and numerical semantic contract

| Configuration | Contents that need to be kept consistent |
|---|---|
| Field key | Node selection, data storage, generation of calls, and generation of backend signatures |
| Material model | `MaterialsParams.models` Parameter types and visible fields |
| Process devices | The UI components are arranged in a process-based order and transmitted to `Solver.process_devices`. Each process corresponds to a specific device. |
| Instance pose | Three translations plus three rotation vectors; the units and arrangements are consistent with the original scheme. |
| Curved surface dimensions | `seed_size` and the body's grid size need to be defined separately. |
| Fairness threshold | Curvature, the first fundamental form, and non-orthogonal metrics do not serve as constraints for determining the upper limit of point displacements. |
| Initial values for SIMP | The control field `f`, material proportion `ρ`, and stiffness ratio are defined separately. |
| Unit selection | The block name is `Part.elems`, not determined by the unit formula name. |
| Cylindrical Envelope | The currently implemented value of `bottom` represents the lower bound of Z, while `height` represents the upper bound of Z. |

The upper limit of curvature is stored as `Fairness(max_curvature=...)`; the metric changes and non-orthogonal thresholds for BSP are respectively 0.1 and 0.2. The surface only stores geometry information; the normal direction is set based on the component order. The constructor does not accept `flip`. The new surface penalty term is extended through the visitor mechanism, and optimization parameters are not added to the surface class. The internal algorithm parameters and UI labels cannot be considered equivalent just because their names are similar.

<a id="section-可视化扩展契约"></a>

## 4 Visualized extension contract

Preview registration for the node Python class: `PartPreviewVisitor.register(NodeType, adapter)`. It does not match the type display string. The adapter prepares the grid and scene, and does not hold widgets, plotters, or VTK actors. The load elements are dispatched for rendering by the renderer.

The results are displayed using either the archived model or the physical field context. The solution model is not obtained from the defined preview cache. New field quantities are defined with clear positions, units, coordinate systems, tensor conventions, and handling of missing values. The exporter is only responsible for file representation.

<a id="section-现有检查工具与覆盖位置"></a>

## 5 Existing inspection tools and locations to be covered

The following table indicates the responsibilities associated with various checks. The scope of execution depends on the actual changes made.

| Tools or documents | Cover content |
|---|---|
| [`tests/optcore/test_objfunc.py`](../../../tests/optcore/test_objfunc.py) | Target and result saving behavior |
| [`tests/optcore/test_solver.py`](../../../tests/optcore/test_solver.py) | Solution to operating conditions and initial value processing |
| [`tests/optcore/test_runner.py`](../../../tests/optcore/test_runner.py) | Task function's spawn phase, continued execution, failure at the first round, and debugging options |
| [`tests/ui/test_model_persistence.py`](../../../tests/ui/test_model_persistence.py) | Define serialization and type restoration procedures. |
| [`tests/ui/test_application.py`](../../../tests/ui/test_application.py) | Application operations, references, and sessions |
| [`tests/ui/test_parameter_contracts.py`](../../../tests/ui/test_parameter_contracts.py) | The node, generation parameters, and backend signature are all properly matched. |
| [`tests/ui/test_custom_classes.py`](../../../tests/ui/test_custom_classes.py) | Custom class binding and generation |
| [`tests/ui/test_quickstart.py`](../../../tests/ui/test_quickstart.py) | Initial definitions and combination of conditions/targets |
| [`tests/ui/test_refresh.py`](../../../tests/ui/test_refresh.py) | Refresh merged items and their context. |
| [`tests/ui/test_finite_element.py`](../../../tests/ui/test_finite_element.py) | Independent finite elements, field quantities, and their derivatives |
| [`tests/ui/test_viewer_lifecycle.py`](../../../tests/ui/test_viewer_lifecycle.py) | Viewport and Object Lifecycle |
| [`utils/gradient_check.py`](../../../src/morphopt/utils/gradient_check.py) | Comparison of AD and central difference sensitivities |

`morphopt.check_gradients()` uses the same variables of the model to write back the geometric and material gradients compared with the target path, involving the solution of the actual model. `morphopt.get_controller()` Reconstructing the controller from the archive and loading the state also involves the corresponding initialization process; both are not simple queries that only read file names.

The undo function for defined edits, deserialization for recovery, code generation, initial solving, and long-term optimization cover different contracts respectively. Unexecuted checks cannot be used as evidence of successful implementation.

<a id="section-命名资源与文档维护"></a>

## 6 Naming, resource management, and document maintenance

`Session` represents a stateful application session, `Library` represents the resource/file entry, and `Page/Editor/Viewer` represents the Qt display role. The method names differentiate between domain editing, file reading/writing, session binding, and display refreshing, to avoid using temporary names that have unclear meanings in long-term business objects.

The default values for business settings and numerical configurations are assigned to `constants.py`. The appearance and layout are assigned to `ui/theme/`, and the application text is assigned to `ui/locales/`. Resource paths are resolved based on the package location or specific task sources, and do not include absolute paths to specific computers or environment names.

Auxiliary functions that are cross-module reusable and do not hold business state are categorized under `utils/`: `paths.py`. They handle file name components for Windows and Linux, while `quadrature.py` provides Gaussian integration at the load space boundary. Short auxiliary functions that belong to only one caller are placed within the calling module; the loops for starting and continuing tasks are centralized in `opt_runner.py`. Independent domain objects are organized by model, solution, design updates, or UI responsibilities. The number of lines in files is not the only criterion for merging modules. The controller types in tool modules are annotated using `TYPE_CHECKING` to prevent reverse loading of the running controller by the base tools.

The code structure document uses this directory as the only navigation entry, with a README file. Changes to the public boundaries update the system architecture; specific implementation changes are only discussed in the relevant topics, while other topics use the links provided. Parameters and operations that are visible to users are updated synchronously in [Four documents containing usage instructions](../README.md).

Execute `python scripts/docs/number_docs.py` in the root directory of the warehouse to update the title number and directory. File names are based on the topic names, and the numbers are generated based on the title hierarchy. No other order is maintained using the file prefixes.
