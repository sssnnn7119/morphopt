"""PyVista scene operations shared by the UI and post-processing exports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pyvista as pv
    from pyvista.plotting.plotter import BasePlotter


def configure_plotter(plotter: BasePlotter, background: str) -> None:
    """Configure a render window using an explicit caller-selected background."""
    plotter.render_window.SetMultiSamples(0)
    plotter.render_window.SetAlphaBitPlanes(1)
    plotter.set_background(background)
    plotter.enable_lightkit()
    for renderer in plotter.renderers:
        renderer.SetUseDepthPeeling(False)
        renderer.SetUseOIT(True)


def add_design_component(
    plotter: BasePlotter,
    component: Any | None,
    *,
    geometry_color: str,
    ambient: float,
    diffuse: float,
    specular: float,
    specular_power: float,
    boundary_shell_opacity: float,
) -> None:
    """Draw one design component with explicit visual properties."""
    from pyvista import Actor

    if component is not None:
        existing = set(plotter.actors)
        component.plot(plotter=plotter)
        surface_count = int(getattr(component, "num_surface_interfaces", 0) or 0)
        for name, actor in plotter.actors.items():
            if name in existing or not isinstance(actor, Actor):
                continue
            mapper = actor.mapper
            if mapper is not None and mapper.scalar_visibility:
                continue
            actor.prop.color = geometry_color
            actor.prop.ambient = ambient
            actor.prop.diffuse = diffuse
            actor.prop.specular = specular
            actor.prop.specular_power = specular_power
            if surface_count > 1 and str(name).endswith("surface-0"):
                actor.prop.opacity = boundary_shell_opacity
    plotter.show_axes()


def add_deformation_mesh(
    plotter: BasePlotter, mesh: pv.DataSet, color: str
) -> None:
    """Draw one archived deformation mesh."""
    plotter.add_mesh(
        mesh,
        color=color,
        opacity=1.0,
        show_edges=True,
        name="deformation-mesh",
    )
    plotter.show_axes()


def set_camera(plotter: pv.Plotter, camera: dict[str, Any]) -> None:
    """Apply a serialized camera position and projection to the render window."""
    position = camera.get("position")
    if position:
        plotter.camera_position = tuple(
            tuple(float(value) for value in point) for point in position
        )
    active = plotter.camera
    active.SetParallelProjection(bool(camera.get("parallel_projection", False)))
    active.SetParallelScale(
        float(camera.get("parallel_scale", active.GetParallelScale()))
    )
    active.SetViewAngle(float(camera.get("view_angle", active.GetViewAngle())))
    plotter.reset_camera_clipping_range()

