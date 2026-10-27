"""Export saved optimization histories as animated GIF files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .archive import OptimizationArchive
from .context import cpu_torch_defaults
from .rendering import (
    add_deformation_mesh,
    add_design_component,
    configure_plotter,
    set_camera,
)


def export_history_gif(
    folder: str,
    destination: str,
    mode: str,
    target: dict[str, str],
    first_iteration: int,
    last_iteration: int,
    fps: int,
    camera: dict[str, Any],
    window_size: tuple[int, int],
    style: dict[str, Any],
) -> int:
    """Render archived design or deformation frames into a GIF file."""
    with cpu_torch_defaults():
        archive = OptimizationArchive(folder)
        completed = archive.completed_iteration
        if not 1 <= first_iteration <= last_iteration <= completed:
            raise ValueError("The selected iteration range is not available.")
        if fps < 1:
            raise ValueError("GIF frame rate must be at least 1 frame per second.")
        if mode not in {"design", "deformation"}:
            raise ValueError(f"Unsupported history GIF mode: {mode}")

        if mode == "design":
            if archive.initialize_params() is None:
                raise ValueError("The archived optimization model is unavailable.")
        elif not target.get("case"):
            raise ValueError("Select a load case before exporting deformation history.")

        import imageio.v2 as imageio
        import pyvista as pv

        output = Path(destination)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.stem}.partial.gif")
        size = tuple(max(1, int(value)) for value in window_size)
        frame_count = 0
        plotter = pv.Plotter(off_screen=True, window_size=size)
        try:
            with imageio.get_writer(
                temporary, mode="I", duration=1000 / fps, loop=0
            ) as writer:
                for iteration in range(first_iteration, last_iteration + 1):
                    plotter.clear()
                    configure_plotter(plotter, background=style["background"])
                    if mode == "design":
                        archive.load_parameters(iteration)
                        component = _find_component(
                            archive, target.get("category", ""), target.get("name", "")
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
                        add_deformation_mesh(
                            plotter, mesh, style["deformation_color"]
                        )

                    set_camera(plotter, camera)
                    plotter.add_text(
                        f"Iteration {iteration}",
                        position="upper_left",
                        font_size=12,
                        color=style["text_color"],
                    )
                    plotter.render()
                    writer.append_data(plotter.screenshot(return_img=True))
                    frame_count += 1
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        finally:
            plotter.close()

        if frame_count == 0:
            temporary.unlink(missing_ok=True)
            raise ValueError("No frames are available in the selected iteration range.")
        temporary.replace(output)
        return frame_count


def _find_component(
    archive: OptimizationArchive, category: str, name: str
) -> Any | None:
    return next(
        (
            component
            for item_category, component in archive.visualizable_components()
            if item_category == category and component.name == name
        ),
        None,
    )
