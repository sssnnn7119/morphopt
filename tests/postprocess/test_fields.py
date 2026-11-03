"""Physical-field extraction, contour projection, and table-export regressions."""

from __future__ import annotations

import csv
import json
import math

import numpy as np
import pytest
import torch
import torchfea

from morphopt.postprocess import (
    FiniteElementResults,
    cpu_torch_defaults,
    export_fields,
    export_saved_fields,
)


def test_exports_merge_selected_quantities_into_one_file(iteration_model, tmp_path):
    _, controller, result = iteration_model
    previous_dtype = torch.get_default_dtype()
    node_path = export_fields(controller, result, tmp_path / "my_nodes.csv")
    element_path = export_fields(
        controller, result, tmp_path / "my_elements.csv", location="elements"
    )
    export_fields(
        controller, result, tmp_path / "my_elements.npz", location="elements"
    )
    assert torch.get_default_dtype() is previous_dtype
    with node_path.open(encoding="utf-8-sig") as stream:
        nodes = list(csv.DictReader(stream))
    assert len(nodes) == 27
    assert set(nodes[0]) == {
        "instance",
        "node_id",
        "X",
        "Y",
        "Z",
        "U1",
        "U2",
        "U3",
        "U",
        "x",
        "y",
        "z",
    }
    for node in nodes:
        assert float(node["x"]) - float(node["X"]) == pytest.approx(
            float(node["U1"]), abs=1e-12
        )
    with element_path.open(encoding="utf-8-sig") as stream:
        points = list(csv.DictReader(stream))
    assert len(points) == 64
    assert (
        len(
            {
                (
                    row["instance"],
                    row["element_block"],
                    row["element_id"],
                    row["integration_point"],
                )
                for row in points
            }
        )
        == 64
    )
    assert sum(float(point["reference_volume"]) for point in points) == pytest.approx(
        1.0
    )
    assert sum(float(point["strain_energy"]) for point in points) > 0
    assert "S_Mises" in points[0] and "E11" in points[0]
    for point in points:
        assert float(point["strain_energy"]) == pytest.approx(
            float(point["strain_energy_density"]) * float(point["reference_volume"])
        )
    with np.load(tmp_path / "my_elements.npz", allow_pickle=False) as data:
        assert data["S_Mises"].shape == (64,)
        assert np.isfinite(data["S_Mises"]).all()
        assert data["strain_energy"].sum() == pytest.approx(
            sum(float(row["strain_energy"]) for row in points)
        )
        assert json.loads(str(data["__metadata__"]))["location"] == "elements"
    assert not (tmp_path / "manifest.json").exists()
    before = node_path.read_bytes()
    with pytest.raises(FileExistsError):
        export_fields(controller, result, node_path)
    assert node_path.read_bytes() == before
    export_fields(
        controller, result, node_path, fields=["displacement"], overwrite=True
    )
    with node_path.open(encoding="utf-8-sig") as stream:
        assert next(csv.reader(stream)) == [
            "instance",
            "node_id",
            "U1",
            "U2",
            "U3",
            "U",
        ]
    with pytest.raises(ValueError, match="one result location"):
        export_fields(
            controller, result, tmp_path / "mixed.csv", fields=["coordinates", "stress"]
        )
    assert not (tmp_path / "mixed.csv").exists()


def test_saved_result_export_restores_its_load_case(iteration_model, tmp_path):
    source, _, _ = iteration_model
    with cpu_torch_defaults():
        controller = torchfea.load_model(str(source.model_path))
        controller.assembly._loads["body_force"]._parameters *= 2
        result = controller.solve(if_initialize=False)
        result_path = tmp_path / "different_case.npz"
        result.save(str(result_path))
        instance = controller.assembly._instances["body-1"]
        expected = controller.GC2RGC(result.GC)[instance._RGC_index].detach().cpu().numpy()

    output = export_saved_fields(
        source.model_path, result_path, tmp_path / "fields.npz",
        location="nodes", fields=["displacement"],
    )
    with np.load(output) as data:
        np.testing.assert_allclose(data["U1"], expected[:, 0])


