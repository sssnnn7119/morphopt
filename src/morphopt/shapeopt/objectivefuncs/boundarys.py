import torch

from ...constants import CONSTANT
from .basefuncs import BaseConstraints


class MinRadius(BaseConstraints):
    """
    Cylinder boundary objective function for MorphOpt.
    """

    def __init__(self, radius: float) -> None:
        """Initialize the Cylinder objective function.

        Args:
            radius (float): Geometric radius in model length units.
        """
        super().__init__()

        self._radius = radius
        """
        The radius of the cylinder.
        """

    def __call__(self, r, rdu, rdu2, *args, **kwargs):

        """Evaluate MinRadius for the supplied inputs.

        Args:
            r: Current Cartesian surface samples; each surface block has shape (num_points, 3).
            rdu: Current first surface derivatives; each block has shape (num_points, 3, 2).
            rdu2: Current second surface derivatives; each block has shape (num_points, 3, 2, 2).
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.

        Returns:
            torch.Tensor: One-element tensor containing the integrated minimum-radius penalty.
        """
        thre = CONSTANT.KERNEL.SHAPE_CONSTRAINTS.BARRIER_THRESHOLD
        degree = CONSTANT.KERNEL.SHAPE_CONSTRAINTS.MIN_RADIUS_EXPONENT

        loss = torch.zeros(1, device=r[0].device, dtype=r[0].dtype)
        for i in range(len(r)):
            if not self.surfaces[i].is_updatable:
                continue

            length_r = -(r[i][:, 0] ** 2 + r[i][:, 1] ** 2).sqrt() + self._radius

            index_r, loss_r = self.barrier_function(
                length_r, thre, CONSTANT.KERNEL.SHAPE_CONSTRAINTS.BARRIER_RATIO, degree,
            )

            if len(index_r) > 0:
                loss = loss + (self.integration_weights[i][index_r] * loss_r).sum()

        return loss


class Cylinder(BaseConstraints):
    """
    Cylinder boundary objective function for MorphOpt.
    """

    def __init__(self, radius: float, height: float, bottom: float) -> None:
        """Initialize the Cylinder objective function.

        Args:
            radius (float): Geometric radius in model length units.
            height (float): Geometric height in model length units.
            bottom (float): Lower axial coordinate in model length units.
        """
        super().__init__()

        self._radius = radius
        """
        The radius of the cylinder.
        """

        self._height = height
        """
        The height of the cylinder.
        """

        self._bottom = bottom
        """
        The bottom of the cylinder.
        """

    def __call__(self, r, rdu, rdu2, *args, **kwargs):

        """Evaluate Cylinder for the supplied inputs.

        Args:
            r: Current Cartesian surface samples; each surface block has shape (num_points, 3).
            rdu: Current first surface derivatives; each block has shape (num_points, 3, 2).
            rdu2: Current second surface derivatives; each block has shape (num_points, 3, 2, 2).
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.

        Returns:
            torch.Tensor: One-element tensor containing the integrated radial and axial containment
                penalties.
        """
        thre = CONSTANT.KERNEL.SHAPE_CONSTRAINTS.BARRIER_THRESHOLD
        degree = CONSTANT.KERNEL.SHAPE_CONSTRAINTS.CYLINDER_EXPONENT

        loss = torch.zeros(1, device=r[0].device, dtype=r[0].dtype)
        for i in range(len(r)):
            if not self.surfaces[i].is_updatable:
                continue

            length_r = (r[i][:, 0] ** 2 + r[i][:, 1] ** 2).sqrt() - self._radius
            length_bottom = -r[i][:, 2] + self._bottom
            length_top = r[i][:, 2] - self._height

            barrier_ratio = CONSTANT.KERNEL.SHAPE_CONSTRAINTS.BARRIER_RATIO
            index_r, loss_r = self.barrier_function(
                length_r, thre, barrier_ratio, degree,
            )
            index_bottom, loss_bottom = self.barrier_function(
                length_bottom, thre, barrier_ratio, degree,
            )
            index_top, loss_top = self.barrier_function(
                length_top, thre, barrier_ratio, degree,
            )

            if len(index_r) > 0:
                loss = loss + (self.integration_weights[i][index_r] * loss_r).sum()
            if len(index_bottom) > 0:
                loss = (
                    loss
                    + (self.integration_weights[i][index_bottom] * loss_bottom).sum()
                )
            if len(index_top) > 0:
                loss = loss + (self.integration_weights[i][index_top] * loss_top).sum()

        return loss
