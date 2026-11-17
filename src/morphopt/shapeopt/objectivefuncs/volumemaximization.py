from __future__ import annotations

import torch

from ...constants import CONSTANT
from ..surfaces import CPGEOSurface
from .basefuncs import BaseConstraints


class VolumeMaximization(BaseConstraints):
    """Contribute a signed volume objective to a boundary-shape subproblem.

    This auxiliary objective can be negative and is not a nonnegative geometric violation
    penalty.
    """
    def __init__(
        self,
        surf_idx: int,
        weight: float = CONSTANT.KERNEL.SHAPE_OBJECTIVES.DEFAULT_WEIGHT,
    ):
        """Initialize VolumeMaximization and its configuration state.

        Args:
            surf_idx (int): Zero-based boundary-surface index.
            weight (float): Scalar coefficient multiplying this objective or penalty term.
        """
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
        """Evaluate VolumeMaximization for the supplied inputs.

        Args:
            r: Current Cartesian surface samples; each surface block has shape (num_points, 3).
            rdu: Current first surface derivatives; each block has shape (num_points, 3, 2).
            rdu2: Current second surface derivatives; each block has shape (num_points, 3, 2, 2).
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.

        Returns:
            torch.Tensor: Signed, scaled volume objective of the selected CPGEO boundary.
        """
        if not self.surfaces:
            raise ValueError("VolumeMaximization requires the updater's surfaces.")
        cpgeo_interface = self.surfaces[self._surf_idx]
        if not isinstance(cpgeo_interface, CPGEOSurface):
            raise TypeError("VolumeMaximization requires a CPGEOSurface at surf_idx.")
        cpr = r[self._surf_idx]
        faces = cpgeo_interface._preload_data.faces

        volume = (
            torch.cross(cpr[faces[:, 0]], cpr[faces[:, 1]]) * cpr[faces[:, 2]] / 6.0
        ).sum()

        return -volume * self._weight
