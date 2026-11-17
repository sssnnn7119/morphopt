import torch

from ...constants import CONSTANT
from .basefuncs import BaseObjective


class DensityFieldMinimize(BaseObjective):
    """
    Small regularization objective that minimizes the SIMP density field.

    This objective encourages the density field to approach zero everywhere
    outside the solid material domain. It is scaled by a very small factor so
    that it only acts as a gentle regularization term.
    """

    def __init__(
        self,
        scale: float = CONSTANT.KERNEL.SIMP_CONSTRAINTS.DENSITY_FIELD_MINIMIZE_SCALE,
    ) -> None:
        """Initialize DensityFieldMinimize and its configuration state.

        Args:
            scale (float): Reference scale used to express the requested quantity or geometry.
        """
        super().__init__()
        self.scale = float(scale)

    def initialize(self, gradient: torch.Tensor, cps0: torch.Tensor, *args, **kwargs) -> None:
        # This objective does not require gradient initialization from the FE model.
        """Initialize the DensityFieldMinimize state.

        Args:
            gradient (torch.Tensor): Unscaled physical objective gradient in the target's
                design-variable order.
            cps0 (torch.Tensor): Reference SIMP control variables at the start of the subproblem.
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.
        """
        self.sensitivity = torch.zeros_like(cps0)

    def __call__(self, cps: torch.Tensor, *args, **kwargs) -> torch.Tensor:
        """Evaluate DensityFieldMinimize for the supplied inputs.

        Args:
            cps (torch.Tensor): Current SIMP design control variables.
            *args: Additional positional arguments accepted by the shared interface.
            **kwargs: Additional keyword arguments accepted by the shared interface.

        Returns:
            torch.Tensor: Scalar regularization value scale * (sum(cps) + 1)**2.
        """
        cps_now = cps.reshape_as(self.sensitivity if self.sensitivity is not None else cps)
        return self.scale * (cps_now.sum() + 1)**2
