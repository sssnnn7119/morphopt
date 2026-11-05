"""Focused result-view tests for per-surface and control-net rendering."""

import numpy as np
import pyvista as pv

from morphopt.postprocess.visualization import (
    add_design_component,
    design_view_options,
)


class BspSurface:
    def __init__(self):
        self.control_points = np.array(
            [[x, y, 0.0] for y in range(2) for x in range(3)], dtype=float
        )
        self.model = type("BspModel", (), {"size": (2, 3)})()

    def get_mesh(self):
        return pv.Plane(i_resolution=4, j_resolution=2)


class BoundaryPart:
    def __init__(self):
        self.surfaceinterfaces = [BspSurface(), BspSurface()]
        self.name = "boundary"

    @property
    def num_surface_interfaces(self):
        return len(self.surfaceinterfaces)

    def plot(self, plotter):
        for index, surface in enumerate(self.surfaceinterfaces):
            plotter.add_mesh(
                surface.get_mesh(),
                name=f"boundary:{id(self)}:surface-{index}",
                color="#3f9fd6",
            )


def test_boundary_view_options_include_each_surface_and_control_net():
    keys = [view.key for view in design_view_options(BoundaryPart())]
    assert keys == [
        "all",
        "surface:0",
        "surface:0:control-net",
        "surface:1",
        "surface:1:control-net",
    ]


def test_control_net_is_rendered_as_overlay_actors():
    component = BoundaryPart()
    view = next(view for view in design_view_options(component) if view.control_net)
    plotter = pv.Plotter(off_screen=True, window_size=(300, 300))
    try:
        add_design_component(
            plotter,
            component,
            geometry_color="#3f9fd6",
            ambient=0.2,
            diffuse=0.8,
            specular=0.1,
            specular_power=20.0,
            boundary_shell_opacity=0.35,
            view=view,
        )
        names = {str(name) for name in plotter.actors}
        prefix = f"boundary:{id(component)}:surface-0"
        assert f"{prefix}:control-net" in names
        assert f"{prefix}:control-points" in names
        assert f"{prefix}" in names
    finally:
        plotter.close()
