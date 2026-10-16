"""Qt controls for Part/Assembly preview; geometry and rendering are delegated."""
from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, QTimer, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from pyvistaqt import QtInteractor
from ..theme import theme_manager
from ..i18n import tr
from ..refresh import RefreshContext
from ..presentation.labels import part_title_text
from ..model.problem import PartNode, ProblemDefinition
from ..visualization.geometry import PreviewGeometry
from ..visualization.loads import LoadPreviewVisitor
from ..visualization.scene import LoadScene
from .preview_renderer import PreviewRenderer
from .plot_style import apply_plotter_theme


class _PlotHost(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self.plotter = QtInteractor(self)
        lay.addWidget(self.plotter.interactor)


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
        outer.setContentsMargins(*theme_manager.palette.layout.zero_margins)

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
        self.step_combo.currentIndexChanged.connect(self._on_step_changed)
        bar.addWidget(self.step_combo)
        bar.addStretch(1)
        self._btn_reset = QPushButton(tr('ui.widgets.viewer.reset_view'))
        self._btn_reset.clicked.connect(self._reset_view)
        bar.addWidget(self._btn_reset)
        outer.addLayout(bar)

        self.host = _PlotHost(self)
        outer.addWidget(self.host, 1)

        self._selected_step: int | None = None
        self._problem: ProblemDefinition | None = None
        self._language_pending = False
        self._theme_pending = False
        self._render_pending = False
        self._pending_reset_camera = False
        self.geometry = geometry or PreviewGeometry()
        self.loads = loads or LoadPreviewVisitor()
        self.renderer = PreviewRenderer(self.host.plotter)
        self._sync_view_controls()

    def set_problem(self, problem: ProblemDefinition) -> None:
        reset_camera = problem is not self._problem
        if reset_camera:
            self._selected_step = None
        self._problem = problem
        self._rebuild_all(reset_camera=reset_camera)

    def refresh_ui(self, context: RefreshContext) -> None:
        if context.restoring:
            self._problem = context.problem
            self._rebuild_all(reset_camera=False)
        elif context.problem is not self._problem or context.geometry_changed:
            self.set_problem(context.problem)
        elif context.loads_changed:
            self._sync_step_combo()
            self._redraw_loads()

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
        self._sync_part_combo(current_part)
        current_view = self.view_combo.currentData()
        self.view_combo.blockSignals(True)
        self.view_combo.clear()
        self.view_combo.addItem(tr('ui.widgets.viewer.part'), "part")
        self.view_combo.addItem(tr('ui.widgets.viewer.assembly'), "assembly")
        self._select_combo_data(self.view_combo, current_view)
        self.view_combo.blockSignals(False)
        self._sync_step_combo()
        self._sync_view_controls()
        self._language_pending = True
        self._refresh_load_language()

    def apply_theme(self) -> None:
        """Rebuild theme-colored actors while preserving the current camera."""
        if not self.isVisible():
            self._theme_pending = True
            return
        self._theme_pending = False
        if self._problem is None:
            apply_plotter_theme(self.host.plotter)
            self.host.plotter.render()
            return
        self._rebuild_all(reset_camera=False)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._render_pending or self._language_pending or self._theme_pending:
            QTimer.singleShot(0, self._render_pending_view)

    def _render_pending_view(self) -> None:
        if not self.isVisible():
            return
        rebuilt = False
        if self._render_pending:
            reset_camera = self._pending_reset_camera
            self._render_pending = False
            self._pending_reset_camera = False
            self._rebuild_all(reset_camera=reset_camera)
            rebuilt = True
            if self._problem is None:
                apply_plotter_theme(self.host.plotter)
                self.host.plotter.render()
        if self._language_pending:
            self._refresh_load_language()
        if self._theme_pending:
            self._theme_pending = False
            if rebuilt:
                return
            if self._problem is None:
                apply_plotter_theme(self.host.plotter)
                self.host.plotter.render()
            else:
                self._rebuild_all(reset_camera=False)

    def _refresh_load_language(self) -> None:
        if self._language_pending and self.isVisible():
            self._redraw_loads()
            self._language_pending = False

    def _on_view_changed(self, *_args) -> None:
        self._sync_view_controls()
        self._rebuild_all(reset_camera=True)

    def _on_part_changed(self, *_args) -> None:
        if self.view_combo.currentData() == "part":
            self._rebuild_all(reset_camera=True)

    def _on_step_changed(self, *_args) -> None:
        self._selected_step = self.step_combo.currentData()
        self._redraw_loads()

    def _sync_view_controls(self) -> None:
        part_view = self.view_combo.currentData() == "part"
        self._lbl_part.setVisible(part_view)
        self.part_combo.setVisible(part_view)
        self._lbl_step.setVisible(not part_view)
        self.step_combo.setVisible(not part_view)

    def _sync_part_combo(
        self, selected: PartNode | None = None
    ) -> None:
        self.part_combo.blockSignals(True)
        self.part_combo.clear()
        if self._problem is not None:
            parts = self._problem.parts()
            for part in parts:
                self.part_combo.addItem(part_title_text(part), part)
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
        n = (
            max(int(steps.num_steps), len(steps.step_values))
            if steps is not None
            else 0
        )
        with QSignalBlocker(self.step_combo):
            self.step_combo.clear()
            self.step_combo.addItem(tr('ui.widgets.viewer.no_load_step'), -1)
            for step in range(n):
                self.step_combo.addItem(tr('ui.widgets.viewer.step_value', value_0=step), step)
            selected = self.step_combo.findData(self._selected_step)
            self.step_combo.setCurrentIndex(selected if selected >= 0 else (1 if n else 0))
            self._selected_step = self.step_combo.currentData()

    @staticmethod
    def _select_combo_data(combo: QComboBox, value: object) -> None:
        if value is None:
            return
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _reset_view(self) -> None:
        self.host.plotter.reset_camera()
        self._redraw_loads()

    def _rebuild_all(self, *, reset_camera: bool = False) -> None:
        if isinstance(self.host.plotter, QWidget) and not self.isVisible():
            self._render_pending = True
            self._pending_reset_camera |= reset_camera
            return
        reset_camera |= self._pending_reset_camera
        self._render_pending = False
        self._pending_reset_camera = False
        self._sync_part_combo(self.part_combo.currentData())
        self._sync_step_combo()
        if self._problem is None:
            return
        camera = self.host.plotter.camera_position
        scene = self.geometry.build(self._problem, self.view_combo.currentData(), self.part_combo.currentData())
        # Prepare geometry and loads before replacing any actors. Incomplete
        # definitions must not erase a working viewport during data preparation.
        loads = self._load_scene()
        self.renderer.draw_scene(scene)
        self.host.plotter.show_axes()
        if reset_camera:
            self.host.plotter.view_isometric()
        else:
            self.host.plotter.camera_position = camera
        self.renderer.draw_loads(loads)
        if reset_camera:
            self.host.plotter.reset_camera()
            # Callout spacing is measured in screen pixels. Reflow against
            # the fitted camera after including load glyphs in the bounds.
            self.renderer.draw_loads(loads)

    def _load_scene(self) -> LoadScene | None:
        if self._problem is not None and self.view_combo.currentData() == "assembly":
            return self.loads.build(self.geometry, self._selected_step)
        return None

    def _redraw_loads(self, *_args) -> None:
        if isinstance(self.host.plotter, QWidget) and not self.isVisible():
            self._render_pending = True
            return
        if self._render_pending:
            self._render_pending_view()
            return
        self.renderer.draw_loads(self._load_scene())