def test_result_fields_restore_torch_defaults_between_lazy_records(iteration_model):
    _, controller, result = iteration_model
    previous_dtype = torch.get_default_dtype()
    previous_device = torch.get_default_device()
    try:
        torch.set_default_dtype(torch.float32)
        values = FiniteElementResults(controller, result)
        table = values.table("elements", ["energy", "stress"])
        assert table.fields == ("energy", "stress")
        rows = iter(table.rows)
        for _ in range(2):
            assert next(rows)[0] == "body-1"
            assert torch.get_default_dtype() is torch.float32
            assert torch.get_default_device() == previous_device
        rows.close()
        assert torch.get_default_dtype() is torch.float32

        blocks = values.gauss_values("stress")
        assert next(blocks)[-1].dtype == np.float64
        assert torch.get_default_dtype() is torch.float32
        blocks.close()
        field = next(field for field in values.contour_fields if field.key == "S_Mises")
        assert np.isfinite(values.contour_values(field)["body-1"]).all()
        assert torch.get_default_dtype() is torch.float32
    finally:
        torch.set_default_dtype(previous_dtype)


def test_elements_without_gauss_points_export_only_element_data(
    iteration_model, tmp_path, monkeypatch
):
    _, controller, result = iteration_model
    element = controller.assembly._instances["body-1"].part.elems["C3D8"]

    def no_gauss(_self, _nodes):
        raise NotImplementedError

    monkeypatch.setattr(type(element), "get_gaussian_points", no_gauss)
    assert FiniteElementResults(controller, result).available_fields("elements") == ("element_coordinates",)
    assert {field.key for field in FiniteElementResults(controller, result).contour_fields} == {
        "U", "U1", "U2", "U3"
    }
    path = export_fields(
        controller,
        result,
        tmp_path / "elements.csv",
        location="elements",
        fields=[
            "element_coordinates",
            "gauss_coordinates",
            "energy",
            "stress",
            "strain",
        ],
    )
    with path.open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 8
    assert set(rows[0]) == {"instance", "element_block", "element_id", "CX", "CY", "CZ"}
    assert all(row["CX"] for row in rows)
    with pytest.raises(ValueError, match="no data"):
        export_fields(
            controller,
            result,
            tmp_path / "no_gauss.csv",
            location="elements",
            fields=["stress"],
        )
    assert not (tmp_path / "no_gauss.csv").exists()


def test_gauss_strain_uses_global_axes_for_rotated_instances(iteration_model, tmp_path):
    _, controller, _ = iteration_model
    extension = 0.01
    with cpu_torch_defaults():
        instance = torchfea.Instance(
            "body", translation=[2.0, 3.0, 4.0], rotation=[0.0, 0.0, math.pi / 2]
        )
        controller.assembly._instances["body-1"] = instance
        controller.initialize()
        rgc = controller.GC2RGC(torch.zeros_like(controller.assembly._GC))
        local = torch.zeros_like(instance.part.nodes)
        local[:, 0] = instance.part.nodes[:, 0] * extension
        rgc[instance._RGC_index] = local @ instance.rotation_matrix.T
        result = torchfea.solver.StaticResult(
            GC=controller.RGC2GC(rgc),
            work_conditions=controller.assembly.get_work_conditions(),
            model_hash=controller.get_model_hash(),
            converged=True,
        )
        output = export_fields(
            controller,
            result,
            tmp_path / "rotated_strain.csv",
            location="elements",
            fields=["strain"],
        )
        export_fields(
            controller, result, tmp_path / "rotated_nodes.csv", fields=["coordinates"]
        )
    with output.open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 64
    for row in rows:
        assert float(row["E22"]) == pytest.approx(((1 + extension) ** 2 - 1) / 2)
        assert float(row["E11"]) == pytest.approx(0, abs=1e-12)
    with (tmp_path / "rotated_nodes.csv").open(encoding="utf-8-sig") as stream:
        first = next(csv.DictReader(stream))
    assert [float(first[key]) for key in ("X", "Y", "Z")] == pytest.approx(
        [2.0, 3.0, 4.0]
    )


