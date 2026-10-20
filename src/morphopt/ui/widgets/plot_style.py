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
    plotter.add_axes(interactive=False, color=theme_manager.palette.text,
                     x_color=x_color, y_color=y_color, z_color=z_color,
                     viewport=style.orientation_axes_viewport)


def configure_plotter(plotter: BasePlotter) -> None:
    """Restore lighting and configure compositing for translucent surfaces."""
    # Depth peeling requires alpha planes and cannot use multisample AA.
    plotter.render_window.SetMultiSamples(0)
    plotter.render_window.SetAlphaBitPlanes(1)
    apply_plotter_theme(plotter)
    plotter.enable_lightkit()
    # PyVista's enable_depth_peeling() probes support by rendering a separate,
    # default vtkRenderWindow. On Wayland that window may select GLX, which
    # conflicts with the EGL context owned by the embedded QtInteractor.
    for renderer in plotter.renderers:
        renderer.SetUseDepthPeeling(True)
        renderer.SetMaximumNumberOfPeels(theme_manager.palette.viewer.render.depth_peels)
        renderer.SetOcclusionRatio(
            theme_manager.palette.viewer.render.depth_peeling_occlusion_ratio
        )
