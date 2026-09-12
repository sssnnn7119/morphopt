"""Right-hand preview: initial geometry + material field box + step loads.

The geometry shown is the *initial* shape described by the model tree
(cylinders/spheres match ``r0``/``length``/``init_location`` of the surface
factories at t=0).  Full mesh regeneration (Gmsh) is intentionally not done in
the preview; it happens when the problem is exported/run.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QPushButton

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor

from ..model.problem import Node, ProblemDefinition
from ..model.schemas import INTERFACE_TYPES
from ..i18n import T
from ...optcore.modelparams.geometry import (
    load_geometry_assembly, resolve_model_path)


class _PlotHost(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.plotter = QtInteractor(self)
        lay.addWidget(self.plotter.interactor)
        # Keep the preview consistent with the deformation pages used by the
        # optimization monitor: a dark canvas plus PyVista's soft light kit.
        self.plotter.set_background("black")
        self.plotter.enable_lightkit()


class PreviewViewer(QWidget):
    geometryChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        bar = QHBoxLayout()
        self._lbl_step = QLabel(T("工况：", "Step:"))
        bar.addWidget(self._lbl_step)
        self.step_combo = QComboBox()
        self.step_combo.addItem(T("(无)", "(none)"))
        self.step_combo.currentIndexChanged.connect(self._redraw_loads)
        bar.addWidget(self.step_combo)
        bar.addStretch(1)
        self._btn_reset = QPushButton(T("重置视角", "Reset view"))
        self._btn_reset.clicked.connect(self._reset_view)
        bar.addWidget(self._btn_reset)
        outer.addLayout(bar)

        self.host = _PlotHost(self)
        outer.addWidget(self.host, 1)

        self._problem: ProblemDefinition | None = None
        self._base_meshes: list = []
        self._overlay_actors: list = []
        self._model_cache_key: tuple[str, int] | None = None
        self._model_meshes: dict = {}
        self._model_assembly = None

    # ------------------------------------------------------------------ api
    def set_problem(self, problem: ProblemDefinition) -> None:
        self._problem = problem
        self.refresh()

    def refresh(self) -> None:
        self._rebuild_all()

    # ------------------------------------------------------------ language
    def apply_language(self) -> None:
        """Re-apply the viewer's static texts in place (keeps the viewport)."""
        self._lbl_step.setText(T("工况：", "Step:"))
        self._btn_reset.setText(T("重置视角", "Reset view"))
        # Keep whichever load step is selected while re-localizing the combo.
        # Signals are blocked so a hidden viewer is not forced to re-render
        # (rendering a backgrounded viewport is what used to blacken the
        # observer's GL pages during a language switch).
        idx = self.step_combo.currentIndex()
        self._sync_step_combo()
        self.step_combo.blockSignals(True)
        if 0 <= idx < self.step_combo.count():
            self.step_combo.setCurrentIndex(idx)
        self.step_combo.blockSignals(False)

    # ------------------------------------------------------------- rebuilds
    def _rebuild_all(self) -> None:
        plotter = self.host.plotter
        plotter.clear()
        plotter.enable_lightkit()
        self._base_meshes = []
        if self._problem is None:
            plotter.render()
            return
        geometry = self._problem.geometry
        if self._problem.scheme == "simp" and geometry is not None:
            self._draw_torchfea_model(geometry)
        else:
            surfaces = [s for s in self._problem.surfaces()]
            for i, srf in enumerate(surfaces):
                mesh = self._surface_mesh(srf)
                if mesh is None:
                    continue
                opacity = 0.30
                actor = plotter.add_mesh(mesh, color=[40/255, 120/255, 181/255], opacity=opacity)
                self._base_meshes.append((srf, mesh, actor))

        # material bounding box (SIMP / codesign)
        mat = self._problem.material
        if mat is not None:
            bb = mat.bounding_box
            if bb and any(bb) and len(bb) == 6:
                box = pv.Box(bounds=[bb[0], bb[1], bb[2], bb[3], bb[4], bb[5]])
                plotter.add_mesh(box, style="wireframe", color="#7f8c8d", opacity=0.6)
                plotter.add_mesh(box, color="#7f8c8d", opacity=0.03)

        plotter.show_axes()
        # The model may contain several Parts/Instances with very different
        # extents.  Fit once after all actors are present, like the monitor's
        # result viewport does after rebuilding a scene.
        plotter.reset_camera()
        self._sync_step_combo()
        self._redraw_loads()

    def _draw_torchfea_model(self, geometry: Node) -> None:
        """Render every Instance from the linked TorchFEA Assembly."""
        plotter = self.host.plotter
        if not geometry.model_directory or not geometry.model_filename:
            plotter.add_text(
                T("请在初始几何节点导入 TorchFEA 模型",
                  "Import a TorchFEA model from Initial Geometry"),
                position="upper_left", color="#9aa4b2", font_size=10)
            return
        try:
            path = resolve_model_path(
                geometry.model_directory, geometry.model_filename)
            cache_key = (str(path), path.stat().st_mtime_ns)
            if cache_key != self._model_cache_key:
                assembly = load_geometry_assembly(
                    geometry.model_directory, geometry.model_filename)
                assembly.initialize()
                self._model_meshes = assembly.get_meshes()
                self._model_assembly = assembly
                self._model_cache_key = cache_key
            # Match DeformationCasePage: opaque blue mesh, visible but subtle
            # element edges, and lightkit shading.  This makes an imported
            # model read like an optimization result rather than a translucent
            # CAD preview.  The monitor does not put a legend over the model,
            # so instance names stay in the model tree instead of becoming a
            # distracting ``Part-1-1`` badge in the viewport.
            mesh_color = (40 / 255, 120 / 255, 181 / 255)
            for name, mesh in self._model_meshes.items():
                actor = plotter.add_mesh(
                    mesh, color=mesh_color, opacity=1.0,
                    show_edges=True)
                self._base_meshes.append((name, mesh, actor))
        except Exception as exc:
            self._model_cache_key = None
            self._model_meshes = {}
            self._model_assembly = None
            plotter.add_text(
                T(f"TorchFEA 模型预览：{exc}",
                  f"TorchFEA model preview: {exc}"),
                position="upper_left", color="#e74c3c", font_size=10)

    def _sync_step_combo(self) -> None:
        steps = self._problem.steps
        n = int(steps.num_steps) if steps is not None else 1
        self.step_combo.blockSignals(True)
        self.step_combo.clear()
        self.step_combo.addItem(T("(无)", "(none)"))
        for s in range(n):
            self.step_combo.addItem(T(f"工况 {s}", f"Step {s}"))
        self.step_combo.blockSignals(False)

    # ------------------------------------------------------------- geometry
    def _surface_mesh(self, srf: Node):
        st = srf.surface_type
        p = dict(srf.field_items())
        if st in ("bsp_cylinder", "cpgeo_cylinder"):
            loc = p.get("init_location") or [0.0, 0.0, 0.0]
            z0 = loc[2]
            length = float(p.get("length", 1.0))
            center = [loc[0], loc[1], z0 + length / 2.0]
            return pv.Cylinder(center=center, direction=(0.0, 0.0, 1.0),
                               radius=float(p.get("r0", 1.0)), height=length,
                               resolution=64)
        if st == "cpgeo_sphere":
            loc = p.get("init_location") or [0.0, 0.0, 0.0]
            return pv.Sphere(center=loc, radius=float(p.get("r0", 1.0)),
                             theta_resolution=48, phi_resolution=48)
        if st == "fixed_stl":
            path = p.get("path_stl", "")
            if path and os.path.exists(path):
                return pv.read(path)
        return None

    # ----------------------------------------------------------------- loads
    def _interfaces_by_name(self) -> dict[str, Node]:
        return {interface.name: interface for interface in self._problem.interfaces()
                if interface.name}

    def _rp_location(self, rp_name: str):
        for interface in self._problem.interfaces():
            if (interface.name == rp_name
                    and interface.interface_type == "ReferencePoint"):
                loc = interface.rp_location or [0.0, 0.0, 0.0]
                return [float(x) for x in loc]
        return None

    def _redraw_loads(self) -> None:
        plotter = self.host.plotter
        for a in self._overlay_actors:
            try:
                plotter.remove_actor(a)
            except Exception:
                pass
        self._overlay_actors = []
        if self._problem is None:
            plotter.render()
            return

        idx = self.step_combo.currentIndex() - 1
        if idx < 0:
            plotter.render()
            return

        steps = self._problem.steps
        if steps is None:
            return
        values = list(steps.step_values)
        if idx >= len(values):
            return
        step = values[idx] or {}
        by_name = self._interfaces_by_name()
        surfaces = [s for s in self._problem.surfaces()]
        scale_len = self._model_diagonal() if self._model_meshes else _diag(self._problem)

        for name, amps in step.items():
            iface = by_name.get(name)
            if iface is None:
                continue
            itype = iface.interface_type
            amps = [float(a) for a in (amps or [])]
            if itype == "Pressure":
                # Only show a pressure surface when it is actually loaded in
                # this step; a zeroed / off pressure must not remain visible
                # (otherwise a later step appears to still carry an earlier
                # step's load).
                if not any(abs(v) > 1e-12 for v in amps):
                    continue
                # tint the referenced surface with a semi-transparent copy
                surf_name = str(iface.surface_name or "")
                mesh = None
                if self._problem.scheme == "simp" and self._model_assembly is not None:
                    try:
                        mesh = self._model_assembly.get_instance(
                            iface.instance_name).get_mesh(surf_name=surf_name)
                    except (KeyError, ValueError):
                        mesh = None
                else:
                    srf_idx = _surface_index_from_name(surf_name)
                    if 0 <= srf_idx < len(surfaces):
                        mesh = self._surface_mesh(surfaces[srf_idx])
                if mesh is not None:
                    over = mesh.copy()
                    act = plotter.add_mesh(over, color="#1abc9c", opacity=0.45,
                                           show_edges=False)
                    self._overlay_actors.append(act)
            elif itype in ("ConcentratedForce", "ConcentratedMoment"):
                rp = iface.rp_name or ""
                loc = self._rp_location(rp)
                if loc is None:
                    continue
                vals = [float(a) for a in amps[:3]]
                while len(vals) < 3:
                    vals.append(0.0)
                vec = np.array(vals)
                if np.allclose(vec, 0.0):
                    continue
                arrow_length = _load_arrow_length(scale_len)
                direction = vec / np.linalg.norm(vec)
                color = "#e74c3c" if itype == "ConcentratedForce" else "#f1c40f"
                arrow = pv.Arrow(start=loc, direction=direction, scale=arrow_length,
                                 tip_length=0.30, tip_radius=0.08, shaft_radius=0.025)
                act = plotter.add_mesh(arrow, color=color)
                self._overlay_actors.append(act)
        plotter.render()

    def _model_diagonal(self) -> float:
        bounds = [mesh.bounds for mesh in self._model_meshes.values()
                  if mesh.n_points]
        if not bounds:
            return 10.0
        lo = np.min(np.asarray([[b[0], b[2], b[4]] for b in bounds]), axis=0)
        hi = np.max(np.asarray([[b[1], b[3], b[5]] for b in bounds]), axis=0)
        diagonal = float(np.linalg.norm(hi - lo))
        return diagonal if diagonal > 0 else 10.0

    def _reset_view(self) -> None:
        self.host.plotter.reset_camera()


