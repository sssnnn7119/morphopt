"""Structured primitive Parts used by numerical optimization models."""

from __future__ import annotations

import math

import numpy as np
import torch
import torchfea

from .basepartinterface import BasePartInterface


def _positive(**values: float) -> None:
    for name, value in values.items():
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive.")


class BoxPartInterface(BasePartInterface):
    """Structured hexahedral box with node and surface sets for each face."""

    cache_part = True

    def __init__(
        self,
        length: float = 40.0,
        height: float = 16.0,
        depth: float = 8.0,
        mesh_size: float = 2.0,
        mesh_order: int = 2,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        _positive(length=length, height=height, depth=depth, mesh_size=mesh_size)
        if mesh_order not in (1, 2):
            raise ValueError("mesh_order must be 1 or 2.")
        self.length, self.height, self.depth = length, height, depth
        self.mesh_size, self.mesh_order = mesh_size, mesh_order

    def build_part(self, path_result=None, pools=None) -> torchfea.Part:
        dimensions = [self.length, self.height, self.depth]
        axes = [
            np.linspace(0.0, size, max(2, math.ceil(size / self.mesh_size)) + 1)
            for size in dimensions
        ]
        nodes = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
        ids = np.arange(len(nodes)).reshape(*(len(axis) for axis in axes))
        offsets = [
            (0, 0, 0),
            (1, 0, 0),
            (1, 1, 0),
            (0, 1, 0),
            (0, 0, 1),
            (1, 0, 1),
            (1, 1, 1),
            (0, 1, 1),
        ]
        cells = np.stack(
            [
                ids[
                    a : len(axes[0]) - 1 + a,
                    b : len(axes[1]) - 1 + b,
                    c : len(axes[2]) - 1 + c,
                ].ravel()
                for a, b, c in offsets
            ],
            axis=1,
        )
        part = torchfea.Part(
            torch.as_tensor(
                nodes,
                dtype=torch.get_default_dtype(),
                device=torch.get_default_device(),
            )
        )
        part.add_element(
            torchfea.elements.C3D8(
                elems_index=torch.arange(len(cells), device=part.nodes.device),
                elems=torch.as_tensor(cells, device=part.nodes.device),
            ),
            name="design",
        )
        if self.mesh_order == 2:
            part.convert_linear_to_quadratic_elements(["design"], ["design"])

        node_coordinates = part.nodes.detach().cpu().numpy()
        bounds = np.array(
            [[0.0, self.length], [0.0, self.height], [0.0, self.depth]],
            dtype=float,
        )
        part.add_node_set("all", np.arange(len(node_coordinates), dtype=int))
        axis_names = ("x", "y", "z")
        for axis, axis_name in enumerate(axis_names):
            part.add_node_set(
                f"nodes_{axis_name}min",
                np.flatnonzero(np.isclose(node_coordinates[:, axis], bounds[axis, 0])),
            )
            part.add_node_set(
                f"nodes_{axis_name}max",
                np.flatnonzero(np.isclose(node_coordinates[:, axis], bounds[axis, 1])),
            )

        all_surface_groups: list[tuple[np.ndarray, int]] = []
        face_groups: dict[str, list[tuple[np.ndarray, int]]] = {
            f"surface_{axis_name}{side}": []
            for axis_name in axis_names
            for side in ("min", "max")
        }
        for element in part.elems.values():
            for element_indices, surface_index in element.extract_boundary_surface_set():
                element_indices = np.asarray(element_indices, dtype=np.int64).reshape(-1)
                if not len(element_indices):
                    continue
                element_index_tensor = torch.as_tensor(
                    element_indices, dtype=torch.long, device=element._elems.device
                )
                local_face = element.surfaceid_map[int(surface_index)]
                face_nodes = (
                    element._elems[element_index_tensor][:, local_face]
                    .detach()
                    .cpu()
                    .numpy()
                )
                face_coordinates = node_coordinates[face_nodes]
                spans = np.ptp(face_coordinates.reshape(-1, 3), axis=0)
                axis = int(np.argmin(spans))
                coordinate = float(face_coordinates[..., axis].mean())
                lower, upper = bounds[axis]
                side = "min" if abs(coordinate - lower) <= abs(coordinate - upper) else "max"
                group = (element_indices, int(surface_index))
                all_surface_groups.append(group)
                face_groups[f"surface_{axis_names[axis]}{side}"].append(group)

        exterior_name = self.exterior_surface or "extern"
        if exterior_name in face_groups:
            raise ValueError(
                f"exterior_surface {exterior_name!r} conflicts with a box face set."
            )
        part.exterior_surface = exterior_name
        part.add_surface_set(exterior_name, all_surface_groups)
        for name, groups in face_groups.items():
            if groups:
                part.add_surface_set(name, groups)
        return part