def test_mixed_elements_do_not_invent_gauss_points(tmp_path):
    from types import SimpleNamespace

    class PlainElement:
        _elems = torch.tensor([[1, 2]])
        _elems_index = torch.tensor([1])

        def get_gaussian_points(self, nodes):
            raise NotImplementedError

    class IntegratedElement:
        _elems = torch.tensor([[0, 1]])
        _elems_index = torch.tensor([0])
        gaussian_weight = torch.ones((1, 1))

        def get_gaussian_points(self, nodes):
            return nodes[self._elems].mean(dim=1)[None, ...]

        def get_potential_energy_density(self, local):
            return torch.full((1, 1), 2.0)

    nodes = torch.tensor([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0]])
    instance = SimpleNamespace(
        enabled=True,
        nodes=nodes,
        _RGC_index=slice(0, 9),
        rotation_matrix=None,
        part=SimpleNamespace(
            elems={"solid": IntegratedElement(), "plain": PlainElement()}
        ),
    )
    controller = SimpleNamespace(
        assembly=SimpleNamespace(_instances={"part": instance}),
        GC2RGC=lambda values: values,
        get_model_hash=lambda: "mixed model",
    )
    result = SimpleNamespace(
        GC=torch.zeros(9), converged=True, model_hash="mixed model"
    )
    path = export_fields(
        controller,
        result,
        tmp_path / "mixed.csv",
        location="elements",
        fields=["element_coordinates", "gauss_coordinates", "energy"],
    )
    with path.open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2
    assert rows[0]["integration_point"] == "1"
    assert rows[0]["strain_energy_density"] == "2.0"
    assert rows[1]["integration_point"] == ""
    assert rows[1]["strain_energy_density"] == ""
    assert rows[1]["X"] == ""
    assert float(rows[1]["CY"]) == pytest.approx(0.5)
    export_fields(
        controller,
        result,
        tmp_path / "mixed.npz",
        location="elements",
        fields=["element_coordinates", "energy"],
    )
    with np.load(tmp_path / "mixed.npz", allow_pickle=False) as data:
        assert np.isnan(data["integration_point"][1])
        assert np.isnan(data["strain_energy_density"][1])
        assert all(data[key].dtype != object for key in data.files)


def test_failed_export_preserves_existing_file_and_cleans_temporary_files(
    iteration_model, tmp_path, monkeypatch
):
    from morphopt.postprocess import (
        RESULT_FIELDS,
        ResultField,
        ResultLocation,
        ResultTable,
    )

    _, controller, result = iteration_model

    def broken_rows():
        yield "body-1", 1, 0.0
        raise ValueError("field evaluation failed")

    monkeypatch.setitem(
        RESULT_FIELDS,
        "broken",
        ResultField(
            "broken",
            "Test provider",
            ResultLocation.NODES,
            lambda context: ResultTable(
                "broken", ("instance", "node_id", "bad"), broken_rows()
            ),
        ),
    )
    path = tmp_path / "user_data.csv"
    path.write_text("original data")
    with pytest.raises(ValueError, match="field evaluation failed"):
        export_fields(controller, result, path, fields=["broken"], overwrite=True)
    assert path.read_text() == "original data"
    assert not list(tmp_path.glob(".user_data.csv.*"))
    new_path = tmp_path / "incomplete.csv"
    with pytest.raises(ValueError, match="field evaluation failed"):
        export_fields(controller, result, new_path, fields=["broken"])
    assert not new_path.exists()
    assert not list(tmp_path.glob(".incomplete.csv.*"))


