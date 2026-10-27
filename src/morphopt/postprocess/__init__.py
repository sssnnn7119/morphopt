"""Read optimization results, evaluate fields, and export post-processing data."""

from .archive import (
    IterationModel,
    OptimizationArchive,
    last_completed_iteration,
)
from .context import cpu_torch_defaults
from .contours import CONTOUR_FIELDS, ContourField, ResultContours
from .exporters import (
    CSVExporter,
    EXPORTERS,
    NPZExporter,
    ResultExporter,
    export_results,
    export_saved_results,
)
from .fields import (
    RESULT_FIELDS,
    FieldContext,
    ResultField,
    ResultLocation,
    ResultTable,
    available_fields,
)
from .history_gif import export_history_gif
from .native import NativeResultSnapshot, export_native_results, normalize_export_name
from .rendering import (
    add_deformation_mesh,
    add_design_component,
    configure_plotter,
)
from .surface_export import (
    BoundarySurfaceExport,
    boundary_surface_options,
    export_boundary_surfaces,
)

__all__ = [
    "BoundarySurfaceExport",
    "CONTOUR_FIELDS",
    "CSVExporter",
    "ContourField",
    "EXPORTERS",
    "FieldContext",
    "IterationModel",
    "NPZExporter",
    "NativeResultSnapshot",
    "OptimizationArchive",
    "RESULT_FIELDS",
    "ResultContours",
    "ResultExporter",
    "ResultField",
    "ResultLocation",
    "ResultTable",
    "add_deformation_mesh",
    "add_design_component",
    "available_fields",
    "boundary_surface_options",
    "configure_plotter",
    "cpu_torch_defaults",
    "export_boundary_surfaces",
    "export_history_gif",
    "export_native_results",
    "export_results",
    "export_saved_results",
    "last_completed_iteration",
    "normalize_export_name",
]
