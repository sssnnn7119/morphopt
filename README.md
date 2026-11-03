# MorphOpt — A Differentiable Optimization Framework for Soft Structure & Morphology Design

**Developed by Zenan Song**

MorphOpt is a differentiable structural optimization framework that combines the adjoint method with automatic differentiation (AD). The sensitivity corresponds to the virtual work of residual force derivatives on the adjoint displacement field, computed via a single backpropagation through the residual graph. MorphOpt provides a unified interface for geometry, load, and material definition, calls torchfea for GPU-accelerated differentiable nonlinear FEA and adjoint-AD sensitivity, and employs a trust-region optimizer with L-BFGS for design updates. Validated on SIMP topology optimization with B-spline density fields and pneumatic soft robot shape optimization with deformation-dependent follower loads.

## Features

- Custom model definition covering geometry, material, and load parameters
- Differentiable FEA via torchfea with automatic solving and sensitivity propagation
- L-BFGS and trust-region methods for parameter updates within a subproblem framework
- Component customization through framework class inheritance

## Quick Start

Install the package:

```bash
pip install morphopt
```

Requirements: Python ≥ 3.12; a PyTorch **float64** build is recommended.

> **Optimizations are run as scripts.** Each job is an ordinary Python file that calls `morphopt.start_optimization(...)`. It runs headlessly in a terminal (local or remote), and optimization runs can be stopped and resumed from their result folders. Script execution is the recommended way to run jobs.

1. **Run a minimal example** — execute it directly in a terminal:

   ```bash
   # Shape optimization (pneumatic bending actuator)
   python examples/bending_actuator/bending_actuator.py

   # SIMP topology optimization (compliant gripper)
   python examples/simp_gripper/simp_gripper.py
   ```

2. **Run a custom job** — copy an example as a starting point, configure the geometry, material, loads, updater, and objective, and launch it as a script:

   ```bash
   python my_task.py
   ```

   Each run writes its results (logs, FEA files, restart script) into a timestamped result folder under the run root.

3. **Graphical interface.** The GUI supports problem definition, optimization monitoring, and result inspection in one window. It also exports runnable Python scripts (`.py`) for execution in the UI or a terminal.

   ```bash
   morphopt-ui            # console command, available after `pip install morphopt`
   # Alternative entry point: python -m morphopt.ui
   ```

The GUI opens directly into the full definition workbench with its standard sections present and no problem setup prefilled. Definitions can be created directly in the workbench or generated through **Quickstart**. Quickstart provides shape and topology optimization settings, geometry definitions, and weighted objective terms with associated load conditions. Workspace terms select their driving pressure channels and use boundary integration. Generated problems stay editable and can be saved or exported as runnable scripts.

The [UI quick start](docs/UIguide.md) covers the complete example from model definition to optimization and result inspection. The [script quick start](docs/scriptguide.md) provides the equivalent runnable Python task.

### Run the UI in a virtual environment

Create and activate a Conda environment, then install and launch MorphOpt:

```bash
conda create -n morphopt python=3.12
conda activate morphopt
python -m pip install morphopt
morphopt-ui
```

For an existing environment, activate it instead. To run the source checkout, install the project in editable mode from its root directory:

```bash
conda activate morphopt
cd /path/to/morphopt
python -m pip install -e .
morphopt-ui
```

Replace the environment name and project path as appropriate. Installation is required once per environment; subsequent launches require only environment activation and the launch command. The equivalent module entry point uses the active environment's Python interpreter:

```bash
python -m morphopt.ui
```

### Numeric configuration

Shared UI defaults and tunable kernel parameters live in [`src/morphopt/constants.py`](src/morphopt/constants.py), grouped under `CONSTANT.UI` and `CONSTANT.KERNEL`. Code accesses them directly, for example `CONSTANT.UI.VIEWER.RENDER.LABEL_FONT_SIZE` or `CONSTANT.KERNEL.SOLVER.NUM_PROCESS`. Edit a value there to change its default; restart MorphOpt for the change to take effect. Coordinate indices, tensor dimensions, and coefficients that define mathematical formulas remain in code. UI translations remain in JSON files under `src/morphopt/ui/locales/`.

### Documentation

| Workflow | Quick start | Module and interface reference |
|---|---|---|
| Python script | [Start an optimization](docs/scriptguide.md) | [Define and extend each module](docs/scriptreference.md) |
| Graphical UI | [Create and run the example](docs/UIguide.md) | [Modules, parameters and interface definitions](docs/UIreference.md) |

The [documentation index](docs/README.md) includes the reading order and automatic section numbering commands. Theory and code architecture are documented separately under `docs/theory/` and `docs/codestructure/`.

## Directory Overview

- `src/morphopt/`
  - `optcore` — Core package (controller, params, solver, objective, updaters)
  - `shapeopt/` — B-spline shape optimization
  - `simp/` — SIMP topology optimization
  - `codesign/` — Shell co-design (shape + material)
  - `ui/` — PySide6 graphical UI (definition + observer in one window)
- [`examples/`](examples/README.md) — Runnable tasks, UI definitions, input geometry assets, and case notes
- `docs/` — Usage guides, API reference, theory papers
- `tests/` — Gradient checks, geometry tests, UI tests
- `ui_runs/` — runs launched from the UI and their results (`<label>_T<timestamp>/`)

## License

Research use preferred. For production or commercial use, please evaluate and ensure numerical and engineering robustness first.

## Citation

Research using MorphOpt can cite the following publications:

- TRO 2023

```
@ARTICLE{10296178,
  author={Chen, Feifei and Song, Zenan and Chen, Shitong and Gu, Guoying and Zhu, Xiangyang},
  journal={IEEE Transactions on Robotics}, 
  title={Morphological Design for Pneumatic Soft Actuators and Robots With Desired Deformation Behavior}, 
  year={2023},
  volume={39},
  number={6},
  pages={4408-4428},
  keywords={Shape;Surface morphology;Robots;Splines (mathematics);Pneumatic systems;Actuators;Soft robotics;Morphological design;shape optimization;pneumatic soft robots},
  doi={10.1109/TRO.2023.3323825}}
```

- TRO 2026

```
@ARTICLE{11617347,
  author={Song, Zenan and Chen, Feifei and Gu, Guoying and Zhu, Xiangyang},
  journal={IEEE Transactions on Robotics}, 
  title={Continuum Jacobian-Based Computational Morphogenesis for Soft Robotic Workspace Optimization}, 
  year={2026},
  volume={42},
  number={},
  pages={3048-3068},
  keywords={Optimization;Design methodology;Surfaces;Modeling;End effectors;Shape;Soft robotics;Deformation;Vectors;Robots;Computational morphogenesis;Jacobian shape derivative;soft robotics;workspace optimization},
  doi={10.1109/TRO.2026.3716051}}

```

- TMECH 2026

```
@ARTICLE{11536090,
  author={Song, Zenan and Zhou, Guozhen and Chen, Feifei},
  journal={IEEE/ASME Transactions on Mechatronics}, 
  title={Contact-Aware Soft Robot Design via Differentiable Simulation and Morphological Optimization}, 
  year={2026},
  volume={31},
  number={4},
  pages={4576-4584},
  keywords={Contacts;Optimization;Modeling;Design methodology;Soft robotics;Surfaces;Actuators;Materials;Force;Simulation;Differentiable contact modeling;morphological design;soft robotics},
  doi={10.1109/TMECH.2026.3692920}}

```


