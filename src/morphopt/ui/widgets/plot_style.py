"""Render-window settings shared by definition and result viewports."""
from pyvista.plotting.plotter import BasePlotter


def configure_plotter(plotter: BasePlotter) -> None:
    """Restore lighting and configure compositing for translucent surfaces."""
    # Depth peeling requires alpha planes and cannot use multisample AA.
    plotter.render_window.SetMultiSamples(0)
    plotter.render_window.SetAlphaBitPlanes(1)
    plotter.set_background("#0e131c")
    plotter.enable_lightkit()
    plotter.enable_depth_peeling(number_of_peels=8, occlusion_ratio=0.0)
