"""Persistent, application-wide settings for three-dimensional viewports."""

import json
from dataclasses import asdict, dataclass

from PySide6.QtCore import QObject, QSettings, Signal


@dataclass(frozen=True)
class VisualizationSettings:
    """Store a projection, lighting, and surface-material preference snapshot."""
    parallel_projection: bool = True
    light_intensity: float = 1.0
    ambient: float = 0.17
    diffuse: float = 0.78
    specular: float = 0.24
    specular_power: float = 30.0
    smooth_shading: bool = True

    def __post_init__(self) -> None:
        for name, maximum in (
            ("light_intensity", 3),
            ("ambient", 1),
            ("diffuse", 1),
            ("specular", 1),
        ):
            if not 0 <= getattr(self, name) <= maximum:
                raise ValueError(f"{name} must be between 0 and {maximum}.")
        if not 1 <= self.specular_power <= 128:
            raise ValueError("specular_power must be between 1 and 128.")

    def material_options(self) -> dict[str, float | bool]:
        """Return material options.

        Returns:
            dict[str, float | bool]: Material options.
        """
        return {
            name: getattr(self, name)
            for name in (
                "ambient",
                "diffuse",
                "specular",
                "specular_power",
                "smooth_shading",
            )
        }


class VisualizationManager(QObject):
    """Persist global visualization preferences and notify viewports when they change."""
    changed = Signal()

    def __init__(self) -> None:
        """Initialize VisualizationManager and its configuration state."""
        super().__init__()
        self.settings = VisualizationSettings()

    def restore(self) -> None:
        """Restore the VisualizationManager state."""
        stored = QSettings("MorphOptUI", "ui").value("visualization", "", str)
        try:
            settings = (
                VisualizationSettings(**json.loads(stored))
                if stored
                else VisualizationSettings()
            )
        except (ValueError, TypeError):
            settings = VisualizationSettings()
        self.apply(settings, persist=False)

    def apply(self, settings: VisualizationSettings, *, persist: bool = True) -> None:
        """Apply the VisualizationManager state.

        Args:
            settings (VisualizationSettings): Visualization preference snapshot; None uses the
                current global settings.
            persist (bool): Write the accepted preference to application settings when True.
        """
        if persist:
            QSettings("MorphOptUI", "ui").setValue(
                "visualization", json.dumps(asdict(settings))
            )
        if settings != self.settings:
            self.settings = settings
            self.changed.emit()


visualization_manager = VisualizationManager()
