"""Standalone viewer for an existing optimization result.

``morphopt.opt_runner.view_optimization_result`` was removed (results are now
watched inside the MorphOpt UI, or via ``morphopt.ui.monitor`` for a one-off
standalone window).  This script opens the standalone monitor on a result folder.
"""

if __name__ == "__main__":
    from morphopt.ui.monitor import view_optimization_result

    view_optimization_result(
        '/run/media/song/SS/minedata/learning/code/projects/morphopt/ui_runs/results/shapeopt_untitled_T20260906_221229')
