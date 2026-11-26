"""Shared PyVista rendering for preview and optimization result views."""

from __future__ import annotations

from collections.abc import Iterator
from itertools import product

import numpy as np
from pyvista import array_from_vtkmatrix
from pyvista.plotting.plotter import BasePlotter
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkCommonDataModel import vtkPointSet
from vtkmodules.vtkRenderingCore import vtkActor, vtkProp3D

from ...constants import CONSTANT
from ...postprocess.visualization import (
    apply_mesh_style,
)
from ...postprocess.visualization import (
    configure_plotter as configure_result_plotter,
)
from ..theme import theme_manager
from ..theme.visualization import VisualizationSettings, visualization_manager


def _camera_space_geometry(
    plotter: BasePlotter, view: np.ndarray
) -> Iterator[np.ndarray]:
    """Yield visible geometry in camera coordinates, including actor transforms."""
    for prop in plotter.renderer.GetViewProps():
        if (
            not isinstance(prop, vtkProp3D)
            or not prop.GetVisibility()
            or not prop.GetUseBounds()
        ):
            continue
        mapper = prop.GetMapper() if isinstance(prop, vtkActor) else None
        data = mapper.GetInput() if mapper is not None else None
        if isinstance(data, vtkPointSet) and data.GetNumberOfPoints():
            points = vtk_to_numpy(data.GetPoints().GetData())
            transform = view @ array_from_vtkmatrix(prop.GetMatrix())
        else:
            bounds = prop.GetBounds()
            if bounds is None or any(
                low > high for low, high in zip(bounds[::2], bounds[1::2])
            ):
                continue
            points = np.array(list(product(*np.reshape(bounds, (3, 2)))))
            transform = view  # Prop bounds are already in world coordinates.
        yield points @ transform[:3, :3].T + transform[:3, 3]


def fit_camera_to_geometry(plotter: BasePlotter) -> None:
    """Center and frame the model within the current viewport, preserving direction and roll."""
    camera = plotter.camera
    view = array_from_vtkmatrix(camera.GetViewTransformMatrix())
    aspect = plotter.renderer.GetTiledAspectRatio()
    if aspect <= 0:
        return
    frame = CONSTANT.UI.CAMERA.FIT_VIEW_FRACTION * np.array([aspect, 1.0])
    tangent = np.tan(np.radians(camera.view_angle) / 2)
    if camera.GetUseHorizontalViewAngle():
        tangent /= aspect
    # The parallel frame has straight sides. In perspective each side widens
    # with distance from the eye, so include vertex depth when fitting it.
    slope = 0.0 if camera.parallel_projection else frame * tangent
    lower, upper = np.full(2, np.inf), np.full(2, -np.inf)
    far_z, near_z = np.inf, -np.inf
    for points in _camera_space_geometry(plotter, view):
        xy, z = points[:, :2], points[:, 2:3]  # Positive Z points toward the eye.
        lower = np.minimum(lower, (xy - slope * z).min(axis=0))
        upper = np.maximum(upper, (xy + slope * z).max(axis=0))
        far_z, near_z = min(far_z, z.min()), max(near_z, z.max())
    if near_z < far_z:
        return

    center_xy = (lower + upper) / 2
    center_z = (far_z + near_z) / 2
    half_span = (upper - lower) / 2
    if camera.parallel_projection:
        scale = (half_span / frame).max()
        if scale > 0:
            camera.parallel_scale = scale
        eye_z = near_z + camera.parallel_scale / tangent
    else:
        eye_z = (half_span / slope).max()
        if (
            eye_z <= near_z
        ):  # A point or an axial edge has no apparent width at its tip.
            eye_z = near_z + (near_z - far_z or camera.distance)
    # Transform the two points back to world coordinates using the rigid view basis.
    to_world = view[:3, :3].T
    camera.focal_point = to_world @ (np.r_[center_xy, center_z] - view[:3, 3])
    camera.position = to_world @ (np.r_[center_xy, eye_z] - view[:3, 3])


def apply_plotter_theme(plotter: BasePlotter, background: str | None = None) -> None:
    """Apply the active viewer background, or an explicit render background.

    Args:
        plotter (BasePlotter): PyVista plotter receiving the scene; None creates a new plotter.
        background (str | None): Optional background color; None uses the active visualization
            palette.
    """
    plotter.set_background(background or theme_manager.palette.viewer.render.background)


def add_orientation_axes(plotter: BasePlotter) -> None:
    """Add labelled global XYZ directions in the lower-left corner.

    Args:
        plotter (BasePlotter): PyVista plotter receiving the scene; None creates a new plotter.
    """
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


def configure_plotter(
    plotter: BasePlotter,
    background: str | None = None,
    *,
    settings: VisualizationSettings | None = None,
) -> None:
    """Apply the UI palette through the shared post-processing renderer.

    Args:
        plotter (BasePlotter): PyVista plotter receiving the scene; None creates a new plotter.
        background (str | None): Optional background color; None uses the active visualization
            palette.
        settings (VisualizationSettings | None): Visualization preference snapshot; None uses
            the current global settings.
    """
    settings = settings or visualization_manager.settings
    configure_result_plotter(
        plotter,
        background or theme_manager.palette.viewer.render.background,
        light_intensity=settings.light_intensity,
    )
    if bool(plotter.camera.parallel_projection) != settings.parallel_projection:
        if settings.parallel_projection:
            plotter.enable_parallel_projection()
        else:
            plotter.disable_parallel_projection()


def apply_visualization(
    plotter: BasePlotter, settings: VisualizationSettings | None = None
) -> None:
    """Apply visualization.

    Args:
        plotter (BasePlotter): PyVista plotter receiving the scene; None creates a new plotter.
        settings (VisualizationSettings | None): Visualization preference snapshot; None uses
            the current global settings.
    """
    apply_mesh_style(
        plotter, **(settings or visualization_manager.settings).material_options()
    )
