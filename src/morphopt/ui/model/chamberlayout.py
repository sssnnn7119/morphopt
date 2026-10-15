"""Layered series/parallel chamber geometry for the Quickstart editor."""
from copy import deepcopy
from ..i18n import localized_message
from ...constants import CONSTANT
from dataclasses import dataclass, field
import math


@dataclass
class ChamberLayer:
    length: float = CONSTANT.UI.QUICKSTART.DEFAULT_LAYER.LENGTH
    chambers: int = CONSTANT.UI.QUICKSTART.DEFAULT_LAYER.CHAMBERS
    arrangement: str = CONSTANT.UI.QUICKSTART.DEFAULT_LAYER.ARRANGEMENT
    radius: float = CONSTANT.UI.QUICKSTART.DEFAULT_LAYER.RADIUS
    center_radius: float = CONSTANT.UI.QUICKSTART.DEFAULT_LAYER.CENTER_RADIUS
    shape: str = CONSTANT.UI.QUICKSTART.DEFAULT_LAYER.SHAPE
    phase_degrees: float = CONSTANT.UI.QUICKSTART.DEFAULT_LAYER.PHASE_DEGREES
    pressure_channels: list[int] = field(
        default_factory=lambda: list(CONSTANT.UI.QUICKSTART.DEFAULT_LAYER.PRESSURE_CHANNELS)
    )


@dataclass(frozen=True)
class CavitySpec:
    layer: int
    x: float
    y: float
    z: float
    length: float
    radius: float
    shape: str
    pressure_channel: int


