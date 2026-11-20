# UI Application Services

[简体中文](../../zh-CN/codestructure/ui-application.md)

[Code structure overview](README.md)  ·  [Domain Model](ui-model.md)  ·  [Displaying and refreshing](ui-presentation.md)  ·  [Result analysis](results.md)

## Contents

<!-- docs:toc depth=1 -->

- [1 Source code entry point](#section-源码入口)
- [2 Define session and file entries.](#section-定义会话与文件入口)
- [3 Edit commands and parameter queries](#section-编辑命令与参数查询)
- [4 Edit History and Restoration](#section-编辑历史与恢复)
- [5 Quickstart and initial model setups](#section-quickstart-与初始模型)
- [6 Code generation boundaries](#section-代码生成边界)
- [7 Selection and binding of custom classes](#custom-classes)
- [8 CAD conversion and STEP export](#cad)
- [9 Optimize running sessions.](#runs)
- [10 Operating conditions and parameter metadata](#section-工况操作与参数元数据)

<!-- /docs:toc -->

<a id="section-源码入口"></a>

## 1 Source code entry point

| Path | Responsibility |
|---|---|
| [`application/definitions.py`](../../../src/morphopt/ui/application/definitions.py) | `ProblemSession`、`ProblemLibrary` |
| [`application/editing.py`](../../../src/morphopt/ui/application/editing.py) | Default object creation, auxiliary codes, custom classes, condition settings, and task editing. |
| [`application/edit_history.py`](../../../src/morphopt/ui/application/edit_history.py) | Immutable edited snapshots and branch history |
| [`application/fields.py`](../../../src/morphopt/ui/application/fields.py)、[`values.py`](../../../src/morphopt/ui/application/values.py) | Editable fields, options, and numerical text |
| [`application/expressions.py`](../../../src/morphopt/ui/application/expressions.py)、[`part_sets.py`](../../../src/morphopt/ui/application/part_sets.py) | Expression context and Part collection queries |
| [`application/cad.py`](../../../src/morphopt/ui/application/cad.py)、[`worker.py`](../../../src/morphopt/ui/worker.py) | CAD geometry preview, STEP export, and component conversion process |
| [`application/updaters.py`](../../../src/morphopt/ui/application/updaters.py) | Sub-optimizer: Segmentation and ordered entry editing functions. |
| [`application/quickstart.py`](../../../src/morphopt/ui/application/quickstart.py) | Construction of the initial model |
| [`codegen/snippets.py`](../../../src/morphopt/ui/codegen/snippets.py) | Finite metadata extraction templates in the objective function |
| [`codegen/`](../../../src/morphopt/ui/codegen) | Python-based generation and custom class projections |
| [`application/runs.py`](../../../src/morphopt/ui/application/runs.py)、[`launcher.py`](../../../src/morphopt/ui/launcher.py) | Task source, running sessions, and process infrastructure |

The results of load case analysis, finite element calculations, and field quantity services are presented in [Results](results.md). This document describes the application process for defining and editing these definitions before task execution.

<a id="section-定义会话与文件入口"></a>

## 2 Define session and file entries.

`ProblemSession` currently holds `ProblemDefinition` and `EditHistory`.

| Interface | Responsibility |
|---|---|
| `replace()` | Replace the definition and establish a historical baseline. |
| `synchronize()` | Parse and align the configuration related to the surface. |
| `source()` | The current Python code is generated on demand from the synchronized definition. |
| `validate_for_run()` | Perform validation and necessary reference checks. |
| `record_edit()`、`restore_edit_step()` | Submit and restore defined snapshots |
| `set_label/result_folder/device()` | Modify task configuration. |

`ProblemLibrary` is the entry point for creating blank definitions and starting models quickly, opening/saving `.morph`, exporting Python, and saving definitions for runtime. The dialog box provides the path, while the service layer is responsible for handling the file content. Additional fields, missing default values, and unsupported entries during the import phase are summarized by the importer. The window is only responsible for displaying warnings; the runtime verification ensures the integrity of the current definitions.

Field editing, structural operations, and restoration history trigger corresponding synchronizations respectively. The refresh component consumes the synchronized context, avoiding redundant calls for generating data that needs to be synchronized across domains.

<a id="section-编辑命令与参数查询"></a>

## 3 Edit commands and parameter queries

| Types or services | Responsibility |
|---|---|
| `DefinitionCommands` | Use default values for the creation of Part, surface, material, load, CAD, and updater entries. |
| `set_node_field()`、`rename_node()` | Unified field writing and name routing |
| `HelperCodeSession` | Save and verify the auxiliary code, variables, and functions. |
| `CustomClassSession` | Classes and methods are created, renamed, deleted, and referenced simultaneously. |
| `LoadCaseSession` | Condition name, registration order, read/write of parameters for each load, and synchronization of generated conditions. |
| `SolverTasks` | Ordered operating conditions, movement within groups, disassembly and assembly of groups |
| `UpdaterItems` and other ordered services | Target values, penalty functions, and sorting based on surface symmetry |
| `PartSetCatalog` | Query node sets, surface sets, and cell blocks based on the actual type of parts. |

In a collective query, providers should be selected based on their belonging to a specific Part. The option of whether all components exist as INPParts cannot be used to determine the collective options for other components. Reference fields can have null values; templates and Quickstart explicitly specify the target, and it is necessary to check these references before running the process.

`DefinitionValues` Create namespaces for auxiliary variables, functions, and expressions for evaluation purposes. These namespaces provide current defined values for preview and CAD operations. Saving field expressions means managing the preview evaluation results separately. The generated scripts retain the corresponding Python expressions.

<a id="section-编辑历史与恢复"></a>

## 4 Edit History and Restoration

`EditSnapshot` Save and `.morph` UTF-8 JSON bytes with the same structure, operation descriptions, and lightweight selection paths. The snapshot is not shared with the current model, and it does not save the mesh or results.

```text
The definitions after synchronization are as follows: → snapshot() → EditHistory.commit()
                                    ├── Consecutive inputs of the same type can be merged together.
                                    └── After revocation, a new branch is created through editing.
Historical Step ID → Decoded Snapshots → ProblemDefinition.from_dict()
                         → Restore the navigation position. → Unified refresh
```

`EditHistoryNode` associates parent nodes, ordered child nodes, and preferred redo branches with a stable ID. The same JSON does not create new records; `EditHistory.commit()` does not automatically delete nodes. `at_capacity` only reports whether the number of nodes has reached the limit. After editing and submitting, the workbench displays a scheduling capacity window, allowing users to choose whether to clean up or expand the capacity. `clear()` only retains the current snapshot, along with the stable ID, subsequent numbers, and markers indicating that the data is already saved.

The upper limit of nodes is configured through “Settings → Design Options → Maximum Number of Historical Nodes”. Save the configuration using `QSettings`. When the number of nodes is reduced to below the current limit, the workbench will reuse the same capacity. Canceling the operation does not modify the historical data or the original upper limit. The model layer does not depend on Qt. The pop-up windows and preferences are coordinated by the UI. The historical graph uses iterative traversal, and the branch length is not limited by the Python call stack depth.

First, successfully decode the target snapshot, then move the historical cursor. Before restoration, cancel the values being edited, cancel the previous refresh requests, and bind each form to the new object. The selection of the location is described by the navigation path, independent of the old object's Python `id()`.

Create, open, and use Quickstart to establish a new starting point; save the content as it is, but retain the historical branches. Changes in cameras, languages, and selections will not be recorded in the document history. The optimization process, external files, and result status will not be rolled back when the definition is revoked.

<a id="section-quickstart-与初始模型"></a>

## 5 Quickstart and initial model setups

The typified configuration of `application/quickstart.py` is validated during input processing, resulting in the generation of geometric, material, load conditions, weighted objectives, and updaters. `ObjectiveDraft` maintains the objectives and pressure channels in a draft form; `model/chamberlayout.py` manages the hierarchical arrangement of air cavities. The output remains as ordinary `ProblemDefinition`; the settings can be saved as auxiliary variables `quickstart_settings`.

The quick start option only determines the objects registered in the initial model. After generation, the geometry, materials, targets, and updaters are all represented by standard typed nodes; `ProblemDefinition` does not retain the global scheme identifier. The add menu directly reads from `model/registry.py`, and node construction uses the default fields of each node type. The finite element metadata extraction template is provided by `codegen/snippets.py`, regardless of the type of the initial model.

The generation of geometric factories and meshes is implemented by the kernel. The Quickstart module combines existing Part/urface types. The boundary integral points and weights of the workspace targets are provided by `utils/quadrature.py`. The application layer maps the pressure channels to the load cases and the Jacobian matrices in the targets.

<a id="section-代码生成边界"></a>

## 6 Code generation boundaries

`codegen/generator.py` synchronizes the defined projections to the standard `ThisController`. The generator reads the model, without writing the temporary state generated back into the definitions.

`codegen/assets.py` collects STL, INP, and STEP resources uniformly, and returns the mapping of nodes to relative paths along with `DefinitionAsset` records. The records include categories, formats, file contents, sources, associated nodes, and reference locations. The name of the resources is determined solely by the current definition and the file content. Code previews, asset pages, and file exports use the same inventory; `ProblemLibrary.export_python()` is responsible for writing the source code and resources to the disk. File overwriting is handled through the interface.

| Definition | Generate locations |
|---|---|
| Part, Instance, Surface, CAD Operations | `Params.GeometryParams` and its corresponding Part subclass |
| Load and operating conditions | `Params.FEAParams` |
| Material interfaces and constitutive parameters | `Params.MaterialsParams` |
| Losses, metrics, and Jacobian selection | `ObjectiveFunction` |
| Equipment and task groups | `Solver` is constructed. |
| Geometry and material updates configuration | `Updater` and its sub-optimizers |
| Auxiliary codes and custom classes | Inheritance points for module-level definitions and configuration settings |

The generation and invocation follow the same kernel registration order and reference names. Identical definitions should yield the same text; `.morph` is an editable source, and Python provides one-way output, without the responsibility of reconstructing any tasks in reverse.

<a id="asset-previews"></a>

The asset page is located at `widgets/asset_browser.py`. The preview components are registered by category. `AssetBrowser.register_preview(category, title_key, factory)` specifies the category identifier, language text keys, and component factories; the components inherit from `AssetPreview` and implement `set_asset(asset, problem)`. They can respond to interface switching through `apply_language()` and `apply_theme()`. The collection logic for new categories should return the corresponding `DefinitionAsset`, and the display logic is handled by the registered components.

The built-in `GeometryAssetPreview` uses `visualization/assets.py` to convert STEP, STL, and INP contents into scene formats, and then reuses `PreviewRenderer` for rendering. The STEP scene follows the CAD patch merging logic; the INP scene continues to use the component selection of its associated nodes. Components are created when they are visible and selected on the asset page. No additional rendering windows are created on hidden pages. The list is refreshed, retaining the current selection; when the content remains unchanged, the displayed scenes and perspectives are preserved.

<a id="custom-classes"></a>

## 7 Selection and binding of custom classes

`codegen/custom_classes.py` The analysis framework’s parent class, the location where configuration classes are generated, method signatures, and the implementation of user methods. Class directories and method validation do not include the implementation of user methods; the evaluation of expression previews belongs to another application path.

| Select objects | Save location | Projection |
|---|---|---|
| Fixed configuration locations for parameters, controllers, etc. | Fixed path binding or corresponding node fields | Generate configuration classes that inherit from the selected class. |
| ObjectiveFunction | `ObjectiveNode.custom_class` | Generate classes that inherit from the selected implementations. |
| Items such as parts, surfaces, materials, etc. | `Node.custom_class` | The construction expression of the current entry uses the selected class. |
| Individual geometric/material sub-optimizers | Configuration dictionary for `custom_class` | Generate the corresponding nested classes according to the current configuration order. |
| Sub-goals or constraints | Entry configuration | Create the selected implementation based on the entry. |

The sub-optimizer is bound to the configuration object and is saved together with it. It does not use variable list indexes to persist the business identity. During generation, the nested class path is calculated, and after adjusting the order of entries, the class selected from the original object remains unchanged.

Creating a custom class does not automatically replace all objects of the same type. Class renaming, deletion, and compatibility checks are handled by the shared service. The presentation layer only provides a class directory and selection controls.

<a id="cad"></a>

## 8 CAD conversion and STEP export

`application/cad.py` converts CAD nodes into native `torchfea.cad` format for preview and export reuse. `export_cad_step(node, path, problem)` parses the ordered operations using the current expression context, and then calls `torchfea.cad.export_step()`. STEP export does not construct FE meshes, and does not change the problem tree or edit history. The save dialog box, file extension filtering, and overwrite confirmation are handled by `widgets/file_dialogs.py`.

`convert_cad_to_boundary(node: CADPartNode, problem: ProblemDefinition, asset_directory: str | Path) -> BoundaryPartNode` generates task source code and assets through the same `ProblemLibrary.export_python()`. It loads the geometric definitions of custom classes that are enabled. It only initializes the target CADPart, and then calls the `to_boundary_part()` of the kernel. Each enclosed shell is converted into STEP format and surface mapping. The service embeds them into `BREPSurfaceNode`, and returns the BoundaryPart that needs to be submitted. The service does not modify the original problem.

`DefinitionActions.convert_cad_to_boundary(part: CADPartNode) -> None` provides a common entry point for editing cards and tree menus. The action freezes the current problem, and `QProcess` is used to initiate the `convert_cad` task of the unified `worker.py`. The working process reads a snapshot and generates replacement nodes. After success, the main thread retains the instance object through `ProblemDefinition.replace_part()` and redirects the model association. Then, a reversible edit is submitted again. The progress window can be canceled; if failure, cancellation, or the source problem is switched, the conversion result is not submitted. Temporary source code and assets are cleared after the conversion is completed. The current definitions are held as BREP assets through embedded data.

<a id="runs"></a>

## 9 Optimize running sessions.

`RunSourceKind`, `RunSource` and `RunMode` represent the sources of definitions, Python code, or existing results. `OptimizationRunSession` holds unique information about the active `subprocess.Popen`, output consumption status, result directory discovery, and sources for continued running.

When starting from the interface definition, the running session creates an independent definition snapshot. `launcher.run_job()` calls the same `export_python_bundle()` used for manual export, generating the script and `morphopt_assets` in a separate temporary directory, and then launching the script. The controller copies the script and resources to the `scripts/` in the result directory. The reference check is performed before starting, and the full code verification is carried out when the script is actually generated.

```text
Select the source of the task. → Freeze Definition/Script Snapshot → Launch an independent process
                     → Output collection and poll() function → RunProgress
                     → The result directory has been found. → Reading the archive on the observation page.
Stop/Exit → Stop the process group → Retain the complete results along with the sources from which they were obtained.
```

`ObserverControls` connects to buttons, dialog boxes, timers, and Qt signals; tracks the progress of consumer sessions; does not save another copy of the process state. Output reading is performed in the background, and the UI thread does not block waiting for standard output.

The opened results are only for browsing and continuing the calculation; no tasks are automatically initiated. Switching pages does not start, stop, or reset the process. The definition snapshots during execution are stored separately from the currently edited definitions, so subsequent edits will not overwrite the ongoing tasks.

<a id="section-工况操作与参数元数据"></a>

## 10 Operating conditions and parameter metadata

The load case collection page and the tree menu share `DefinitionActions.add_load_case()`, `move_load_case()`, and `remove_load_case()`. Name changes and scalar editing are routed through `set_node_field()` / `rename_node()` to `LoadCaseSession`. When the workspace configuration is complete, boundary Gaussian point load cases are generated synchronously. When a target is deleted, it is asked whether to clean up the load cases that are no longer referenced. When a load case is deleted, it is asked whether to cascade the deletion of the referenced targets. Otherwise, the corresponding selections will be cleared. Existing load definitions do not participate in this cleanup process.

`application/fields.py` generates fields and candidate options based on the context of the object. In the instance PenaltyDoF, only the node numbers and directions are displayed. The reference points only show six degrees of freedom. The business values are still written back to the same `s`. The independent finite element page reads the same `value_fields` based on the actual load category. Each scalar value is independently verified and submitted.
