"""BREP boundaries stored as STEP assets with optional source face-name maps."""

from __future__ import annotations

import json
from functools import partial
from pathlib import Path
from shutil import copyfile
from typing import TYPE_CHECKING

import gmsh
import numpy as np
import pyvista as pv
from torchfea import cad

from ...optcore.modelparams.parts import CADPart
from .base_surface import BaseSurface

if TYPE_CHECKING:
    from multiprocessing.pool import Pool

    from torchfea.cad.builder import OCCBuilder


class BREPSurface(BaseSurface):
    """A closed BREP boundary stored as a STEP asset with source face names."""

    def __init__(self, path_step: str | Path) -> None:
        super().__init__()
        self.path_step = Path(path_step).resolve()
        mapping = self.path_step.with_suffix(".faces.json")
        self._face_map: dict[str, list[float]] = (
            json.loads(mapping.read_text(encoding="utf-8")) if mapping.exists() else {}
        )

    @property
    def face_names(self) -> tuple[str, ...]:
        """Original face names stored with a converted STEP boundary."""
        return tuple(self._face_map)

    def _match_faces(self, tags: list[int]) -> dict[int, str]:
        """Resolve original names after STEP import, independently of face order."""
        if not self._face_map:
            return {}
        if len(tags) != len(self._face_map):
            raise ValueError(
                f"STEP face count differs from its face map: {self.path_step}"
            )
        signatures = np.asarray([CADPart.get_face_signature(tag) for tag in tags])
        names: dict[int, str] = {}
        for name, signature in self._face_map.items():
            matches = np.flatnonzero(
                np.all(
                    np.isclose(
                        signatures,
                        signature,
                        rtol=1e-7,
                        atol=1e-8,
                    ),
                    axis=1,
                )
            )
            if len(matches) != 1 or tags[int(matches[0])] in names:
                raise ValueError(f"Cannot uniquely identify {name} in {self.path_step}")
            names[tags[int(matches[0])]] = name
        return names

    def load_geometry(self, part: CADPart, context: OCCBuilder) -> list[int]:
        """Import this STEP boundary and restore its named geometric faces."""
        tags = part.load_step_boundary(self.path_step, context)
        names = self._match_faces(tags)
        conflicts = set(names.values()) & set(part._face_names.values())
        if conflicts:
            raise ValueError(
                f"Duplicate STEP face names: {', '.join(sorted(conflicts))}"
            )
        part._face_names.update(names)
        return tags

    def prepare_geometry(
        self,
        path_output: str | Path,
        name_output: str,
        flip: bool = False,
        pools: Pool | None = None,
    ) -> None:
        """Use the existing STEP asset directly during boundary assembly."""

    def output_data(
        self,
        path_output: str | Path,
        name_output: str,
        seed_size: float = -1,
        flip: bool = False,
        pools: Pool | None = None,
    ) -> str:
        """Copy the exact STEP boundary and its face map to an output directory."""
        destination = Path(path_output) / f"{name_output}.stp"
        if destination.resolve() != self.path_step:
            copyfile(self.path_step, destination)
        mapping = destination.with_suffix(".faces.json")
        if self._face_map:
            mapping.write_text(json.dumps(self._face_map, indent=2), encoding="utf-8")
        elif mapping.exists():
            mapping.unlink()
        return destination.name

    def _preview_geometry(
        self,
        context: OCCBuilder,
        *,
        names: dict[int, str],
    ) -> list[tuple[int, int]]:
        """Load a single closed boundary inside TorchFEA's preview session."""
        entities = context.occ.importShapes(str(self.path_step))
        context.occ.synchronize()
        volumes = [(dim, tag) for dim, tag in entities if dim == 3]
        if len(volumes) != 1:
            raise ValueError(
                "BREPSurface requires one closed shell stored as a STEP solid."
            )
        tags = sorted(
            tag
            for _, tag in gmsh.model.getBoundary(
                volumes,
                oriented=False,
                recursive=False,
            )
        )
        names.update(
            self._match_faces(tags)
            or {tag: f"face_{index}" for index, tag in enumerate(tags)}
        )
        return volumes

    def get_mesh(self) -> pv.PolyData:
        """Tessellate the STEP asset for display and retain geometric face IDs."""
        names: dict[int, str] = {}
        action = partial(self._preview_geometry, names=names)
        records = cad.preview_brep([CADPart._Operation("brep_preview", action)])
        triangles = np.concatenate([record["triangles"] for record in records])
        nodes, local = np.unique(triangles, return_inverse=True)
        cells = np.column_stack((np.full(len(triangles), 3), local.reshape(-1, 3)))
        mesh = pv.PolyData(np.asarray(records[0]["points"])[nodes], cells)
        mesh.cell_data["face_index"] = np.concatenate(
            [
                np.full(
                    len(record["triangles"]),
                    int(names[record["surface_tag"]][5:]),
                    dtype=np.int64,
                )
                for record in records
            ]
        )
        return mesh
