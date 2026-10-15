from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import torch

from ..surfaces import CPGEOSurface
from .basefuncs import BaseConstraints

if TYPE_CHECKING:
    from ..surfaces import BaseSurface


class VolumeMaximization(BaseConstraints):
    def __init__(
        self, surf_idx: int, weight: float = 1.0
    ):
        super().__init__()
        self._weight = weight
        self._surf_idx = surf_idx
        self.surfaces: list[BaseSurface] = []

    def initialize(
        self,
        *args: object,
        surfaces: Sequence[BaseSurface] | None = None,
        **kwargs: object,
    ) -> None:
        """Bind the current Part's surfaces before evaluating volume."""
        super().initialize(*args, **kwargs)
        if surfaces is None:
            raise ValueError("VolumeMaximization requires the updater's surfaces.")
        self.surfaces = list(surfaces)

    def __call__(
        self,
        r,
        rdu,
        rdu2,
        *args,
        **kwargs,
    ):
        if not self.surfaces:
            raise ValueError("VolumeMaximization requires the updater's surfaces.")
        cpgeo_interface = self.surfaces[self._surf_idx]
        if not isinstance(cpgeo_interface, CPGEOSurface):
            raise ValueError(
                "VolumeMaximization requires a CPGEOSurface at surf_idx."
            )
        cpr = r[self._surf_idx]
        faces = cpgeo_interface._preload_data.faces

        volume = (
            torch.cross(cpr[faces[:, 0]], cpr[faces[:, 1]]) * cpr[faces[:, 2]] / 6.0
        ).sum()

        return -volume * self._weight
