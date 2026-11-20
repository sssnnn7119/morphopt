"""Build post-processing scenes and render history frames without file I/O."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .archive import OptimizationArchive
from .snapshots import SavedComponent

if TYPE_CHECKING:
    import numpy as np
    import pyvista as pv
    from pyvista.plotting.plotter import BasePlotter


@dataclass(frozen=True)
class DesignView:
    """One renderable view of an optimization design component."""

    key: str
    surface_index: int | None = None
    control_net: bool = False


def design_view_options(component: SavedComponent | None) -> tuple[DesignView, ...]:
    """Return the views supported by one design component.

    Boundary parts expose the complete assembly and one focused view per surface.  B-spline and
    CPGEO surfaces additionally expose their control net.  Other components, including SIMP
    materials, deliberately keep one view because they have no alternate geometric
    representation.

    Args:
        component (SavedComponent | None): Design component indexed in the iteration snapshot.

    Returns:
        tuple[DesignView, ...]: The views supported by one design component.
    """
    if component is None:
        return ()
    surface_count = sum(key.startswith("surface_") for key in component.files)
    if not surface_count:
        return (DesignView("default"),)
    views = [DesignView("all")]
    for index in range(surface_count):
        views.append(DesignView(f"surface:{index}", index))
        if f"net_{index}" in component.files:
            views.append(DesignView(f"surface:{index}:control-net", index, True))
    return tuple(views)


def configure_plotter(
    plotter: BasePlotter, background: str, *, light_intensity: float = 1.0
) -> None:
    """Configure a render window using an explicit caller-selected background.

    Args:
        plotter (BasePlotter): PyVista plotter receiving the scene; None creates a new plotter.
        background (str): Optional background color; None uses the active visualization palette.
        light_intensity (float): Multiplier applied to the renderer's light-kit intensities.
    """
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
    plotter: BasePlotter,
    *,
    ambient: float,
    diffuse: float,
    specular: float,
    specular_power: float,
    smooth_shading: bool = True,
) -> None:
    """Update lit mesh actors, preserving scalar maps, colors, and overlays.

    Args:
        plotter (BasePlotter): PyVista plotter receiving the scene; None creates a new plotter.
        ambient (float): Ambient surface-lighting coefficient.
        diffuse (float): Diffuse surface-lighting coefficient.
        specular (float): Specular surface-lighting coefficient.
        specular_power (float): Exponent controlling specular highlight sharpness.
        smooth_shading (bool): Use interpolated surface normals when True; otherwise use flat
            shading.
    """
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
    component: SavedComponent | None,
    *,
    geometry_color: str,
    ambient: float,
    diffuse: float,
    specular: float,
    specular_power: float,
    boundary_shell_opacity: float,
    view: DesignView | None = None,
) -> None:
    """Draw one design component with explicit visual properties.

    The default view displays the complete component.

    Args:
        plotter (BasePlotter): PyVista plotter receiving the scene; None creates a new plotter.
        component (SavedComponent | None): Design component indexed in the iteration snapshot.
        geometry_color (str): Base color of geometry actors that do not display a scalar field.
        ambient (float): Ambient surface-lighting coefficient.
        diffuse (float): Diffuse surface-lighting coefficient.
        specular (float): Specular surface-lighting coefficient.
        specular_power (float): Exponent controlling specular highlight sharpness.
        boundary_shell_opacity (float): Opacity of the exterior boundary when showing a complete
            multi-surface component.
        view (DesignView | None): Requested design-component view, including an optional surface
            or control-point net.
    """
    from pyvista import Actor

    if component is not None:
        existing = set(plotter.actors)
        surface_count = sum(key.startswith("surface_") for key in component.files)
        index = view.surface_index if view else None
        for key in component.files:
            if key.startswith("net_") or (index is not None and key != f"surface_{index}"):
                continue
            mesh = component.mesh(key)
            if "density_max" in mesh.field_data and "density" in mesh.point_data:
                from ..simp.simpmaterial import plot_density
                plot_density(plotter, mesh, float(mesh.field_data["density_max"][0]))
            elif mesh.n_points:
                plotter.add_mesh(mesh, name=key.replace("surface_", "surface-"),
                                 color=geometry_color if surface_count else None,
                                 smooth_shading=bool(surface_count))
        if view and view.control_net:
            _draw_control_net(plotter, component.mesh(f"net_{index}"), id(component), index)
        for name, actor in plotter.actors.items():
            if name in existing or not isinstance(actor, Actor):
                continue
            if str(name).endswith((":control-net", ":control-points")):
                continue
            mapper = actor.mapper
            if mapper is not None and mapper.scalar_visibility:
                continue
            actor.prop.color = geometry_color
            actor.prop.ambient = ambient
            actor.prop.diffuse = diffuse
            actor.prop.specular = specular
            actor.prop.specular_power = specular_power
            if (
                (view is None or view.surface_index is None)
                and surface_count > 1
                and str(name).endswith("surface-0")
            ):
                actor.prop.opacity = boundary_shell_opacity
    plotter.show_axes()


def _draw_control_net(plotter, net, component_id: int, index: int) -> None:
    if net.n_lines:
        plotter.add_mesh(
            net,
            name=f"boundary:{component_id}:surface-{index}:control-net",
            color="#F2B84B",
            line_width=1.5,
            render_lines_as_tubes=True,
        )
    plotter.add_points(
        net.points,
        name=f"boundary:{component_id}:surface-{index}:control-points",
        color="#FFF1B8",
        point_size=4.5,
        render_points_as_spheres=True,
    )


def add_deformation_mesh(plotter: BasePlotter, mesh: pv.DataSet, color: str) -> None:
    """Draw one archived deformation mesh.

    Args:
        plotter (BasePlotter): PyVista plotter receiving the scene; None creates a new plotter.
        mesh (pv.DataSet): Mesh used for geometric evaluation or visualization.
        color (str): Actor or annotation color accepted by PyVista.
    """
    plotter.add_mesh(
        mesh,
        color=color,
        opacity=1.0,
        show_edges=True,
        name="deformation-mesh",
    )
    plotter.show_axes()


def set_camera(plotter: pv.Plotter, camera: dict[str, Any]) -> None:
    """Apply a serialized camera position and projection to the render window.

    Args:
        plotter (pv.Plotter): PyVista plotter receiving the scene; None creates a new plotter.
        camera (dict[str, Any]): Camera state captured from the currently displayed viewport.
    """
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
    """Yield RGB frames; closing the iterator releases its render window.

    Args:
        archive (OptimizationArchive): Optimization archive supplying saved design and result
            states.
        iterations (range): Completed iteration indices included in the requested export.
        mode (str): Operation mode selecting the applicable computation or visualization path.
        target (dict[str, str]): Target interface or selection receiving the operation.
        camera (dict[str, Any]): Camera state captured from the currently displayed viewport.
        window_size (tuple[int, int]): Output image dimensions (width, height) in pixels.
        style (dict[str, Any]): Explicit colors, lighting, opacity, and material settings for
            rendering.

    Returns:
        Iterator[np.ndarray]: Yield RGB frames; closing the iterator releases its render window.
    """
    import pyvista as pv

    if mode not in {"design", "deformation"}:
        raise ValueError(f"Unsupported history GIF mode: {mode}")
    if mode == "deformation" and not target.get("case"):
        raise ValueError("Select a load case before exporting deformation history.")

    size = tuple(max(1, int(value)) for value in window_size)
    plotter = pv.Plotter(off_screen=True, window_size=size)

    def render_frame(iteration: int) -> np.ndarray | None:
        nonlocal camera
        plotter.clear()
        configure_plotter(
            plotter,
            background=style["background"],
            light_intensity=style.get("light_intensity", 1.0),
        )
        if mode == "design":
            component = archive.design_view_component(target["category"], target["name"], iteration)
            views = {v.key: v for v in design_view_options(component)}
            view = views[target["view"]] if "view" in target else None
            add_design_component(
                plotter, component,
                view=view,
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
                return None
            add_deformation_mesh(plotter, mesh, style["deformation_color"])
        apply_mesh_style(
            plotter,
            ambient=style["mesh_ambient"],
            diffuse=style["mesh_diffuse"],
            specular=style["mesh_specular"],
            specular_power=style["mesh_specular_power"],
            smooth_shading=style.get("smooth_shading", True),
        )
        if "direction" in camera:
            plotter.view_vector(camera["direction"], viewup=camera["up"], render=False)
            camera = {
                "position": plotter.camera_position,
                "parallel_scale": plotter.camera.parallel_scale,
                "parallel_projection": camera.get("parallel_projection", False),
            }
        set_camera(plotter, camera)
        plotter.add_text(
            f"Iteration {iteration}",
            position="upper_left",
            font_size=12,
            color=style["text_color"],
        )
        plotter.render()
        return plotter.screenshot(return_img=True)

    try:
        if iterations and "direction" in camera:
            # Frame the preset on the preview iteration and keep that camera for the animation.
            last_frame = render_frame(iterations[-1])
            iterations = iterations[:-1]
        else:
            last_frame = None
        for iteration in iterations:
            frame = render_frame(iteration)
            if frame is not None:
                yield frame
        if last_frame is not None:
            yield last_frame
    finally:
        plotter.close()
