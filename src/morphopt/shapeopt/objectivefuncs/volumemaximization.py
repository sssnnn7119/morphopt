from __future__ import annotations

import torch

from ...constants import CONSTANT
from ..surfaces import CPGEOSurface
from .basefuncs import BaseConstraints

class VolumeMaximization(BaseConstraints):
    def __init__(
        self,
        surf_idx: int,
        weight: float = CONSTANT.KERNEL.SHAPE_OBJECTIVES.DEFAULT_WEIGHT,
    ):
        super().__init__()
        self._weight = weight
        self._surf_idx = surf_idx

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