class LayeredChambers:
    """Layers along Z are in series; each layer holds parallel cavities.

    Channel numbers define pneumatic connections independently of geometry:
    cavities assigned the same number share one pressure input.
    """

    def __init__(self, layers, body_radius, wall):
        self.layers = list(layers)
        self.body_radius, self.wall = body_radius, wall
        self.validate()

    @property
    def length(self):
        return sum(layer.length for layer in self.layers)

    @property
    def channels(self):
        return sorted(
            {channel for layer in self.layers for channel in layer.pressure_channels}
        )

    def validate(self):
        if not CONSTANT.UI.QUICKSTART.LIMITS.LAYER_MIN_COUNT <= len(self.layers) <= CONSTANT.UI.QUICKSTART.LIMITS.CHAMBER_MAX_COUNT:
            raise ValueError(localized_message("ui.errors.chamberlayout.define_1_8_chamber_layers"))
        if (
            not math.isfinite(self.body_radius)
            or not math.isfinite(self.wall)
            or min(self.body_radius, self.wall) <= 0
        ):
            raise ValueError(localized_message("ui.errors.chamberlayout.body_radius_and_wall_must_be_positive"))
        for index, layer in enumerate(self.layers, 1):
            if (
                not all(
                    math.isfinite(value)
                    for value in (
                        layer.length,
                        layer.radius,
                        layer.center_radius,
                        layer.phase_degrees,
                    )
                )
                or layer.length
                <= CONSTANT.UI.QUICKSTART.LIMITS.MINIMUM_LAYER_LENGTH_WALL_RATIO * self.wall
                or layer.radius <= 0
                or layer.center_radius < 0
            ):
                raise ValueError(
                    localized_message("ui.errors.chamberlayout.layer_value_length_must_exceed_four_wall_thicknesses_radius_must", value_0=index)
                )
            if (
                not isinstance(layer.chambers, int)
                or not 1 <= layer.chambers <= CONSTANT.UI.QUICKSTART.LIMITS.CHAMBER_MAX_COUNT
                or len(layer.pressure_channels) != layer.chambers
                or any(
                    not isinstance(channel, int) or channel < 1
                    for channel in layer.pressure_channels
                )
            ):
                raise ValueError(
                    localized_message("ui.errors.chamberlayout.layer_value_assign_one_positive_integer_pressure_channel_per_cavity", value_0=index)
                )
            if layer.arrangement not in ("ring", "line") or layer.shape not in (
                "cylinder",
                "sphere",
            ):
                raise ValueError(
                    localized_message("ui.errors.chamberlayout.layer_value_select_an_arrangement_and_shape", value_0=index)
                )
            if layer.shape == "sphere" and 2 * layer.radius > layer.length - 2 * self.wall:
                raise ValueError(
                    localized_message("ui.errors.chamberlayout.layer_value_sphere_exceeds_the_layer_length", value_0=index)
                )
        cavities = self.cavity_specs()
        for cavity in cavities:
            if (
                math.hypot(cavity.x, cavity.y) + cavity.radius + self.wall
                > self.body_radius + CONSTANT.UI.QUICKSTART.LIMITS.GEOMETRY_CLEARANCE_TOLERANCE
            ):
                raise ValueError(
                    localized_message("ui.errors.chamberlayout.layer_value_insufficient_outer_wall", value_0=cavity.layer + 1)
                )
        for index, cavity in enumerate(cavities):
            for other in cavities[index + 1 :]:
                if (
                    cavity.layer == other.layer
                    and math.hypot(cavity.x - other.x, cavity.y - other.y)
                    < cavity.radius
                    + other.radius
                    + self.wall
                    - CONSTANT.UI.QUICKSTART.LIMITS.GEOMETRY_CLEARANCE_TOLERANCE
                ):
                    raise ValueError(
                        localized_message("ui.errors.chamberlayout.layer_value_insufficient_wall_between_parallel_cavities", value_0=cavity.layer + 1)
                    )

    def cavity_specs(self):
        cavities, bottom = [], 0.
        for index, layer in enumerate(self.layers):
            phase = math.radians(layer.phase_degrees)
            for cavity_index in range(layer.chambers):
                if layer.arrangement == "ring":
                    angle = phase + 2 * math.pi * cavity_index / layer.chambers
                    x = layer.center_radius * math.cos(angle)
                    y = layer.center_radius * math.sin(angle)
                else:
                    if layer.chambers == 1:
                        offset = layer.center_radius
                    else:
                        offset = -layer.center_radius + (
                            2
                            * layer.center_radius
                            * cavity_index
                            / (layer.chambers - 1)
                        )
                    x, y = offset * math.cos(phase), offset * math.sin(phase)
                cavities.append(
                    CavitySpec(
                        index,
                        x,
                        y,
                        bottom + self.wall,
                        layer.length - 2 * self.wall,
                        layer.radius,
                        layer.shape,
                        layer.pressure_channels[cavity_index],
                    )
                )
            bottom += layer.length
        return cavities

    def get_initial_meshes(self):
        """Create primitive preview meshes, separate from FEA mesh generation."""
        import pyvista as pv

        meshes = {
            "body": pv.Cylinder(
                center=[0., 0., self.length / 2],
                direction=[0., 0., 1.],
                radius=self.body_radius,
                height=self.length,
                resolution=CONSTANT.UI.QUICKSTART.PREVIEW.BODY_RESOLUTION,
            )
        }
        for index, cavity in enumerate(self.cavity_specs()):
            center = [cavity.x, cavity.y, cavity.z + cavity.length / 2]
            meshes[f"layer-{cavity.layer}:cavity-{index}"] = (
                pv.Sphere(
                    center=center,
                    radius=cavity.radius,
                    theta_resolution=CONSTANT.UI.QUICKSTART.PREVIEW.SPHERE_THETA_RESOLUTION,
                    phi_resolution=CONSTANT.UI.QUICKSTART.PREVIEW.SPHERE_PHI_RESOLUTION,
                )
                if cavity.shape == "sphere"
                else pv.Cylinder(
                    center=center,
                    direction=[0., 0., 1.],
                    radius=cavity.radius,
                    height=cavity.length,
                    resolution=CONSTANT.UI.QUICKSTART.PREVIEW.CAVITY_CYLINDER_RESOLUTION,
                )
            )
        return meshes
