"""Export still previews and animated GIFs from the same history renderer."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Any

from .._runtime import cpu_torch_defaults
from ..archive import OptimizationArchive
from ..visualization import history_frames


def export_history_frame(
    folder: str, destination: str, iteration: int, mode: str, target: dict[str, str],
    camera: dict[str, Any], window_size: tuple[int, int], style: dict[str, Any],
) -> None:
    """Render one selected iteration as a still image using the animation renderer."""
    import imageio.v2 as imageio

    frames = history_frames(
        OptimizationArchive(folder), range(iteration, iteration + 1),
        mode=mode, target=target, camera=camera, window_size=window_size, style=style,
    )
    with cpu_torch_defaults(), closing(frames):
        frame = next(frames, None)
        if frame is None:
            raise ValueError(f"No frame is available for iteration {iteration}.")
        imageio.imwrite(destination, frame)


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
    """Write archived design or deformation frames using the supplied view.

    Args:
        folder (str): Directory containing the optimization run or archive.
        destination (str): Output file or directory selected by the caller.
        mode (str): "design" animates saved geometry or material views; "deformation" animates a
            named load-case result.
        target (dict[str, str]): Selected component/view identifiers for design mode, or the
            load-case identifier for deformation mode.
        first_iteration (int): First completed iteration included in the animation.
        last_iteration (int): Last completed iteration included in the animation.
        fps (int): Animation playback rate in frames per second.
        camera (dict[str, Any]): Camera state captured from the currently displayed viewport.
        window_size (tuple[int, int]): Output image dimensions (width, height) in pixels.
        style (dict[str, Any]): Explicit colors, lighting, opacity, and material settings for
            rendering.

    Returns:
        int: Number of frames written to the GIF.
    """
    import imageio.v2 as imageio

    archive = OptimizationArchive(folder)
    if not 1 <= first_iteration <= last_iteration <= archive.completed_iteration:
        raise ValueError("The selected iteration range is not available.")
    if fps < 1:
        raise ValueError("GIF frame rate must be at least 1 frame per second.")
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}.partial.gif")
    count = 0
    frames = history_frames(
        archive,
        range(first_iteration, last_iteration + 1),
        mode=mode,
        target=target,
        camera=camera,
        window_size=window_size,
        style=style,
    )
    try:
        with (
            cpu_torch_defaults(),
            closing(frames),
            imageio.get_writer(
                temporary, mode="I", duration=1000 / fps, loop=0
            ) as writer,
        ):
            for frame in frames:
                writer.append_data(frame)
                count += 1
        if count == 0:
            raise ValueError("No frames are available in the selected iteration range.")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return count
