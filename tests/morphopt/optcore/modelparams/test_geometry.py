"""End-to-end tests for V4 geometry definitions and their export pipeline."""

from __future__ import annotations

from pathlib import Path

from morphopt._torch import torch
from morphopt.optcore.modelparams.geometry import GeometryParams
from morphopt.optcore.modelparams.parts.boundary import BoundaryPart
from morphopt.optcore.modelparams.parts.inp import InpPart
from morphopt.optcore.modelparams.parts.mesh import MeshPart
from morphopt.optcore.modelparams.parts.offset import OffsetShellPart
from morphopt.optcore.modelparams.parts.torchfea import TorchFEAPart
from morphopt.optcore.modelparams.reference import ReferencePoint
from morphopt.optcore.modelparams.surfaces.bsp import BSPCylinderSurface
from morphopt.optcore.modelparams.surfaces.cpgeo import (
    CPGEOCylinderSurface,
    CPGEOSphereSurface,
)
from morphopt.optcore.modelparams.surfaces.stl import STLSurface


class SpherePart(BoundaryPart):
    """Small closed CPGEO Part used by the geometry integration tests."""

    def define_surfaces(self) -> None:
        """Register a closed sphere as the external boundary surface."""
        self.add_surface(CPGEOSphereSurface(1.0, 0.8))


class SphereGeometry(GeometryParams):
    """Geometry definition containing one editable Part and one reference point."""

    def define_parts(self) -> None:
        """Register the test Part."""
        self.add_part(SpherePart("sphere", fea_seed_size=0.8))

    def define_reference_points(self) -> None:
        """Register one assembly-level reference point."""
        self.add_reference_point(ReferencePoint("tip", torch.as_tensor((0.0, 0.0, 1.0))))


class OrientationPart(BoundaryPart):
    """Boundary definition used to verify the ordered runtime flip convention."""

    def define_surfaces(self) -> None:
        """Register two closed fixed surfaces in a stable order."""
        vertices = torch.as_tensor(
            ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        ).numpy()
        faces = torch.as_tensor(((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3))).numpy()
        self.add_surface(STLSurface.from_mesh(vertices, faces))
        self.add_surface(STLSurface.from_mesh(vertices * 0.25 + 0.2, faces))


def test_concrete_surface_exports_and_orientation(tmp_path: Path) -> None:
    """Every supported concrete surface initializes and writes its native format."""
    bsp = BSPCylinderSurface(1.0, 1.0, 0.5)
    bsp.initialize()
    assert bsp.export_surface(tmp_path / "bsp", "stp").exists()

    cpgeo_cylinder = CPGEOCylinderSurface(1.0, 1.0, 0.5)
    cpgeo_cylinder.initialize()
    assert cpgeo_cylinder.get_preload_data().faces.shape[1] == 3
    assert cpgeo_cylinder.get_surface_parameters().shape[0] > 50
    assert cpgeo_cylinder.export_surface(tmp_path / "cpgeo_cylinder", "stl").exists()

    cpgeo_sphere = CPGEOSphereSurface(1.0, 0.8)
    cpgeo_sphere.initialize()
    assert not cpgeo_sphere.get_flip()
    assert cpgeo_sphere.export_surface(tmp_path / "cpgeo_sphere", "stl").exists()

    stl = STLSurface.from_mesh(
        vertices=torch.as_tensor(
            ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        ).numpy(),
        faces=torch.as_tensor(((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3))).numpy(),
    )
    stl.initialize()
    assert stl.export_surface(tmp_path / "fixed", "stl").exists()

    orientation = OrientationPart("orientation")
    orientation.initialize()
    assert tuple(surface.get_flip() for surface in orientation.surfaces) == (False, True)


def test_boundary_part_builds_torchfea_part_and_geometry_assembly(tmp_path: Path) -> None:
    """Editable CPGEO geometry exports, meshes and enters a fresh Assembly."""
    geometry = SphereGeometry()
    geometry.initialize()
    geometry.build_assembly(tmp_path / "cache")

    assembly = geometry.get_assembly()
    part = assembly.get_part("sphere")
    assert part.nodes.shape[0] > 0
    assert tuple(part.elems) == ("solid",)
    assert "surface_0_all" in part.surfaces
    assert part.exterior_surface == "extern"
    assert assembly.get_instance("sphere").part_name == "sphere"
    assert "tip" in assembly._reference_points
    assert (tmp_path / "cache" / "sphere" / "__surface-0.stl").exists()

    geometry.build_meshes()
    assert len(geometry.get_meshes()) == 1


def test_inp_part_reuses_generated_topology_and_offset_part_reuses_parameters(tmp_path: Path) -> None:
    """Imported and offset types preserve their documented ownership boundaries."""
    source = SpherePart("source", fea_seed_size=0.8)
    source.initialize()
    source.build_part(tmp_path / "source")
    source_path = tmp_path / "source" / "source.inp"

    imported = InpPart("imported", source_path, "source")
    imported.initialize()
    imported.build_part(tmp_path / "imported")
    assert imported.get_part().nodes.shape == source.get_part().nodes.shape

    offset = OffsetShellPart("offset", source, [False], 0.1, fea_seed_size=0.8)
    offset.initialize()
    assert torch.equal(offset.get_parameters(), source.get_parameters())
    offset.build_part(tmp_path / "offset")
    assert offset.get_part().nodes.shape[0] > 0


def test_mesh_part_tetrahedralizes_a_closed_stl_surface(tmp_path: Path) -> None:
    """The generic fixed-mesh Part uses the same Gmsh-to-TorchFEA import path."""
    surface = STLSurface.from_mesh(
        vertices=torch.as_tensor(
            ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        ).numpy(),
        faces=torch.as_tensor(((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3))).numpy(),
    )
    surface.initialize()
    mesh_path = surface.export_surface(tmp_path / "source", "stl")

    part = MeshPart("mesh", mesh_path, fea_seed_size=0.5)
    part.initialize()
    part.build_part(tmp_path / "mesh")
    assert tuple(part.get_part().elems) == ("solid",)


def test_torchfea_part_reuses_selected_saved_model_part(tmp_path: Path) -> None:
    """Saved-model imports retain the selected Part and source instance placement."""
    import torchfea

    source_part = torchfea.Part(
        torch.as_tensor(
            ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        )
    )
    source_part.add_element(
        torchfea.elements.initialize_element(
            "C3D4", torch.as_tensor([0]), torch.as_tensor(((0, 1, 2, 3),))
        ),
        "C3D4",
    )
    controller = torchfea.FEAController()
    controller.assembly = torchfea.Assembly()
    controller.assembly.add_part(source_part, "source")
    controller.assembly.add_instance(torchfea.Instance("source"), "source_instance")
    controller.save_model(str(tmp_path / "source.npz"), if_save_source_code=False)

    imported = TorchFEAPart("imported", tmp_path, "source.npz", "source")
    imported.initialize()
    imported.build_part()
    assert imported.get_part().nodes.shape == source_part.nodes.shape
    assert tuple(imported.instances) == ("source_instance",)
