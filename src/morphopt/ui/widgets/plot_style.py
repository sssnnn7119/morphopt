"""Render-window settings shared by definition and result viewports."""

from pyvista.plotting.plotter import BasePlotter

from ..theme import theme_manager


def apply_plotter_theme(plotter: BasePlotter) -> None:
    """Apply the active theme's background to an existing render window."""
    plotter.set_background(theme_manager.palette.viewer_background)


def add_orientation_axes(plotter: BasePlotter) -> None:
    """Keep labelled global XYZ directions in the lower left of a result view."""
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


def configure_plotter(plotter: BasePlotter) -> None:
    """Restore lighting and configure compositing for translucent surfaces."""
    # Weighted order-independent transparency does not depend on actor order.
    plotter.render_window.SetMultiSamples(0)
    plotter.render_window.SetAlphaBitPlanes(1)
    apply_plotter_theme(plotter)
    plotter.enable_lightkit()
    # Use VTK's OIT pass rather than depth peeling: nested translucent shells
    # must survive hide/show and render-context changes in Qt viewports.
    for renderer in plotter.renderers:
        renderer.SetUseDepthPeeling(False)
        renderer.SetUseOIT(True)
