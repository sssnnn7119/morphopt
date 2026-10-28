"""Build post-processing scenes and render history frames without file I/O."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from .archive import OptimizationArchive

if TYPE_CHECKING:
    import numpy as np
    import pyvista as pv
    from pyvista.plotting.plotter import BasePlotter


def configure_plotter(
    plotter: BasePlotter, background: str, *, light_intensity: float = 1.0
) -> None:
    """Configure a render window using an explicit caller-selected background."""
    plotter.render_window.SetMultiSamples(0)
    plotter.render_window.SetAlphaBitPlanes(1)
    plotter.set_background(background)
    plotter.enable_lightkit()
    for renderer in plotter.renderers:
        for light in renderer.lights:
            light.intensity *= light_intensity
        renderer.SetUseDepthPeeling(False)
        renderer.SetUseOIT(True)


def apply_mesh_style(
    plotter: BasePlotter, *, ambient: float, diffuse: float, specular: float,
    specular_power: float, smooth_shading: bool = True,
) -> None:
    """Update lit mesh actors, preserving scalar maps, colors, and overlays."""
    from pyvista import Actor

    for actor in plotter.actors.values():
        if isinstance(actor, Actor) and actor.prop.lighting:
            actor.prop.ambient = ambient
            actor.prop.diffuse = diffuse
            actor.prop.specular = specular
            actor.prop.specular_power = specular_power
            actor.prop.interpolation = "phong" if smooth_shading else "flat"


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


def history_frames(
    archive: OptimizationArchive,
    iterations: range,
    *,
    mode: str,
    target: dict[str, str],
    camera: dict[str, Any],
    window_size: tuple[int, int],
    style: dict[str, Any],
) -> Iterator[np.ndarray]:
    """Yield RGB frames; closing the iterator releases its render window."""
    import pyvista as pv

    if mode not in {"design", "deformation"}:
        raise ValueError(f"Unsupported history GIF mode: {mode}")
    if mode == "design":
        if archive.initialize_params() is None:
            raise ValueError("The archived optimization model is unavailable.")
    elif not target.get("case"):
        raise ValueError("Select a load case before exporting deformation history.")

    size = tuple(max(1, int(value)) for value in window_size)
    plotter = pv.Plotter(off_screen=True, window_size=size)
    try:
        for iteration in iterations:
            plotter.clear()
            configure_plotter(
                plotter, background=style["background"],
                light_intensity=style.get("light_intensity", 1.0),
            )
            if mode == "design":
                archive.load_parameters(iteration)
                component = next(
                    (
                        component
                        for category, component in archive.visualizable_components()
                        if category == target.get("category")
                        and component.name == target.get("name")
                    ),
                    None,
                )
                if component is None:
                    raise ValueError("The selected design component is unavailable.")
                add_design_component(
                    plotter,
                    component,
                    geometry_color=style["geometry_color"],
                    ambient=style["mesh_ambient"],
                    diffuse=style["mesh_diffuse"],
                    specular=style["mesh_specular"],
                    specular_power=style["mesh_specular_power"],
                    boundary_shell_opacity=style["boundary_shell_opacity"],
                )
            else:
                mesh = archive.deformation_mesh(target["case"], iteration)
                if mesh is None:
                    continue
                add_deformation_mesh(plotter, mesh, style["deformation_color"])
            apply_mesh_style(
                plotter, ambient=style["mesh_ambient"], diffuse=style["mesh_diffuse"],
                specular=style["mesh_specular"], specular_power=style["mesh_specular_power"],
                smooth_shading=style.get("smooth_shading", True),
            )
            set_camera(plotter, camera)
            plotter.add_text(
                f"Iteration {iteration}",
                position="upper_left",
                font_size=12,
                color=style["text_color"],
            )
            plotter.render()
            yield plotter.screenshot(return_img=True)
    finally:
        plotter.close()
