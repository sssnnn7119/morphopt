"""Evaluated design and deformation meshes in a standard VTK multiblock time series."""

from __future__ import annotations

import json
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import numpy as np
import pyvista as pv
from vtkmodules.vtkIOXML import vtkXMLMultiBlockDataWriter

from ..constants import CONSTANT
from ..optcore.protocal import ProtocalVisualizable
from .fields import FiniteElementResults


def snapshot_path(log_folder: str | Path, iteration: int) -> Path:
    return Path(log_folder) / "views" / f"iteration_{iteration:06d}.vtm"


def design_components(params):
    """Yield updatable interfaces in model registration order."""
    for category, collection in (("Part", params.geometry), ("FEA", params.feamodel),
                                 ("Material", params.materials)):
        for component in collection.design_interfaces():
            yield category, component


def has_control_net(surface: Any) -> bool:
    return any(cls.__name__ in {"BspSurface", "CPGEOSurface"} for cls in type(surface).__mro__)


def control_net_mesh(surface: Any) -> pv.PolyData | None:
    """Connect current control points using the CPGEO topology or periodic BSP grid."""
    try:
        points = np.asarray(surface.control_points.detach().cpu(), dtype=float)
    except Exception:
        points = np.asarray(surface.control_points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not len(points):
        return

    faces = None
    model = getattr(surface, "model", None)
    if model is not None and hasattr(model, "_cp_faces"):
        faces = np.asarray(model._cp_faces, dtype=int)
    if faces is not None and faces.ndim == 2 and faces.shape[1] == 3:
        edges = np.concatenate(
            (faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]), axis=0
        )
        edges = np.unique(np.sort(edges, axis=1), axis=0)
    else:
        size = getattr(model, "size", None)
        if size is None or len(size) != 2 or int(np.prod(size)) != len(points):
            return
        rows, columns = (int(size[0]), int(size[1]))
        edges_list: list[tuple[int, int]] = []
        for row in range(rows):
            for column in range(columns - 1):
                edges_list.append((row * columns + column, row * columns + column + 1))
            # BSP cylinders are periodic in the circumferential direction.
            if columns > 2:
                edges_list.append((row * columns + columns - 1, row * columns))
        for row in range(rows - 1):
            for column in range(columns):
                edges_list.append(
                    (row * columns + column, (row + 1) * columns + column)
                )
        edges = np.asarray(edges_list, dtype=int)

    if not len(edges):
        return pv.PolyData(points)
    lines = np.column_stack((np.full(len(edges), 2, dtype=np.int64), edges)).ravel()
    return pv.PolyData(points, lines=lines)


def capture_design(params) -> pv.MultiBlock:
    """Freeze the meshes evaluated in this solve before any design variables change."""
    scene = pv.MultiBlock()
    for category, component in design_components(params):
        if not isinstance(component, ProtocalVisualizable):
            continue
        meshes = pv.MultiBlock()
        surfaces = getattr(component, "surfaceinterfaces", ())
        datasets = component.get_meshes()
        if not datasets and type(component).plot is not ProtocalVisualizable.plot:
            # Some task-defined components expose their geometry only through plot().
            with closing(pv.Plotter(off_screen=True)) as plotter:
                component.plot(plotter=plotter)
                datasets = [actor.mapper.dataset for actor in plotter.actors.values()
                            if isinstance(actor, pv.Actor) and actor.mapper is not None
                            and isinstance(actor.mapper.dataset, pv.DataSet)]
        for i, mesh in enumerate(datasets):
            meshes[f"surface_{i}" if surfaces else f"mesh_{i}"] = mesh
        for i, surface in enumerate(surfaces):
            if has_control_net(surface):
                net = control_net_mesh(surface)
                if net is not None:
                    meshes[f"net_{i}"] = net
        if category not in scene.keys():
            scene[category] = pv.MultiBlock()
        scene[category][component.name] = pv.MultiBlock({type(component).__name__: meshes})
    # Custom get_meshes implementations can share numpy or tensor storage with the optimizer.
    return scene.copy(deep=True)


def _reference_surface(instance) -> tuple[pv.PolyData, np.ndarray]:
    """Compact the exterior once and retain its point-to-FE-node map for all cases."""
    mesh = instance.get_mesh()
    if not mesh.n_cells:
        return mesh, np.empty(0, dtype=np.intp)
    mesh.point_data["node_id"] = np.arange(mesh.n_points)
    mesh = mesh.clean(point_merging=False)
    return mesh, mesh.point_data.pop("node_id")


