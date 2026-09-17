"""Assembly-instance definitions owned by geometry Part definitions."""

from __future__ import annotations

from collections.abc import Sequence

import torchfea


class InstanceDefinition:
    """Describe one rigid placement of a registered geometry Part."""

    def __init__(
        self,
        name: str,
        part_name: str,
        *,
        translation: Sequence[float] | None = None,
        rotation: Sequence[float] | None = None,
    ) -> None:
        self._name = str(name)
        """Stable Assembly name of this instance."""
        self._part_name = str(part_name)
        """Name of the Part definition placed by this instance."""
        self._translation = tuple(float(value) for value in (translation or (0.0, 0.0, 0.0)))
        """Rigid translation applied to the Part in global coordinates."""
        self._rotation = tuple(float(value) for value in (rotation or (0.0, 0.0, 0.0)))
        """Rigid rotation applied to the Part in global coordinates."""
        self._torchfea_Instance: torchfea.Instance | None = None
        """TorchFEA Instance created while building the current Assembly."""

    @property
    def name(self) -> str:
        """Return the stable Assembly instance name."""
        return self._name

    @property
    def part_name(self) -> str:
        """Return the referenced Part name."""
        return self._part_name

    @property
    def translation(self) -> tuple[float, ...]:
        """Return the configured rigid translation."""
        return self._translation

    @property
    def rotation(self) -> tuple[float, ...]:
        """Return the configured rigid rotation."""
        return self._rotation

    def build_instance(self) -> None:
        """Create and cache the TorchFEA instance for the current Assembly."""
        self._torchfea_Instance = torchfea.Instance(
            part_name=self._part_name,
            translation=list(self._translation),
            rotation=list(self._rotation),
        )

    def get_instance(self) -> torchfea.Instance:
        """Return the backend instance created by :meth:`build_instance`."""
        if self._torchfea_Instance is None:
            raise RuntimeError(f"Instance {self._name!r} has not been built.")
        return self._torchfea_Instance
