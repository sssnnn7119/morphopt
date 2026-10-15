"""Render-window settings shared by definition and result viewports."""
from pyvista.plotting.plotter import BasePlotter
from ...constants import CONSTANT
def configure_plotter(plotter: BasePlotter) -> None:
    """Restore lighting and configure compositing for translucent surfaces."""
    # Depth peeling requires alpha planes and cannot use multisample AA.
    plotter.render_window.SetMultiSamples(0)
    plotter.render_window.SetAlphaBitPlanes(1)
    plotter.set_background(CONSTANT.UI.VIEWER.RENDER.BACKGROUND)
    plotter.enable_lightkit()
    plotter.enable_depth_peeling(
        number_of_peels=CONSTANT.UI.VIEWER.RENDER.DEPTH_PEELS,
        occlusion_ratio=CONSTANT.UI.VIEWER.RENDER.DEPTH_PEELING_OCCLUSION_RATIO,
    )
