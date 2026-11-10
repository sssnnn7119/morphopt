"""Build post-processing scenes and render history frames without file I/O."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .archive import OptimizationArchive

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


def design_view_options(component: Any | None) -> tuple[DesignView, ...]:
    """Return the views supported by one design component.

    Boundary parts expose the complete assembly and one focused view per
    surface.  B-spline and CPGEO surfaces additionally expose their control
    net.  Other components, including SIMP materials, deliberately keep one
    view because they have no alternate geometric representation.
    """
    surfaces = getattr(component, "surfaceinterfaces", None)
    if not surfaces:
        return (DesignView("default"),) if component is not None else ()
    views = [DesignView("all")]
    for index, surface in enumerate(surfaces):
        views.append(DesignView(f"surface:{index}", index))
        if surface.__class__.__name__ in {"BspSurface", "CPGEOSurface"}:
            views.append(DesignView(f"surface:{index}:control-net", index, True))
    return tuple(views)


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
    view: DesignView | None = None,
) -> None:
    """Draw one design component with explicit visual properties.

    ``view`` is intentionally optional so history exports and existing callers
    retain the complete-component rendering by default.
    """
    from pyvista import Actor

    if component is not None:
        existing = set(plotter.actors)
        surfaces = getattr(component, "surfaceinterfaces", None)
        if view is not None and view.surface_index is not None and surfaces:
            index = int(view.surface_index)
            if index < 0 or index >= len(surfaces):
                raise IndexError(f"Surface index out of range: {index}")
            surface = surfaces[index]
            mesh = surface.get_mesh()
            plotter.add_mesh(
                mesh,
                name=f"boundary:{id(component)}:surface-{index}",
                color=geometry_color,
                opacity=1.0,
                diffuse=diffuse,
                specular=specular,
                ambient=ambient,
                specular_power=specular_power,
                smooth_shading=True,
                show_edges=False,
            )
            if view.control_net:
                _add_control_net(plotter, surface, id(component), index)
        else:
            component.plot(plotter=plotter)
        surface_count = int(getattr(component, "num_surface_interfaces", 0) or 0)
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
                view is None or view.surface_index is None
            ) and surface_count > 1 and str(name).endswith("surface-0"):
                actor.prop.opacity = boundary_shell_opacity
    plotter.show_axes()


def _add_control_net(plotter: BasePlotter, surface: Any, component_id: int, index: int) -> None:
    """Overlay one compact control-point net without creating per-edge actors."""
    import numpy as np
    import pyvista as pv

    try:
        points = np.asarray(surface.control_points.detach().cpu(), dtype=float)
    except Exception:
        points = np.asarray(surface.control_points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not len(points):
        return

    faces = None
    model = getattr(surface, "model", None)
    if model is not None and hasattr(model, "_cp_faces"):
        faces = np.asarray(model._cp_faces, dtype=int)
    if faces is not None and faces.ndim == 2 and faces.shape[1] == 3:
        edges = np.concatenate(
            (faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]), axis=0
        )
        edges = np.unique(np.sort(edges, axis=1), axis=0)
    else:
        size = getattr(model, "size", None)
        if size is None or len(size) != 2 or int(np.prod(size)) != len(points):
            return
        rows, columns = (int(size[0]), int(size[1]))
        edges_list: list[tuple[int, int]] = []
        for row in range(rows):
            for column in range(columns - 1):
                edges_list.append((row * columns + column, row * columns + column + 1))
            # BSP cylinders are periodic in the circumferential direction.
            if columns > 2:
                edges_list.append((row * columns + columns - 1, row * columns))
        for row in range(rows - 1):
            for column in range(columns):
                edges_list.append((row * columns + column, (row + 1) * columns + column))
        edges = np.asarray(edges_list, dtype=int)

    if len(edges):
        lines = np.column_stack((np.full(len(edges), 2, dtype=np.int64), edges)).ravel()
        net = pv.PolyData(points, lines=lines)
        plotter.add_mesh(
            net,
            name=f"boundary:{component_id}:surface-{index}:control-net",
            color="#F2B84B",
            line_width=1.5,
            render_lines_as_tubes=True,
        )
    plotter.add_points(
        points,
        name=f"boundary:{component_id}:surface-{index}:control-points",
        color="#FFF1B8",
        point_size=4.5,
        render_points_as_spheres=True,
    )


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