def save_snapshot(log_folder: str | Path, iteration: int, scene: pv.MultiBlock, objective) -> None:
    """Save one reference exterior per instance and one displacement field per active case."""
    assembly = objective.fe.assembly
    original = assembly.get_work_conditions()
    reference = pv.MultiBlock()
    node_ids = {}
    case_instances = {}
    try:
        for case, result in objective.fe_results.items():
            assembly.set_work_conditions(result.work_conditions)
            active = []
            fields = FiniteElementResults(objective.fe, result)
            for name, instance, displacement in fields.instances():
                if name not in node_ids:
                    mesh, nodes = _reference_surface(instance)
                    node_ids[name] = nodes
                    if nodes.size:
                        reference[name] = mesh
                nodes = node_ids[name]
                if nodes.size:
                    u = displacement.detach().cpu().numpy()
                    reference[name].point_data[f"U_{case}"] = u[nodes]
                    active.append(name)
            if active:
                case_instances[case] = active
    finally:
        assembly.set_work_conditions(original)
    scene["Displacement"] = reference
    path = snapshot_path(log_folder, iteration)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Compress each dataset directly so a reader can still open a single block.
    writer = vtkXMLMultiBlockDataWriter()
    writer.SetFileName(str(path))
    writer.SetInputData(scene)
    writer.SetDataModeToAppended()
    writer.EncodeAppendedDataOff()
    writer.SetCompressorTypeToLZMA()
    writer.SetCompressionLevel(CONSTANT.KERNEL.VISUALIZATION.SNAPSHOT_LZMA_LEVEL)
    writer.SetBlockSize(CONSTANT.KERNEL.VISUALIZATION.SNAPSHOT_BLOCK_BYTES)
    if not writer.Write() or writer.GetErrorCode():
        raise OSError(f"Failed to write VTK snapshot: {path}")
    if case_instances:
        # Record registration and activation order without opening every instance dataset.
        (path.with_suffix("") / "load_cases.json").write_text(
            json.dumps(case_instances, ensure_ascii=False), encoding="utf-8"
        )


@dataclass
class SavedComponent:
    """Index of the native datasets for a component; reading the index loads no meshes."""

    category: str
    name: str
    class_name: str
    files: dict[str, Path]

    def mesh(self, key: str) -> pv.DataSet:
        return pv.read(self.files[key])


class Snapshot:
    """Index a VTM by block names so selecting one view reads only the required files."""

    def __init__(self, path: Path) -> None:
        self.components: dict[tuple[str, str], SavedComponent] = {}
        root = ElementTree.parse(path).getroot().find("vtkMultiBlockDataSet")
        displacement = root.find("Block[@name='Displacement']")
        if displacement is None:
            raise ValueError(f"Missing Displacement block in {path}")
        self._instances = self._files(displacement, path.parent)
        self._case_instances: dict[str, list[str]] = {}
        if self._instances:
            index = path.with_suffix("") / "load_cases.json"
            self._case_instances = json.loads(index.read_text(encoding="utf-8"))

        for group in root.findall("Block"):
            category = group.attrib["name"]
            for item in group.findall("Block"):
                name = item.attrib["name"]
                cls = item.find("Block")
                self.components[category, name] = SavedComponent(
                    category, name, cls.attrib["name"], self._files(cls, path.parent)
                )

    @property
    def cases(self) -> tuple[str, ...]:
        return tuple(self._case_instances)

    def deformation_mesh(self, case: str) -> pv.PolyData | None:
        """Read only the requested displacement array on each participating instance."""
        meshes = []
        field = f"U_{case}"
        for name in self._case_instances.get(case, ()):
            reader = pv.get_reader(self._instances[name])
            reader.disable_all_point_arrays()
            reader.enable_point_array(field)
            mesh = reader.read()
            u = mesh.point_data.pop(field)
            mesh.points = mesh.points + u
            mesh.point_data["U"] = u
            meshes.append(mesh)
        if not meshes:
            return None
        return meshes[0] if len(meshes) == 1 else pv.merge(meshes, merge_points=False)

    @staticmethod
    def _files(block, directory: Path) -> dict[str, Path]:
        return {node.attrib["name"]: directory / node.attrib["file"]
                for node in block.findall("DataSet") if "file" in node.attrib}
