"""
MorphOpt UI package.

PySide6-based design tool split into TWO parts inside ONE window:
* definition part (Workbench)  -- build an optimization problem with an
  Abaqus-like model tree, preview the initial geometry / load steps in a
  PyVista viewport, and export/run a standard ``ThisController`` module;
* observer part (observe_panel) -- open results, start / continue / stop
  optimizations, and watch geometry / metrics / load cases by polling the
  result folder on disk.

Layout
------
ui/app.py            application entry point
ui/mainwindow.py     top-level window hosting the two parts
ui/workbench.py      definition workspace (problem-level actions live here)
ui/observe_panel.py  in-window observer + run/continue/stop controls
ui/model/            data model (ProblemDefinition tree)
ui/codegen/          ProblemDefinition -> ThisController source
ui/widgets/          modeltree / editor / stepmatrix / codeeditor / viewer
ui/schemes/          per-scheme templates + generators
ui/launcher.py       headless job launch / continue / result helpers

The design spec lives at the repository root in ``UIprompt.md``.
"""

from __future__ import annotations


def run_app() -> int:
    """Launch the MorphOpt UI (creates the QApplication and enters the loop)."""
    from .app import main

    return main()


__all__ = ["run_app"]
