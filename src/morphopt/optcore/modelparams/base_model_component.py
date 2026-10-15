"""Lifecycle base for individual geometry, FEA and material definitions."""

from ..protocal import (
    ProtocalInitializable,
    ProtocalSavable,
    ProtocalVisualizable,
)


class BaseModelComponent(
    ProtocalInitializable,
    ProtocalSavable,
    ProtocalVisualizable,
):
    """Shared lifecycle, persistence and visualization contract for one model object."""

