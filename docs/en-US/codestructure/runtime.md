# Runtime and processes

[简体中文](../../zh-CN/codestructure/runtime.md)

[Code structure overview](README.md)  ·  [Model Construction](model.md)  ·  [Design updates](optimization.md)  ·  [Result analysis](results.md)

## Contents

<!-- docs:toc depth=1 -->

- [1 Source code entry point](#section-源码入口)
- [2 Task loading and process hierarchy](#section-任务加载与进程层次)
- [3 Controller initialization](#section-控制器初始化)
- [4 Single-wheel computing](#section-单轮计算)
- [5 Solving scheduling problems with initial solutions](#section-求解调度与初始解)
- [6 Segmented operation and recovery](#section-分段运行与恢复)
- [7 Responsibility for running directories and storing files](#section-运行目录与保存责任)
- [8 Devices, resources, and error boundaries](#section-设备资源与错误边界)
- [9 First round failed, logs are being archived now.](#section-首轮失败与日志归档)

<!-- /docs:toc -->

<a id="section-源码入口"></a>

## 1 Source code entry point

| File | Main targets and responsibilities |
|---|---|
| [`opt_runner.py`](../../../src/morphopt/opt_runner.py) | Publicly launched and configured the entry points. The `_run_task()` segment continues the loop, and the `_run_worker()` task is in progress. |
| [`optcore/controller.py`](../../../src/morphopt/optcore/controller.py) | `Controller`: running objects, calculating main loops, saving data, and switching between devices. |
| [`optcore/solver.py`](../../../src/morphopt/optcore/solver.py) | Task allocation based on operating conditions, initial values for finite element analysis, and invocation of solution processes |
| [`optcore/objfunc.py`](../../../src/morphopt/optcore/objfunc.py) | Target calculation, sensitivity analysis, and model/result saving. |
| [`optcore/history.py`](../../../src/morphopt/optcore/history.py) | Reading and writing from `History` files in CSV format |

<a id="section-任务加载与进程层次"></a>

## 2 Task loading and process hierarchy

```text
__main__ entry in the user task file
└── start_optimization()
    └── _run_task()
        └── _run_worker() Working processes
            ├── ThisController in the import task module
            ├── Create the Controller and initialize it.
            └── spawn Process pool → Solver Tasks for various operating conditions
```

The executor uses `spawn`, and the work process imports modules at the module level `ThisController`. The task startup call is located within `if __name__ == "__main__":`. The work process sets the floating-point precision and device settings, and switches the working directory to the task script directory. Therefore, the relative input and output paths are resolved according to the script directory.

Load the class from the user task file for new runs; load the class from the specific result directory `scripts/MAIN_SCRIPT_FOR_RESTART.py` for continued runs. `path_result` indicates the existing run directory, and `target_iteration` determines the saved state to be read.

`debug_optimization()` calls the same `_run_worker()` in the current process. The controller is created only once, and `_debug_mode=True` is set on the actual controller being executed. The solver then uses the serial debugging path. The function of the working process is defined at the top level of the module, and supports `spawn` import for both Windows and Linux.

The responsibility for starting and stopping external tasks lies with `OptimizationRunSession`, as described in [UI running session](ui-application.md#runs). This session does not replace the computational processes within the kernel.

<a id="section-控制器初始化"></a>

## 3 Controller initialization

`Controller.initialize()` first registers itself as `morphopt.controller`, then creates four running objects: `Params`, `Solver(params)`, `Updater(params)`, and `ObjectiveFunction`. The initialization order is parameters, solver, updater, objective, and history. After that, a solution process pool is established.

| Call phase | Content |
|---|---|
| Object construction | Save task configurations and declared parameters, and create containers. |
| `params.initialize()` | Register the model interface, specifying the surface, instances, operating conditions, and material properties. |
| `solver.initialize()` | Preparation phase task grouping |
| `updater.initialize()` | Parsing the updated targets and preparing the local state of the corresponding design objects. |
| `objfun.initialize()`、`history.initialize()` | Prepare targets for the new history. |
| `initialize_path()` | Create a specific directory for running the script, assign a log directory, save the script and any dependencies. |

Declaration and construction belong to different stages. The initialization of the parameter set is not equal to the generation of the finite element mesh; the assembly is established in each round `Params.create_feamodel()`.

<a id="section-单轮计算"></a>

## 4 Single-wheel computing

```text
Controller.opt_loop()
├── clear_cache()
├── step()
│   ├── Params / Solver / Updaters / ObjectiveFunction.reinitialize()
│   ├── Params.create_feamodel()                 → FEAController
│   ├── Solver.solve()                          → Various operating conditions: StaticResult
│   ├── ObjectiveFunction.sensitivity_analysis()→ Gradients by design block
│   ├── Updaters.update()                       → Local variable variables
│   ├── Updaters.update_variables()             → Write back to the design object
│   └── objective_function()                    → The losses recorded in this round
├── record_history()、print_info()
└── save()、Iteration notifications are now being sent out.
```

`step()` is responsible for the numerical phase, with historical records and storage occurring during the outer loop. The FEA model corresponds to the state that has been solved in this round, and the design variables are updated for subsequent calculations. During analysis, models and solutions from the same round are archived together. The updated parameters cannot be used to reconstruct the mesh and replace the original model.

`Controller.record_history()` Organize the objectives for this round, name the relevant indicators, estimate the time required for each stage, and generate grid-based statistics. Then, carry out the execution. `history.append(**record)` Add complete records. `History` Only those dictionaries composed of ordinary dictionaries are managed. `records` Lists, as well as functions for copying, saving, and reading data. It does not declare any business-related fields. `iteration` It is obtained from the number of records. Each cell in the CSV file uses JSON-style reserved field values. When reading the data, there is no need to infer the name suffix or array shape. The UI display layer expands the fields based on the content of the records. No modifications are required to the existing containers when adding new records. `get_metrics()` Only the amount of data provided for recording; the design gradient is derived from the calculation of the sensitivity of the objective function. For more details, please refer to… [Optimizing data flow](optimization.md#gradients) .

<a id="section-求解调度与初始解"></a>

## 5 Solving scheduling problems with initial solutions

`Solver` is set to default. `num_process=1` and `process_devices` specify the computing devices in the order of processes. By default, the CPU is used for the default process. `Controller.optdevice` and `Solver.process_devices` control the device configurations for the optimization side and the finite element side, respectively.

Each sub-list in `task_step_list` constitutes a scheduling task. The load cases in the sub-lists are solved in a sequential order. The solutions from the previous load case can be used as initial values for the subsequent load cases. The process pool allocates tasks to available working processes. The number of task groups does not need to be equal to the number of working processes. When no grouping is specified, the framework creates a separate task for each load case in the registration order.

When all parts in the model are `is_variable=False` and `U_guess` is not explicitly provided, the solver attempts to read the most recent saved result as the initial value. If no corresponding solution exists, `None` will be used. Parts whose shape or mesh changes with iteration should be declared as variable; material optimization on a fixed grid does not change this geometric property.

`U_guess` The mapping from the names of load cases to the initial value array is used, and then the load cases in the task group are extracted based on their names. The names of load cases and the row numbers in the UI list are processed separately, and the result files are named using the names of load cases.

<a id="section-分段运行与恢复"></a>

## 6 Segmented operation and recovery

`restart_per_iteration` The control work process returns in segments. After the outer tasks obtain the result directory, they continue from the saved state. The return of the work process does not mean that the optimization has reached a stable state.

The current `Controller.opt_loop()` still contains the return branch of `history.iteration == 2`. This is an additional condition for exiting the implementation, not a criterion for total iterations or goal convergence. When the operation mechanism is changed, both `Controller` and `opt_runner._run_task()` should be checked simultaneously; it is not possible to modify only one part of the loop.

`Controller._load_history()` After initializing the running object, read the state of the specified history, parameters, and updaters; `restart_optimization()` Then, the calculation loop begins. The original task file and the running snapshot are independent of each other. After changing the variable layout, material distribution, or the structure of the load case, the old state cannot be directly interpreted as the state of the new model.

<a id="section-运行目录与保存责任"></a>

## 7 Responsibility for running directories and storing files

| Location | Responsibility for writing and content |
|---|---|
| `scripts/` | The controller saves the task script and all dependencies required for execution. |
| `cache/` | Intermediate grids and geometric files used during the model construction process |
| `log/history_record.csv` | `History.save()` has been written in the history. |
| `log/geometry/`、`log/materials/` | The parameter interface stores the design state. |
| `log/geometryupdater/`、`log/materialupdater/` | The sub-optimizer saves its state based on the target interface. |
| `log/femodel&results/` | The target object stores the FE model and operating conditions obtained from each round of matching processes. Post-processing uses this information to reconstruct the deformed mesh. |

Before the first finite element solution, the controller saves the initial surface at step 0 in `log/geometry/<part_name>/`. The design surface for the k-th round of history reads the geometric checkpoints from the k-1 step. If the CPGEO reconstructs the control mesh before this round of solving, the design surface will display the checkpoints from before the reconstruction, and the load case deformation will show the finite element mesh obtained from this round of solving.

The sub-directories are allocated by the `pathlog_required()` of each object. `Controller.save()` should first save the parameters, solver, updater, and the current finite element model and results. Finally, write them into the historical records. The completed rounds in the historical records indicate that the corresponding archives have been saved. The analysis session only consumes the completed archives. For details on model pairing, independent solving, and export procedures, please refer to [Result analysis and export](results.md).

<a id="section-设备资源与错误边界"></a>

## 8 Devices, resources, and error boundaries

The controller is responsible for switching between object devices and clearing the cache during iterations. The sub-optimizer manages the Tensor and optimization status related to its own local problems. The finite element process receives independent copies of the model, avoiding the sharing of modifiable solution states.

Close the corresponding process pool before the work process terminates; UI operations are handled by the running session for the outer process group. The error logs, the exit of the work process, and whether the results are fully saved are different states. The recovery of calculations depends on a complete archive, not just on the process exit code or the existence of a certain file.

<a id="section-首轮失败与日志归档"></a>

## 9 First round failed, logs are being archived now.

`opt_runner._run_worker()` encountered a calculation error. The current result directory and the complete Python traceback have been recorded, and the issue will be re-raised later. The supervision loop distinguishes between “no complete iteration” and “existing complete checkpoints”: the former will fail and exit directly, while the latter will continue from the saved state. The process queue continuously receives completion events while the worker processes are alive, preventing mutual blocking between waiting and sending events.

`Params.save()` First create `log/params/`. After completing the screen capture, close the plotter in `finally`. The directory for the screenshots does not depend on the accidental creation by other modules. The pairing rules for geometry and finite element archives are still determined by the objects being saved and the complete history records.
