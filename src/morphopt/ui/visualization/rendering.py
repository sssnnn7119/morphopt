"""Shared PyVista rendering for preview and optimization result views."""

from __future__ import annotations

from pyvista.plotting.plotter import BasePlotter

from ...postprocess import (
    add_deformation_mesh,
    add_design_component,
    configure_plotter as configure_result_plotter,
)
from ..theme import theme_manager


def apply_plotter_theme(
    plotter: BasePlotter, background: str | None = None
) -> None:
    """Apply the active viewer background, or an explicit render background."""
    plotter.set_background(background or theme_manager.palette.viewer_background)


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
    plotter: BasePlotter, background: str | None = None
) -> None:
    """Apply the UI palette through the shared post-processing renderer."""
    configure_result_plotter(
        plotter, background or theme_manager.palette.viewer_background
    )
