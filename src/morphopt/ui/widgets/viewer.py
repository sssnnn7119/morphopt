"""Qt controls for Part/Assembly preview; geometry and rendering are delegated."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from pyvistaqt import QtInteractor
from ..i18n import tr
from ..model.problem import PartInterfaceNode, ProblemDefinition
from ..visualization.geometry import PreviewGeometry
from ..visualization.loads import LoadPreviewVisitor
from .preview_renderer import PreviewRenderer


class _PlotHost(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.plotter = QtInteractor(self)
        lay.addWidget(self.plotter.interactor)
        # Keep the preview consistent with the deformation pages used by the
        # optimization monitor: a dark canvas plus PyVista's soft light kit.
        self.plotter.set_background("#0e131c")
        self.plotter.enable_lightkit()


class PreviewViewer(QWidget):
    geometryChanged = Signal()

    def __init__(
        self,
        parent=None,
        *,
        geometry: PreviewGeometry | None = None,
        loads: LoadPreviewVisitor | None = None,
    ):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        bar = QHBoxLayout()
        self._lbl_view = QLabel(tr('ui.widgets.viewer.view'))
        bar.addWidget(self._lbl_view)
        self.view_combo = QComboBox()
        self.view_combo.addItem(tr('ui.widgets.viewer.part'), "part")
        self.view_combo.addItem(tr('ui.widgets.viewer.assembly'), "assembly")
        self.view_combo.setCurrentIndex(1)
        self.view_combo.currentIndexChanged.connect(self._on_view_changed)
        bar.addWidget(self.view_combo)

        self._lbl_part = QLabel(tr('ui.widgets.viewer.part_2eacf781'))
        bar.addWidget(self._lbl_part)
        self.part_combo = QComboBox()
        self.part_combo.currentIndexChanged.connect(self._on_part_changed)
        bar.addWidget(self.part_combo)

        self._lbl_step = QLabel(tr('ui.widgets.viewer.step'))
        bar.addWidget(self._lbl_step)
        self.step_combo = QComboBox()
        self.step_combo.currentIndexChanged.connect(self._redraw_loads)
        bar.addWidget(self.step_combo)
        bar.addStretch(1)
        self._btn_reset = QPushButton(tr('ui.widgets.viewer.reset_view'))
        self._btn_reset.clicked.connect(self._reset_view)
        bar.addWidget(self._btn_reset)
        outer.addLayout(bar)

        self.host = _PlotHost(self)
        outer.addWidget(self.host, 1)

        self._problem: ProblemDefinition | None = None
        self.geometry = geometry or PreviewGeometry()
        self.loads = loads or LoadPreviewVisitor()
        self.renderer = PreviewRenderer(self.host.plotter)
        self._sync_view_controls()

    def set_problem(self, problem: ProblemDefinition) -> None:
        self._problem = problem
        self.refresh()

    def refresh(self) -> None:
        self._rebuild_all()

    def apply_language(self) -> None:
        """Re-apply the viewer's static texts in place (keeps the viewport)."""
        self._lbl_view.setText(tr('ui.widgets.viewer.view'))
        self._lbl_part.setText(tr('ui.widgets.viewer.part_2eacf781'))
        self._lbl_step.setText(tr('ui.widgets.viewer.step'))
        self._btn_reset.setText(tr('ui.widgets.viewer.reset_view'))
        # Keep whichever load step is selected while re-localizing the combo.
        # Signals are blocked so a hidden viewer is not forced to re-render
        # (rendering a backgrounded viewport is what used to blacken the
        # observer's GL pages during a language switch).
        current_part = self.part_combo.currentData()
        current_step = self.step_combo.currentData()
        self._sync_part_combo(current_part)
        current_view = self.view_combo.currentData()
        self.view_combo.blockSignals(True)
        self.view_combo.clear()
        self.view_combo.addItem(tr('ui.widgets.viewer.part'), "part")
        self.view_combo.addItem(tr('ui.widgets.viewer.assembly'), "assembly")
        self._select_combo_data(self.view_combo, current_view)
        self.view_combo.blockSignals(False)
        self._sync_step_combo()
        self._select_combo_data(self.step_combo, current_step)
        self._sync_view_controls()

    def _on_view_changed(self, *_args) -> None:
        self._sync_view_controls()
        self._rebuild_all()

    def _on_part_changed(self, *_args) -> None:
        if self.view_combo.currentData() == "part":
            self._rebuild_all()

    def _sync_view_controls(self) -> None:
        part_view = self.view_combo.currentData() == "part"
        self._lbl_part.setVisible(part_view)
        self.part_combo.setVisible(part_view)
        self._lbl_step.setVisible(not part_view)
        self.step_combo.setVisible(not part_view)

    def _sync_part_combo(
        self, selected: PartInterfaceNode | None = None
    ) -> None:
        self.part_combo.blockSignals(True)
        self.part_combo.clear()
        if self._problem is not None:
            parts = self._problem.part_interfaces()
            for part in parts:
                self.part_combo.addItem(part.name or part.resolved_part_name(), part)
            if selected is not None:
                index = next(
                    (
                        i
                        for i, part in enumerate(parts)
                        if part is selected
                        or part.name == getattr(selected, "name", None)
                    ),
                    -1,
                )
                if index >= 0:
                    self.part_combo.setCurrentIndex(index)
        self.part_combo.blockSignals(False)

    def _sync_step_combo(self) -> None:
        steps = self._problem.steps if self._problem is not None else None
        current = self.step_combo.currentData()
        n = (
            max(int(steps.num_steps), len(steps.step_values))
            if steps is not None
            else 0
        )
        self.step_combo.blockSignals(True)
        self.step_combo.clear()
        self.step_combo.addItem(tr('ui.widgets.viewer.no_load_step'), -1)
        for s in range(n):
            self.step_combo.addItem(tr('ui.widgets.viewer.step_value', value_0=s), s)
        selected = self.step_combo.findData(current)
        if selected >= 0:
            self.step_combo.setCurrentIndex(selected)
        elif n:
            self.step_combo.setCurrentIndex(1)
        else:
            self.step_combo.setCurrentIndex(0)
        self.step_combo.blockSignals(False)

    @staticmethod
    def _select_combo_data(combo: QComboBox, value: object) -> None:
        if value is None:
            return
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _reset_view(self) -> None:
        self.host.plotter.reset_camera()

    def _rebuild_all(self) -> None:
        self._sync_part_combo(self.part_combo.currentData())
        self._sync_step_combo()
        if self._problem is None:
            return
        scene = self.geometry.build(self._problem, self.view_combo.currentData(), self.part_combo.currentData())
        self.renderer.draw_scene(scene)
        self.host.plotter.show_axes()
        self.host.plotter.view_isometric()
        self.host.plotter.reset_camera()
        self._redraw_loads()

    def _redraw_loads(self, *_args) -> None:
        scene = None
        if self._problem is not None and self.view_combo.currentData() == "assembly":
            scene = self.loads.build(self.geometry, self.step_combo.currentData())
        self.renderer.draw_loads(
            scene,
            tr('ui.widgets.viewer.pressure_teal_force_red_moment_yellow_body_force_orange_spring_purple_do'),
        )
