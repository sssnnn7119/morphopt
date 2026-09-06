# MorphOpt — A Differentiable Optimization Framework for Soft Structure & Morphology Design

**Developed by Zenan Song**

A differentiable structural optimization framework that eliminates manual sensitivity derivation by fusing the adjoint method with automatic differentiation (AD). The sensitivity corresponds to the virtual work of residual force derivatives on the adjoint displacement field, computed via a single backpropagation through the residual graph. MorphOpt provides a unified interface for geometry, load, and material definition, calls torchfea for GPU-accelerated differentiable nonlinear FEA and adjoint-AD sensitivity, and employs a trust-region optimizer with L-BFGS for design updates. Validated on SIMP topology optimization with B-spline density fields and pneumatic soft robot shape optimization with deformation-dependent follower loads.

## Features

- Custom model definition covering geometry, material, and load parameters
- Differentiable FEA via torchfea with automatic solving and sensitivity propagation
- L-BFGS and trust-region methods for parameter updates within a subproblem framework
- Fully extensible via inheritance — users customize every component in their definition scripts

## Quick Start

Install the package:

```bash
pip install morphopt
```

Requirements: Python ≥ 3.12; a PyTorch **float64** build is recommended.

> **Optimizations are run as scripts.** Each job is an ordinary Python file that calls `morphopt.start_optimization(...)`. It runs headlessly in a terminal (local or remote), and a finished run can be stopped and resumed later from its result folder. Script execution is the recommended way to run jobs.

1. **Run a minimal example** — execute it directly in a terminal:

   ```bash
   # Shape optimization (pneumatic bending actuator)
   python examples/bendingactuator.py

   # SIMP topology optimization (compliant gripper)
   python examples/gripper.py
   ```

2. **Run your own job** — copy an example as a starting point, adapt the definition (geometry, material, load, updater, objective), and launch it as a script:

   ```bash
   python my_task.py
   ```

   Each run writes its results (logs, FEA files, restart script) into a timestamped result folder under the run root.

3. **Optional — the GUI** is a visual aid for authoring a problem definition and inspecting finished runs in one window. It can also export a runnable script (`.py`), which you can either run directly in the UI or further customize before executing it via Step 2 in a terminal.

   ```bash
   morphopt-ui            # console command, available after `pip install morphopt`
   # python -m morphopt.ui works too (handy when running from a source code directory)
   ```

The complete UI workflow (definition part + observer part) is described in [`docs/UI_usage.md`](docs/UI_usage.md).

Further references:

- Task definition guide: `docs/module_definition_guide.md`
- Module API reference: `docs/module_reference.md`
- Theory & papers: `docs/theory/`

## Directory Overview

- `src/morphopt/`
  - `optcore` — Core package (controller, params, solver, objective, updaters)
  - `shapeopt/` — B-spline shape optimization
  - `simp/` — SIMP topology optimization
  - `codesign/` — Shell co-design (shape + material)
  - `ui/` — PySide6 graphical UI (definition + observer in one window)
- `examples/` — Example tasks (bending actuator, gripper, etc.)
- `docs/` — Usage guides, API reference, theory papers
- `tests/` — Gradient checks, geometry tests, UI tests
- `ui_runs/` — runs launched from the UI and their results (`<label>_T<timestamp>/`)

## License

Research use preferred. For production or commercial use, please evaluate and ensure numerical and engineering robustness first.

## Citation

If you use MorphOpt in your research, please cite:

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


