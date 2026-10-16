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
    # PyVista's enable_depth_peeling() probes support by rendering a separate,
    # default vtkRenderWindow. On Wayland that window may select GLX, which
    # conflicts with the EGL context owned by the embedded QtInteractor.
    for renderer in plotter.renderers:
        renderer.SetUseDepthPeeling(True)
        renderer.SetMaximumNumberOfPeels(CONSTANT.UI.VIEWER.RENDER.DEPTH_PEELS)
        renderer.SetOcclusionRatio(
            CONSTANT.UI.VIEWER.RENDER.DEPTH_PEELING_OCCLUSION_RATIO
        )
