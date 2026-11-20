# MorphOpt code structure

[简体中文](../../zh-CN/codestructure/README.md)

This document is intended for developers who maintain and extend MorphOpt. It explains the module boundaries, object ownership, call order, and persistence conventions of the current source code. Task execution and interface operations are described in [Script module reference](../script-reference.md) and [UI module reference](../ui-reference.md) respectively.

<a id="section-模块化设计原则"></a>

## 1 Modular design principles

MorphOpt organizes modules according to their responsibilities, connecting various modules through clear relationships between inputs, outputs, and state ownership. The overall design includes three levels of separation.

| Design hierarchy | Module division | Collaborative relationships |
|---|---|---|
| Application | UI and numerical kernel | The UI turns the model definition into a Python task. Generated tasks and handwritten scripts run through the same kernel. |
| Numerical kernel | Model assembly, FE solution, objectives and sensitivities, and design updates | The controller passes the assembled model, load-case solutions and gradients through these stages. |
| UI | Model data and presentation | Editing sessions maintain the definition. The tree, forms and 3D viewport display views of that definition. |

The types of models, numerical algorithms, and interface layouts are expanded within their respective modules. The shared protocol defines the lifecycle of objects and their interfaces with design variables. Each component retains its own state, and cross-component operations are organized by the corresponding coordinating objects. [System architecture](architecture.md#modularity) illustrates these boundaries and their corresponding source code in three diagrams.

<a id="section-专题导航"></a>

## 2 Module guides

| documentation | Content ownership |
|---|---|
| [System architecture](architecture.md) | Modular design concept, separation of responsibilities at three levels, architecture diagrams, interface contracts, and clear boundaries between different states. |
| [Runtime and processes](runtime.md) | Task initiation, controller initialization, single-round computation, process restart, and archiving of results. |
| [Model and parameter set](model.md) | Shared protocols, parts/instances, load conditions, material allocation, and model construction. |
| [Sensitivity and design updates](optimization.md) | Variable layout, target gradient, optimizer binding, shape, SIMP and bias expansion |
| [UI domain model](ui-model.md) | Typed nodes, object references, structural operations, names, and `.morph` serialization. |
| [UI Application Services](ui-application.md) | Edit sessions, operation history, Quickstart, code generation, custom classes, and optimization run sessions |
| [UI display and refresh mechanisms](ui-presentation.md) | Windows, editors, navigation projections, refresh scheduling, preview rendering, themes and localization settings. |
| [Result analysis and export](results.md) | Result reading, shared iterative selections, independent finite elements, physical field calculations, and file export. |
| [Expansion and maintenance](development.md) | Location of new types and functions, parameter contracts, existing inspection tools, and documentation maintenance |

Each topic is explained in detail in the corresponding document above. The system architecture retains the overall relationships, while the topic-specific documents explain the internal implementations. The source code paths are listed in the “Source Code Entrance” section of the relevant topics.

<a id="section-阅读路径"></a>

## 3 Reading path

- Core maintenance: System architecture → Runtime → Model and parameter set → Sensitivity and design updates.
- UI editing functions: system architecture → UI domain model → UI application services → UI display and refresh.
- Results and post-processing: During operation → Result analysis and export → Combination of result pages for UI display and refresh.
- New feature development: First, determine the layer to which the state belongs. Then, refer to the corresponding topics and extended locations.

<a id="section-按变更定位"></a>

## 4 Locate the changes accordingly.

| Changes made | Mainly responsible for implementing location-related functions | documentation |
|---|---|---|
| Solve scheduling problems, manage work processes, and handle restarts. | `opt_runner.py`、`optcore/controller.py`、`solver.py` | [Runtime](runtime.md) |
| Parts, loads, constitutive relations, and assembly procedures | `optcore/modelparams/` | [Model](model.md) |
| Curved surfaces, density fields, gradients, and local optimization techniques | `shapeopt/`、`simp/`、`codesign/`、`optcore/updaters.py` | [Design updates](optimization.md) |
| Cross-platform naming conventions, boundary integration techniques, and inspection tools | `utils/paths.py`、`utils/quadrature.py`、`utils/gradient_check.py` | [Expansion and maintenance](development.md) |
| Fields, references, sorting, and renaming/modification of fields | `ui/model/`、`ui/application/editing.py` | [UI domain model](ui-model.md) |
| History, script generation, class selection, source of tasks | `ui/application/`、`ui/codegen/` | [UI Application Services](ui-application.md) |
| Controls, trees, cards, refreshing and previewing functions | `ui/widgets/`、`ui/presentation/`、`ui/visualization/`、`ui/refresh.py` | [UI display](ui-presentation.md) |
| Historical data browsing, independent calculations, field quantities and data export capabilities. | `ui/observe_panel.py`、`ui/application/finite_element.py`、`ui/worker.py`、`postprocess/` | [Result analysis](results.md) |

<a id="section-文档组织约定"></a>

## 5 Document organization conventions

The file names are named according to the topics, and do not carry chapter numbers. The title numbers and table of contents for each article are generated from the root directory of the repository, `python scripts/docs/number_docs.py`. You can use `--watch` during editing.

The API parameter table and executable examples are focused on the usage documentation. This directory explains the implementation of boundaries, call relationships, and state constraints. When making structural adjustments, update the relevant topics, current navigation, and document references in the source code to avoid having multiple identical architectural descriptions in the same layer.