def test_contours_match_exported_gauss_fields_and_cache_by_group(iteration_model, tmp_path):
    _, controller, result = iteration_model
    path = export_fields(controller, result, tmp_path / 'contours.npz',
                          location='elements', fields=['energy', 'stress', 'strain'])
    instance = controller.assembly._instances['body-1']
    contours = FiniteElementResults(controller, result)
    previous_dtype = torch.get_default_dtype()
    with np.load(path) as exported:
        for field in contours.contour_fields:
            actual = contours.contour_values(field)['body-1']
            if field.source == 'displacement':
                displacement = controller.GC2RGC(result.GC)[instance._RGC_index].detach().cpu().numpy()
                expected = (np.linalg.norm(displacement, axis=1) if field.key == 'U'
                            else displacement[:, int(field.key[1]) - 1])
            else:
                sums = np.zeros(len(instance.nodes))
                counts = np.zeros(len(instance.nodes))
                for block, element in instance.part.elems.items():
                    for local_index, element_id in enumerate(element._elems_index.tolist()):
                        selection = ((exported['element_block'] == block)
                                     & (exported['element_id'] == element_id + 1))
                        mean = np.average(exported[field.key][selection],
                                          weights=exported['reference_volume'][selection])
                        nodes = element._elems[local_index].cpu().numpy()
                        sums[nodes] += mean
                        counts[nodes] += 1
                expected = sums / counts
            np.testing.assert_allclose(actual, expected, atol=1e-12)
        field = next(field for field in contours.contour_fields if field.key == 'S11')
        assert np.shares_memory(contours.contour_values(field)['body-1'], contours.contour_values(field)['body-1'])
    assert torch.get_default_dtype() is previous_dtype


def test_contour_strain_rotates_into_global_axes(iteration_model):
    _, controller, _ = iteration_model
    with cpu_torch_defaults():
        instance = torchfea.Instance('body', rotation=[0., 0., math.pi / 2])
        controller.assembly._instances['body-1'] = instance
        controller.initialize()
        extension = 0.1
        rgc = controller.GC2RGC(torch.zeros_like(controller.assembly._GC))
        local = torch.zeros_like(instance.part.nodes)
        local[:, 0] = extension * instance.part.nodes[:, 0]
        rgc[instance._RGC_index] = local @ instance.rotation_matrix.T
        result = torchfea.solver.StaticResult(GC=controller.RGC2GC(rgc), converged=True,
                                            work_conditions=controller.assembly.get_work_conditions())
        contours = FiniteElementResults(controller, result)
        for field in contours.contour_fields:
            if field.source == 'strain':
                expected = ((1 + extension) ** 2 - 1) / 2 if field.key == 'E22' else 0.
                np.testing.assert_allclose(contours.contour_values(field)['body-1'], expected, atol=1e-12)


def test_contour_average_handles_weights_missing_nodes_and_sparse_element_ids():
    from types import SimpleNamespace

    class IntegratedElement:
        _elems = torch.tensor([[0, 1], [1, 2]])
        _elems_index = torch.tensor([8, 3])
        gaussian_weight = torch.tensor([[1., 3.], [3., 1.]])

        def get_gaussian_points(self, nodes):
            return nodes[self._elems].mean(dim=1)[None].expand(2, -1, -1)

        def get_potential_energy_density(self, local):
            return torch.tensor([[0., 8.], [4., 0.]])

    class PlainElement:
        _elems = torch.tensor([[2, 3]])
        _elems_index = torch.tensor([2])

    instance = SimpleNamespace(enabled=True, nodes=torch.zeros(4, 3),
        _RGC_index=slice(0, 12), rotation_matrix=None,
        part=SimpleNamespace(elems={'solid': IntegratedElement(), 'plain': PlainElement()}))
    controller = SimpleNamespace(assembly=SimpleNamespace(_instances={'body': instance}),
                                 GC2RGC=lambda values: values)
    result = SimpleNamespace(GC=torch.zeros(12))
    contours = FiniteElementResults(controller, result)
    assert not any(field.source in ('stress', 'strain') for field in contours.contour_fields)
    field = next(field for field in contours.contour_fields if field.source == 'energy')
    np.testing.assert_allclose(contours.contour_values(field)['body'], [3., 4.5, 6., np.nan])
