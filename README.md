# MorphOpt — A Differentiable Optimization Framework for Soft Structure & Morphology Design

**Developed by Zenan Song**

A differentiable structural optimization framework that eliminates manual sensitivity derivation by fusing the adjoint method with automatic differentiation (AD). The sensitivity corresponds to the virtual work of residual force derivatives on the adjoint displacement field, computed via a single backpropagation through the residual graph. MorphOpt provides a unified interface for geometry, load, and material definition, calls torchfea for GPU-accelerated differentiable nonlinear FEA and adjoint-AD sensitivity, and employs a trust-region optimizer with L-BFGS for design updates. Validated on SIMP topology optimization with B-spline density fields and pneumatic soft robot shape optimization with deformation-dependent follower loads.

## Features

- Custom model definition covering geometry, material, and load parameters
- Differentiable FEA via torchfea with automatic solving and sensitivity propagation
- L-BFGS and trust-region methods for parameter updates within a subproblem framework
- Fully extensible via inheritance — users customize every component in their definition scripts

## Quick Start

```bash
pip install morphopt
```

1. Install dependencies. Python ≥ 3.12, PyTorch (float64) recommended.
2. Run a minimal example:

```bash
# Shape optimization (pneumatic bending actuator)
python examples/bendingactuator.py

# SIMP topology optimization (compliant gripper)
python examples/gripper.py
```

3. **Launch the GUI (recommended)** — define, run and observe an optimization all inside one window:

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
  - [`UI_usage.md`](docs/UI_usage.md) — graphical UI user guide
- `tests/` — Gradient checks, geometry tests, UI tests
- `ui_runs/` — runs launched from the UI and their results (`<label>_T<timestamp>/`)

## License

Research use preferred. For production or commercial use, please evaluate and ensure numerical and engineering robustness first.

## Citation

If you use MorphOpt in your research, please cite:

- TRO 2023 — Morphology Design
- TRO 2026 — Jacobian-based Optimization
- TMECH 2026 — Contact-aware Design

