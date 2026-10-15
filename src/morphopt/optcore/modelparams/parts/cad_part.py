"""TorchFEA CAD-backed Part interface."""

from __future__ import annotations

import math
from typing import Any

import torchfea
from torchfea import cad as torchfea_cad

from ....constants import CONSTANT
from .base_part import BasePart


class CADPart(BasePart):
    """Build a Part from an ordered sequence of TorchFEA CAD operations.

    Subclasses override :meth:`define_operations` and add native TorchFEA CAD
    objects with :meth:`add_operation`::

        class Housing(morphopt.CADPart):
            def define_operations(self) -> None:
                body = torchfea.cad.Box(
                    id="body", x=0, y=0, z=0, dx=20, dy=12, dz=8
                )
                bore = torchfea.cad.Cylinder(
                    id="bore", x=10, y=6, z=0, dz=8, radius=2
                )
                self.add_operation(body)
                self.add_operation(bore)
                self.add_operation(
                    torchfea.cad.Cut(
                        id="housing", object_id="body", tool_id="bore"
                    )
                )

    Boolean and transform operations refer to earlier operations by their
    IDs. The order in which :meth:`add_operation` is called is the CAD
    history order. Every OCC face and its nodes are named automatically as
    ``face_N`` and ``face_N_nodes`` after meshing.
    """

    cache_part = True

    def __init__(
        self,
        mesh_size: float = CONSTANT.KERNEL.MESH.DEFAULT_CAD_MESH_SIZE,
        mesh_order: int = CONSTANT.KERNEL.MESH.DEFAULT_ELEMENT_ORDER,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if not math.isfinite(mesh_size) or mesh_size <= 0:
            raise ValueError("mesh_size must be finite and positive.")
        if mesh_order not in (1, 2):
            raise ValueError("mesh_order must be 1 or 2.")
        self.mesh_size = float(mesh_size)
        self.mesh_order = mesh_order
        self.operations: list[torchfea_cad.CADOperation] = []

    def define_operations(self) -> None:
        """Override to declare CAD operations in their execution order."""

    def add_operation(self, operation: torchfea_cad.CADOperation) -> CADPart:
        """Append one native TorchFEA CAD operation to the history."""
        if not isinstance(operation, torchfea_cad.CADOperation):
            raise TypeError("operation must be a TorchFEA CADOperation.")
        self.operations.append(operation)
        return self

    def initialize(self, *args: object, **kwargs: object) -> None:
        """Declare Instances and the CAD history once during initialization."""
        super().initialize(*args, **kwargs)
        self.operations.clear()
        self.define_operations()

    def _build_history(self) -> torchfea_cad.CADHistory:
        return torchfea_cad.CADHistory(
            operations=self.operations,
            mesh_size=self.mesh_size,
            exterior_surface=self.exterior_surface or "extern",
        )

    def build_part(self, path_result=None, pools=None) -> torchfea.Part:
        cad_model = torchfea_cad.CADModel(mesh_size=self.mesh_size)
        cad_model.add_part(self.part_name, self._build_history())
        part = cad_model.mesh_part(self.part_name)
        self._name_occ_faces(part)
        if self.mesh_order == 2:
            element_names = list(part.elems)
            part.convert_linear_to_quadratic_elements(element_names, element_names)
        return part

    @staticmethod
    def _name_occ_faces(part: torchfea.Part) -> None:
        """Name OCC boundary faces in the order returned by TorchFEA's OCC pass."""
        face_names = [
            name for name in part.surfaces if name.startswith("gmsh_surface_")
        ]
        face_names.sort(key=lambda name: int(name.rsplit("_", 1)[1]))

        reserved_surfaces = {f"face_{index}" for index in range(len(face_names))}
        reserved_nodes = {f"face_{index}_nodes" for index in range(len(face_names))}
        surface_conflicts = reserved_surfaces.intersection(part.surfaces.keys())
        node_conflicts = reserved_nodes.intersection(part.set_nodes)
        if surface_conflicts or node_conflicts:
            names = ", ".join(sorted(surface_conflicts | node_conflicts))
            raise ValueError(
                f"CAD set names {names} are reserved for OCC faces and nodes."
            )

        for index, old_name in enumerate(face_names):
            surface = part.surfaces[old_name]
            tag = old_name.rsplit("_", 1)[1]
            old_node_name = f"gmsh_nodes_{tag}"
            nodes = part.set_nodes[old_node_name]

            part.delete_surface_set(old_name)
            part.add_surface_set(f"face_{index}", surface)
            part.delete_node_set(old_node_name)
            part.add_node_set(f"face_{index}_nodes", nodes)

    def get_face_names(self) -> list[str]:
        """Return ``face_N`` names in the OCC preview's face order."""
        history = self._build_history()
        if not history.operations:
            return []
        records = history.preview()
        return [f"face_{index}" for index in range(len(records))]
