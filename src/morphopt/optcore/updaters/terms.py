"""Reusable local penalty and constraint terms."""

from morphopt._torch import torch


class ConstraintTerm:
    """Base scalar constraint term used by updater closures."""

    def evaluate(self, parameters: torch.Tensor) -> torch.Tensor:
        """Evaluate this term at trial parameters."""
        # TODO: Implement concrete geometry/material constraint term.
        return torch.zeros((), dtype=parameters.dtype, device=parameters.device)
