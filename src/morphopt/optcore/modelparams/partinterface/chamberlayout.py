"""Layered series/parallel chamber geometry, using existing surface primitives."""
from dataclasses import dataclass, field
import math


@dataclass
class ChamberLayer:
    length: float = 80.
    chambers: int = 2
    arrangement: str = "ring"
    radius: float = 2.
    center_radius: float = 5.
    shape: str = "cylinder"
    phase_degrees: float = 180.
    pressure_channels: list[int] = field(default_factory=lambda: [1, 2])


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
        return sorted({channel for layer in self.layers for channel in layer.pressure_channels})

    def validate(self):
        if not 1 <= len(self.layers) <= 8:
            raise ValueError("请定义 1–8 层气腔 / Define 1–8 chamber layers.")
        if not math.isfinite(self.body_radius) or not math.isfinite(self.wall) or min(self.body_radius, self.wall) <= 0:
            raise ValueError("外半径和壁厚必须为正 / Body radius and wall must be positive.")
        for index, layer in enumerate(self.layers, 1):
            if not all(math.isfinite(v) for v in (layer.length, layer.radius, layer.center_radius, layer.phase_degrees)) or layer.length <= 4*self.wall or layer.radius <= 0 or layer.center_radius < 0:
                raise ValueError(f"第 {index} 层：长度需大于四倍壁厚，半径需为正 / Layer {index}: length must exceed four wall thicknesses; radius must be positive.")
            if not isinstance(layer.chambers, int) or not 1 <= layer.chambers <= 8 or len(layer.pressure_channels) != layer.chambers or any(not isinstance(c, int) or c < 1 for c in layer.pressure_channels):
                raise ValueError(f"第 {index} 层：每个气腔需指定正整数压力通道 / Layer {index}: assign one positive integer pressure channel per cavity.")
            if layer.arrangement not in ("ring", "line") or layer.shape not in ("cylinder", "sphere"):
                raise ValueError(f"第 {index} 层：请选择截面排布和气腔形状 / Layer {index}: select an arrangement and shape.")
            if layer.shape == "sphere" and 2*layer.radius > layer.length-2*self.wall:
                raise ValueError(f"第 {index} 层：球形气腔超出层长 / Layer {index}: sphere exceeds the layer length.")
        cavities = self.cavity_specs()
        for cavity in cavities:
            if math.hypot(cavity.x, cavity.y)+cavity.radius+self.wall > self.body_radius+1e-9:
                raise ValueError(f"第 {cavity.layer+1} 层：气腔与外壁距离不足 / Layer {cavity.layer+1}: insufficient outer wall.")
        for i, cavity in enumerate(cavities):
            for other in cavities[i+1:]:
                if cavity.layer == other.layer and math.hypot(cavity.x-other.x, cavity.y-other.y) < cavity.radius+other.radius+self.wall-1e-9:
                    raise ValueError(f"第 {cavity.layer+1} 层：并联气腔之间壁厚不足 / Layer {cavity.layer+1}: insufficient wall between parallel cavities.")

    def cavity_specs(self):
        cavities, bottom = [], 0.
        for index, layer in enumerate(self.layers):
            phase = math.radians(layer.phase_degrees)
            for j in range(layer.chambers):
                if layer.arrangement == "ring":
                    angle = phase+2*math.pi*j/layer.chambers
                    x, y = layer.center_radius*math.cos(angle), layer.center_radius*math.sin(angle)
                else:
                    offset = layer.center_radius if layer.chambers == 1 else -layer.center_radius+2*layer.center_radius*j/(layer.chambers-1)
                    x, y = offset*math.cos(phase), offset*math.sin(phase)
                cavities.append(CavitySpec(index, x, y, bottom+self.wall, layer.length-2*self.wall,
                                          layer.radius, layer.shape, layer.pressure_channels[j]))
            bottom += layer.length
        return cavities

    def get_initial_meshes(self):
        """Primitive preview meshes, separate from finite-element mesh generation."""
        import pyvista as pv
        meshes = {"body": pv.Cylinder(center=[0., 0., self.length/2], direction=[0., 0., 1.], radius=self.body_radius, height=self.length, resolution=32)}
        for i, cavity in enumerate(self.cavity_specs()):
            center = [cavity.x, cavity.y, cavity.z+cavity.length/2]
            meshes[f"layer-{cavity.layer}:cavity-{i}"] = (
                pv.Sphere(center=center, radius=cavity.radius, theta_resolution=20, phi_resolution=16)
                if cavity.shape == "sphere" else pv.Cylinder(center=center, direction=[0., 0., 1.], radius=cavity.radius, height=cavity.length, resolution=24))
        return meshes
