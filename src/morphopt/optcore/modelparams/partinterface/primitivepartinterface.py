"""Fixed primitive Parts: geometry construction belongs to the numerical model."""
from __future__ import annotations

import math
import numpy as np
import torch
import torchfea

from .basepartinterface import BasePartInterface


def _positive(**values):
    for name, value in values.items():
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive.")


class BoxPartInterface(BasePartInterface):
    """Structured brick box along X with fixed/tip node sets at its ends."""

    cache_part = True

    def __init__(self, length=40., height=16., depth=8., mesh_size=2., mesh_order=2, **kwargs):
        super().__init__(**kwargs)
        _positive(length=length, height=height, depth=depth, mesh_size=mesh_size)
        if mesh_order not in (1, 2):
            raise ValueError("mesh_order must be 1 or 2.")
        self.length, self.height, self.depth = length, height, depth
        self.mesh_size, self.mesh_order = mesh_size, mesh_order

    def build_part(self, path_result=None, pools=None):
        dimensions = [self.length, self.height, self.depth]
        axes = [np.linspace(0., size, max(2, math.ceil(size/self.mesh_size))+1) for size in dimensions]
        nodes = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
        ids = np.arange(len(nodes)).reshape(*(len(axis) for axis in axes))
        offsets = [(0,0,0), (1,0,0), (1,1,0), (0,1,0), (0,0,1), (1,0,1), (1,1,1), (0,1,1)]
        cells = np.stack([ids[a:len(axes[0])-1+a, b:len(axes[1])-1+b, c:len(axes[2])-1+c].ravel()
                          for a,b,c in offsets], axis=1)
        part = torchfea.Part(torch.as_tensor(nodes, dtype=torch.get_default_dtype(), device=torch.get_default_device()))
        part.add_element(torchfea.elements.C3D8(
            elems_index=torch.arange(len(cells), device=part.nodes.device),
            elems=torch.as_tensor(cells, device=part.nodes.device)), name="design")
        part.add_node_set("all", np.arange(len(nodes)))
        part.add_node_set("fixed", np.flatnonzero(np.isclose(nodes[:, 0], 0.)))
        part.add_node_set("tip", np.flatnonzero(np.isclose(nodes[:, 0], self.length)))
        part.add_surface_set("extern", part.elems["design"].extract_boundary_surface_set())
        if self.mesh_order == 2:
            part.convert_linear_to_quadratic_elements(["design"], ["design"])
        return part

    def get_initial_mesh(self):
        import pyvista as pv
        return pv.Box(bounds=[0., self.length, 0., self.height, 0., self.depth])


class CylinderPartInterface(BasePartInterface):
    """Fixed cylinder starting at init_location and extending along direction."""

    cache_part = True

    def __init__(self, r0=10., length=20., init_location=(0., 0., 0.),
                 direction=(0., 0., 1.), mesh_size=2., mesh_order=1, **kwargs):
        super().__init__(**kwargs)
        _positive(r0=r0, length=length, mesh_size=mesh_size)
        if mesh_order not in (1, 2):
            raise ValueError("mesh_order must be 1 or 2.")
        location = np.asarray(init_location, dtype=float)
        axis = np.asarray(direction, dtype=float)
        if location.shape != (3,) or axis.shape != (3,) or not np.isfinite(location).all() or not np.isfinite(axis).all() or np.linalg.norm(axis) == 0:
            raise ValueError("init_location and direction must be finite 3-vectors; direction must be nonzero.")
        self.r0, self.length = r0, length
        self.init_location = location.tolist()
        self.direction = (axis/np.linalg.norm(axis)).tolist()
        self.mesh_size, self.mesh_order = mesh_size, mesh_order

    def build_part(self, path_result=None, pools=None):
        cad = torchfea.cad.CADModel()
        history = cad.add_part(self.part_name)
        delta = np.asarray(self.direction)*self.length
        history.add_cylinder(x=self.init_location[0], y=self.init_location[1], z=self.init_location[2],
                             dx=float(delta[0]), dy=float(delta[1]), dz=float(delta[2]), radius=self.r0)
        part = cad.mesh_part(self.part_name, mesh_size=self.mesh_size)
        if self.mesh_order == 2:
            names = list(part.elems)
            part.convert_linear_to_quadratic_elements(names, names)
        return part

    def get_initial_mesh(self):
        import pyvista as pv
        center = np.asarray(self.init_location)+np.asarray(self.direction)*self.length/2
        return pv.Cylinder(center=center, direction=self.direction, radius=self.r0, height=self.length)
