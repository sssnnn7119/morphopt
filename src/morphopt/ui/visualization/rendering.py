"""Shared PyVista rendering for preview and optimization result views."""

from __future__ import annotations

from pyvista.plotting.plotter import BasePlotter

from ...postprocess.visualization import (
    apply_mesh_style,
)
from ...postprocess.visualization import (
    configure_plotter as configure_result_plotter,
)
from ..theme import theme_manager
from ..theme.visualization import VisualizationSettings, visualization_manager


def apply_plotter_theme(plotter: BasePlotter, background: str | None = None) -> None:
    """Apply the active viewer background, or an explicit render background."""
    plotter.set_background(background or theme_manager.palette.viewer.render.background)


def add_orientation_axes(plotter: BasePlotter) -> None:
    """Add labelled global XYZ directions in the lower-left corner."""
    style = theme_manager.palette.viewer.render
    x_color, y_color, z_color = style.orientation_axis_colors
    plotter.add_axes(
        interactive=False,
        color=theme_manager.palette.text,
        x_color=x_color,
        y_color=y_color,
        z_color=z_color,
        viewport=style.orientation_axes_viewport,
    )


def configure_plotter(
    plotter: BasePlotter,
    background: str | None = None,
    *,
    settings: VisualizationSettings | None = None,
) -> None:
    """Apply the UI palette through the shared post-processing renderer."""
    settings = settings or visualization_manager.settings
    configure_result_plotter(
        plotter,
        background or theme_manager.palette.viewer.render.background,
        light_intensity=settings.light_intensity,
    )
    if bool(plotter.camera.parallel_projection) != settings.parallel_projection:
        if settings.parallel_projection:
            plotter.enable_parallel_projection()
        else:
            plotter.disable_parallel_projection()


def apply_visualization(
    plotter: BasePlotter, settings: VisualizationSettings | None = None
) -> None:
    apply_mesh_style(
        plotter, **(settings or visualization_manager.settings).material_options()
    )