def _diag(problem) -> float:
    lo = np.full(3, np.inf)
    hi = -lo
    for s in problem.surfaces():
        b = _surface_bounds(s)
        if b is None:
            continue
        lo = np.minimum(lo, np.array(b[::2]))
        hi = np.maximum(hi, np.array(b[1::2]))
    if not np.isfinite(lo).all():
        return 10.0
    d = float(np.linalg.norm(hi - lo))
    return d if d > 0 else 10.0


def _load_arrow_length(characteristic_length: float) -> float:
    """Map the model characteristic length to a readable load-arrow length."""
    return float(characteristic_length) * 0.20


def _surface_bounds(srf: Node):
    st = srf.surface_type
    p = dict(srf.field_items())
    if st in ("bsp_cylinder", "cpgeo_cylinder"):
        loc = p.get("init_location") or [0, 0, 0]
        length = float(p.get("length", 1))
        return [-float(p.get("r0", 1)) , float(p.get("r0", 1)),
                -float(p.get("r0", 1)), float(p.get("r0", 1)),
                loc[2], loc[2] + length]
    if st == "cpgeo_sphere":
        loc = p.get("init_location") or [0, 0, 0]
        r = float(p.get("r0", 1))
        return [loc[0]-r, loc[0]+r, loc[1]-r, loc[1]+r, loc[2]-r, loc[2]+r]
    return None


def _surface_index_from_name(surface_name: str) -> int:
    """surface_1_All / surface_1_offset -> 1"""
    import re
    m = re.match(r"surface_(\d+)_", surface_name)
    return int(m.group(1)) if m else -1
