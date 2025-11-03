# Jobs structure (standardized)

All job scripts now follow a unified pattern similar to `Jobs/examples/displacement.py`:

- Define an `ObjectiveFunction` subclass of `GLOBAL.ObjectiveFunction` and set `GLOBAL.obj_fun`.
- Define `Params(_Params)` with nested parameter groups:
  - `SurfaceParams(_SurfacesParams)` builds design surfaces (use `self.BSP.*`).
  - `LoadParams(_LoadsParams)` defines `load_steps` via `self.LoadStep()` and `self.PressureInterface(...)`.
  - `MaterialParams(_Materials)` sets material constants.
- Define `Generator(_Generator)`, `Solver(_MorphSolver)`, `Updater(_Updaters)` with an inner `UpdaterSurfaces(_UpdaterSurfaces)` that adds objectives via `self.objectivefuncs.*`.
- End with a `__main__` block that initializes paths and runs `controller.opt_loop()`.

Quick start

- Use `Jobs/examples/displacement.py` as a template.
- When adding objectives in `UpdaterSurfaces`, instantiate the class and register with `self.add_objective_function(...)`.

Notes

- Load steps are consumed during sensitivity evaluation; only loads added in `Params.LoadParams` are applied in that phase.
- If your solver adds special loads (e.g., contacts), ensure your objective and solver logic account for `delete_all_loads()` calls inside shape sensitivity routines.
