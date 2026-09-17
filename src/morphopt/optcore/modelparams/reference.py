"""Assembly-level reference point definition."""

from __future__ import annotations

from pathlib import Path

from morphopt._torch import torch
import torchfea


class ReferencePoint:
    """Assembly-level point with six generalized degrees of freedom."""
    def __init__(self, name: str, coordinates: torch.Tensor) -> None:
        self._name = str(name)
        """Stable reference-point name in GeometryParams."""
        self._coordinates = torch.as_tensor(coordinates).detach().clone()
        """Initial coordinates or generalized DOF location."""
        self._torchfea_ReferencePoint: torchfea.ReferencePoint | None = None
        """Backend reference-point object."""

    @property
    def name(self) -> str:
        """Return the reference-point name."""
        return self._name

    @property
    def coordinates(self) -> torch.Tensor:
        """Return the immutable reference-point coordinates."""
        return self._coordinates

    def build_reference_point(self) -> None:
        """Create and cache the backend reference-point object."""
        # TODO: Create torchfea.ReferencePoint and cache it.
        self._torchfea_ReferencePoint = torchfea.ReferencePoint(node=self._coordinates)

    def get_reference_point(self) -> torchfea.ReferencePoint:
        """Read the cached backend reference point."""
        if self._torchfea_ReferencePoint is None:
            raise RuntimeError(f"Reference point {self._name!r} has not been built")
        return self._torchfea_ReferencePoint

    def save(self, folder_path: str | Path, iteration: int) -> None:
        """Persist reference-point coordinates and backend identity."""
        # TODO: Persist coordinates and backend identity.
        return None

    def load(self, folder_path: str | Path, iteration: int) -> None:
        """Restore reference-point coordinates and backend identity."""
        # TODO: Restore coordinates and rebuild the backend reference point.
        return None
