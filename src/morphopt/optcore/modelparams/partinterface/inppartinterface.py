"""Part interface importing a fixed mesh from an Abaqus ``.inp`` file."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import torchfea

from .basepartinterface import BasePartInterface

if TYPE_CHECKING:
    from multiprocessing.pool import Pool

__all__ = ["INPPartInterface"]


class INPPartInterface(BasePartInterface):
    """One fixed Part read from an Abaqus ``.inp`` mesh.

    Parameters
    ----------
    mesh_file:
        Path of the ``.inp`` file holding the mesh.
    part_name:
        Name the Part gets inside the assembly; ``None`` uses the interface
        registration name.
    inp_part_name:
        Name of the Part inside the ``.inp`` file.  ``None`` selects the only
        Part in the file.
    """

    cache_part = True

    def __init__(
        self,
        mesh_file: str,
        part_name: str | None = None,
        inp_part_name: str | None = None,
        exterior_surface: str | None = None,
    ) -> None:
        super().__init__(
            part_name=part_name,
            exterior_surface=exterior_surface,
        )
        self.mesh_file: str = os.fspath(mesh_file)
        """Path of the Abaqus ``.inp`` file holding the mesh."""
        self.inp_part_name: str | None = (
            str(inp_part_name).strip() if inp_part_name else None)
        """Part name inside the ``.inp`` file (``None`` = the only Part)."""
        if not os.path.isfile(self.mesh_file):
            raise FileNotFoundError(
                f"Abaqus mesh file does not exist: {self.mesh_file}")

    def build_part(self, path_result: str | None = None,
                   pools: Pool | None = None) -> torchfea.Part:
        """Read the ``.inp`` file and return the selected Part."""
        inp = torchfea.FEA_INP()
        inp.read_inp(self.mesh_file)
        imported = torchfea.from_inp(inp).assembly

        part_name = self.inp_part_name
        if part_name is None:
            names = list(imported._parts)
            if len(names) != 1:
                raise ValueError(
                    f"{self.mesh_file!r} contains several Parts ({names}); "
                    "pass inp_part_name to select one.")
            part_name = names[0]
        part = imported.get_part(part_name)
        part.exterior_surface = self.exterior_surface or part.exterior_surface
        return part
