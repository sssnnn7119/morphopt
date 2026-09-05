# Compatibility shim: the results observer now lives in morphopt.ui.monitor.
# (Redesigned layout - see UIprompt.md section A.)

from .ui.monitor import (  # noqa: F401
    ObserverUI as OptimizationMonitorUI,
    PyVistaQWidget,
    MonitorThread,
    run_ui,
    view_optimization_result,
)

__all__ = [
    'OptimizationMonitorUI',
    'PyVistaQWidget',
    'MonitorThread',
    'run_ui',
    'view_optimization_result',
]
