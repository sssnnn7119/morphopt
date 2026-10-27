"""Mesh-set data belongs to kernel Parts and follows their mesh lifecycle."""

from pathlib import Path

import numpy as np
import pytest
import torch
import torchfea

from morphopt import BasePart, BoxPart, CADPart, FixedPart, INPPart


REFERENCE = Path(__file__).resolve().parents[2] / "docs/assets/ui_reference/reference-box.inp"


def test_box_build_caches_actual_sets_and_rebuilds_after_dimensions_change():
    part = BoxPart(part_name="body", length=2, height=2, depth=2, mesh_size=1, mesh_order=1)
    mesh = part.get_part()
    assert part.node_sets is mesh.set_nodes
    assert part.element_sets is mesh.set_elements
    assert part.surface_sets is mesh.surfaces
    assert part.surface_sets["surface_zmax"] is mesh.surfaces["surface_zmax"]
    assert part.get_part() is mesh
    part.length = 4
    new_mesh = part.get_part()
    assert new_mesh is not mesh
    assert part.node_sets is new_mesh.set_nodes
    assert new_mesh.nodes[part.node_sets["nodes_xmax"], 0].unique().tolist() == [4]
    part.clear_mesh_cache()
    assert part._part is None
    assert part.node_sets is part.get_part().set_nodes


def test_inp_caches_imported_element_sets_and_refreshes_a_replaced_file(tmp_path):
    path = tmp_path / "body.inp"
    path.write_bytes(REFERENCE.read_bytes())
    part = INPPart(str(path), part_name="body")
    mesh = part.get_part()
    assert part.node_sets is mesh.set_nodes
    assert "extern" in part.surface_sets
    np.testing.assert_array_equal(part.element_sets["design"], [0])
    assert part.get_part() is mesh
    path.write_text(path.read_text().replace("nodes_xmin", "clamped_end"))
    rebuilt = part.get_part()
    assert rebuilt is not mesh
    assert "clamped_end" in part.node_sets
    assert "nodes_xmin" not in part.node_sets
    assert part.element_sets is rebuilt.set_elements


def test_variable_custom_part_does_not_cache_meshes_or_indices():
    class VariablePart(BasePart):
        generation = 0

        def build_part(self, path_result=None, pools=None):
            self.generation += 1
            mesh = torchfea.Part(torch.zeros((self.generation, 3)))
            mesh.add_node_set(f"nodes_{self.generation}", np.arange(self.generation))
            return mesh

    part = VariablePart(part_name="changing")
    first = part.get_part()
    second = part.get_part()
    assert first is not second
    assert tuple(second.set_nodes) == ("nodes_2",)
    assert not isinstance(part, FixedPart)
    assert "_part" not in vars(part)
    for key in ("node_sets", "surface_sets", "element_sets"):
        assert not hasattr(part, key)


def test_boundary_set_names_come_from_geometry_without_meshing(monkeypatch):
    from morphopt import BoundaryPart, OffsetBoundaryPart

    def forbid_mesh(*args, **kwargs):
        pytest.fail("Describing a boundary selection must not build or cache FE indices")

    for part in (BoundaryPart(), OffsetBoundaryPart()):
        part.add_surface_interface(BoundaryPart.BSP.initialize_cylinder(r0=4, length=12, seed_size=1, flip=False))
        part.add_surface_interface(BoundaryPart.BSP.initialize_cylinder(r0=2, length=8, seed_size=1, flip=True))
        monkeypatch.setattr(part, "build_part", forbid_mesh)
        assert "surface_0_All" in part.surface_set_names
        assert "surface_1_All" in part.surface_set_names
        assert "surface_0_Bottom" in part.node_set_names
        assert not isinstance(part, FixedPart)
        assert "_part" not in vars(part)
        assert not hasattr(part, "node_sets")
        assert not hasattr(part, "surface_sets")
        if isinstance(part, OffsetBoundaryPart):
            assert "surface_1_offset" in part.surface_set_names


def test_cad_properties_reuse_the_mesh_and_follow_operation_changes():
    class Housing(CADPart):
        def define_operations(self):
            self.add_operation(torchfea.cad.Box(id="box", x=0, y=0, z=0, dx=2, dy=2, dz=2))

    part = Housing(part_name="housing", mesh_size=1, mesh_order=1)
    part.initialize()
    first = part.get_part()
    assert part.surface_sets is first.surfaces
    assert part.node_sets is first.set_nodes
    part.operations[0].dx = 3
    second = part.get_part()
    assert first is not second
    assert part.surface_sets is second.surfaces
    assert part.node_sets is second.set_nodes


def test_custom_fixed_part_reuses_one_mesh_and_exposes_its_live_sets():
    class ImportedPart(FixedPart):
        builds = 0

        def build_part(self, path_result=None, pools=None):
            self.builds += 1
            return torchfea.Part(torch.zeros((1, 3)))

    part = ImportedPart(part_name="custom")
    mesh = part.get_part()
    mesh.add_node_set("added_after_build", [0])
    assert part.node_sets is mesh.set_nodes
    assert "added_after_build" in part.node_set_names
    assert part.surface_sets is mesh.surfaces
    assert part.element_sets is mesh.set_elements
    assert part.builds == 1
    part.part_name = "renamed"
    assert part._part is None
    assert part.get_part() is not mesh
    assert part.builds == 2
    part.initialize()
    assert part._part is None
    part.get_part()
    assert part.builds == 3


def test_concrete_fixed_parts_share_the_fixed_base():
    from morphopt import GeometryParams

    assert GeometryParams.FixedPart is FixedPart
    for cls in (BoxPart, CADPart, INPPart):
        assert issubclass(cls, FixedPart)
