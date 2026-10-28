"""Post-processing: archive access, physical fields, file export, and scenes.

Use OptimizationArchive for saved iterations and FiniteElementResults for one
finite-element solution. File-writing operations are collected in exports;
scene helpers are available from visualization.
"""

from ._runtime import cpu_torch_defaults
from .archive import IterationModel, OptimizationArchive, last_completed_iteration
from .exports import (
    TABLE_WRITERS,
    BoundarySurfaceInfo,
    NativeResultSnapshot,
    TableWriter,
    boundary_surface_options,
    export_boundary_surfaces,
    export_fields,
    export_history_gif,
    export_native_results,
    export_saved_fields,
    normalize_export_name,
)
from .fields import (
    CONTOUR_FIELDS,
    RESULT_FIELDS,
    ContourField,
    FiniteElementResults,
    ResultField,
    ResultLocation,
    ResultTable,
)

__all__ = [
    "CONTOUR_FIELDS",
    "RESULT_FIELDS",
    "TABLE_WRITERS",
    "BoundarySurfaceInfo",
    "ContourField",
    "FiniteElementResults",
    "IterationModel",
    "NativeResultSnapshot",
    "OptimizationArchive",
    "ResultField",
    "ResultLocation",
    "ResultTable",
    "TableWriter",
    "boundary_surface_options",
    "cpu_torch_defaults",
    "export_boundary_surfaces",
    "export_fields",
    "export_history_gif",
    "export_native_results",
    "export_saved_fields",
    "last_completed_iteration",
    "normalize_export_name",
]
