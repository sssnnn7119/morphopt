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


class _PlotHost(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.plotter = QtInteractor(self)
        lay.addWidget(self.plotter.interactor)
        self.plotter.set_background("#0d1117")


class PreviewViewer(QWidget):
    geometryChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        bar = QHBoxLayout()
        bar.addWidget(QLabel(T("工况：", "Step:")))
        self.step_combo = QComboBox()
        self.step_combo.addItem(T("(无)", "(none)"))
        self.step_combo.currentIndexChanged.connect(self._redraw_loads)
        bar.addWidget(self.step_combo)
        bar.addStretch(1)
        btn_reset = QPushButton(T("重置视角", "Reset view"))
        btn_reset.clicked.connect(self._reset_view)
        bar.addWidget(btn_reset)
        outer.addLayout(bar)

        self.host = _PlotHost(self)
        outer.addWidget(self.host, 1)

        self._problem: ProblemDefinition | None = None
        self._base_meshes: list = []
        self._overlay_actors: list = []

    # ------------------------------------------------------------------ api
    def set_problem(self, problem: ProblemDefinition) -> None:
        self._problem = problem
        self.refresh()

    def refresh(self) -> None:
        self._rebuild_all()

    # ------------------------------------------------------------- rebuilds
    def _rebuild_all(self) -> None:
        plotter = self.host.plotter
        plotter.clear()
        self._base_meshes = []
        if self._problem is None:
            plotter.render()
            return
        surfaces = [s for s in self._problem.surfaces()]
        colors = ["#3498db", "#e67e22", "#2ecc71", "#9b59b6", "#e74c3c", "#f1c40f"]
        for i, srf in enumerate(surfaces):
            mesh = self._surface_mesh(srf)
            if mesh is None:
                continue
            opacity = 0.30 if i == 0 else 0.18
            actor = plotter.add_mesh(mesh, color=colors[i % len(colors)], opacity=opacity,
                                     show_edges=(i == 0))
            self._base_meshes.append((srf, mesh, actor))

        # material bounding box (SIMP / codesign)
        mat = next((n for n in self._problem.root.iter_nodes() if n.kind == "material"), None)
        if mat is not None:
            bb = mat.params.get("bounding_box")
            if bb and any(bb) and len(bb) == 6:
                box = pv.Box(bounds=[bb[0], bb[1], bb[2], bb[3], bb[4], bb[5]])
                plotter.add_mesh(box, style="wireframe", color="#7f8c8d", opacity=0.6)
                plotter.add_mesh(box, color="#7f8c8d", opacity=0.03)

        plotter.show_axes()
        self._sync_step_combo()
        self._redraw_loads()

    def _sync_step_combo(self) -> None:
        steps = next((n for n in self._problem.root.iter_nodes() if n.kind == "steps"), None)
        n = int(steps.params.get("num_steps", 1)) if steps is not None else 1
        self.step_combo.blockSignals(True)
        self.step_combo.clear()
        self.step_combo.addItem(T("(无)", "(none)"))
        for s in range(n):
            self.step_combo.addItem(T(f"工况 {s}", f"Step {s}"))
        self.step_combo.blockSignals(False)

    # ------------------------------------------------------------- geometry
    def _surface_mesh(self, srf: Node):
        st = srf.params.get("type", "bsp_cylinder")
        p = srf.params
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
        out = {}
        for nd in self._problem.root.iter_nodes():
            if nd.kind == "interface" and nd.name:
                out[nd.name] = nd
        return out

    def _rp_location(self, rp_name: str):
        for nd in self._problem.root.iter_nodes():
            if nd.kind == "interface" and nd.name == rp_name and \
                    nd.params.get("type") == "ReferencePoint":
                loc = nd.params.get("rp_location") or [0.0, 0.0, 0.0]
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

        steps = next((n for n in self._problem.root.iter_nodes() if n.kind == "steps"), None)
        if steps is None:
            return
        values = steps.params.get("step_values") or []
        if idx >= len(values):
            return
        step = values[idx] or {}
        by_name = self._interfaces_by_name()
        surfaces = [s for s in self._problem.surfaces()]
        scale_len = _diag(self._problem)

        for name, amps in step.items():
            iface = by_name.get(name)
            if iface is None:
                continue
            itype = iface.params.get("type")
            amps = list(amps or [])
            if itype == "Pressure":
                # tint the referenced surface with a semi-transparent copy
                surf_name = str(iface.params.get("surface_name", ""))
                srf_idx = _surface_index_from_name(surf_name)
                if 0 <= srf_idx < len(surfaces):
                    mesh = self._surface_mesh(surfaces[srf_idx])
                    if mesh is not None:
                        over = mesh.copy()
                        act = plotter.add_mesh(over, color="#1abc9c", opacity=0.45,
                                               show_edges=False)
                        self._overlay_actors.append(act)
            elif itype in ("ConcentratedForce", "ConcentratedMoment"):
                rp = iface.params.get("rp_name", "")
                loc = self._rp_location(rp)
                if loc is None:
                    continue
                vals = [float(a) for a in amps[:3]]
                while len(vals) < 3:
                    vals.append(0.0)
                vec = np.array(vals)
                if np.allclose(vec, 0.0):
                    continue
                direction = vec / np.linalg.norm(vec) * (scale_len * 0.12)
                color = "#e74c3c" if itype == "ConcentratedForce" else "#f1c40f"
                arrow = pv.Arrow(start=loc, direction=direction, scale=1.0,
                                 tip_length=0.35, tip_radius=0.06, shaft_radius=0.02)
                act = plotter.add_mesh(arrow, color=color)
                self._overlay_actors.append(act)
        plotter.render()

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


def _surface_bounds(srf: Node):
    st = srf.params.get("type", "bsp_cylinder")
    p = srf.params
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
