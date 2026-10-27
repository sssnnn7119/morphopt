"""
MorphOpt UI package.

PySide6-based design tool with three persistent workspaces in one window:
* definition part (Workbench)  -- build an optimization problem with an
  Abaqus-like model tree, preview the initial geometry / load steps in a
  PyVista viewport, and export/run a standard ``ThisController`` module;
* observer part (observe_panel) -- open results, start / continue / stop
  optimizations, and watch geometry / metrics / load cases by polling the
  result folder on disk.
* finite elements -- import a completed iteration's exact mesh/material model,
  edit loads on a private copy, solve independently and export physical fields.

Layout
------
ui/app.py            application entry point
ui/mainwindow.py     File/Settings menus, document path and workspace navigation
ui/workbench.py      definition workspace
ui/observe_panel.py  in-window observer + run/continue/stop controls
ui/application/      definition, result and process application services
ui/fea_worker.py     isolated one-shot FEA and data-export worker
ui/cad_worker.py     isolated CAD-to-boundary conversion worker
ui/surface_export_worker.py  archived BoundaryPart surface export worker
postprocess/         archive reading, history GIF and surface export, and result analysis (no Qt)
ui/model/            data model (ProblemDefinition tree)
ui/codegen/          ProblemDefinition -> ThisController source
ui/widgets/          modeltree / editor / load_cases / codeeditor / viewer
ui/schemes/          code-defined scheme policies + snippets
ui/launcher.py       headless job launch / continue / result helpers

The maintainability contract lives in
``docs/codestructure/README.md`` and its UI model, application, presentation,
and results chapters.
"""

from __future__ import annotations


def run_app() -> int:
    """Launch the MorphOpt UI (creates the QApplication and enters the loop)."""
    from .app import main

    return main()


__all__ = ["run_app"]
