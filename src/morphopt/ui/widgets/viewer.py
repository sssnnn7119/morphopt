"""Qt controls for Part/Assembly preview; geometry and rendering are delegated."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from pyvistaqt import QtInteractor

from ..i18n import tr
from ..model.problem import PartNode, ProblemDefinition
from ..presentation.labels import part_title_text
from ..refresh import RefreshContext
from ..theme import theme_manager
from ..visualization.geometry import PreviewGeometry
from ..visualization.loads import LoadPreviewVisitor
from ..visualization.scene import FaceSelection, LoadScene
from .plot_style import apply_plotter_theme
from .preview_renderer import PreviewRenderer


class _PlotHost(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self.plotter = QtInteractor(self)
        lay.addWidget(self.plotter.interactor)


def _qt_to_vtk_position(
    x: float, y: float, widget_size, render_size
) -> tuple[int, int]:
    """Convert widget-local logical pixels to render-window device pixels."""
    width, height = widget_size
    render_width, render_height = render_size
    return (
        round(x * render_width / max(1, width)),
        render_height - 1 - round(y * render_height / max(1, height)),
    )


class _FaceClickFilter(QObject):
    """Capture Qt click coordinates before interactor-style event processing."""

    def __init__(self, widget: QWidget, plotter, renderer: PreviewRenderer):
        super().__init__(widget)
        self.widget = widget
        self.plotter = plotter
        self.renderer = renderer
        self._press = None
        self._dragged = False
        widget.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        kind = event.type()
        if (
            kind == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self._press = event.position()
            self._dragged = False
        elif (
            kind in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease)
            and self._press is not None
        ):
            delta = event.position() - self._press
            threshold = theme_manager.palette.viewer.geometry.pick_drag_distance
            self._dragged |= delta.x() ** 2 + delta.y() ** 2 > threshold**2
            if (
                kind == QEvent.Type.MouseButtonRelease
                and event.button() == Qt.MouseButton.LeftButton
            ):
                self._press = None
                if not self._dragged:
                    position = event.position()
                    x, y = _qt_to_vtk_position(
                        position.x(),
                        position.y(),
                        (self.widget.width(), self.widget.height()),
                        self.plotter.render_window.GetSize(),
                    )
                    # Finish the normal camera interaction before picking.
                    QTimer.singleShot(0, self, lambda: self.renderer.pick_face(x, y))
        elif kind == QEvent.Type.Leave:
            self._press = None
        return False


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
        self._lbl_view = QLabel(tr("ui.widgets.viewer.view"))
        bar.addWidget(self._lbl_view)
        self.view_combo = QComboBox()
        self.view_combo.addItem(tr("ui.widgets.viewer.part"), "part")
        self.view_combo.addItem(tr("ui.widgets.viewer.assembly"), "assembly")
        self.view_combo.setCurrentIndex(1)
        self.view_combo.currentIndexChanged.connect(self._on_view_changed)
        bar.addWidget(self.view_combo)

        self._lbl_part = QLabel(tr("ui.widgets.viewer.part_2eacf781"))
        bar.addWidget(self._lbl_part)
        self.part_combo = QComboBox()
        self.part_combo.currentIndexChanged.connect(self._on_part_changed)
        bar.addWidget(self.part_combo)

        self._lbl_step = QLabel(tr("ui.widgets.viewer.step"))
        bar.addWidget(self._lbl_step)
        self.step_combo = QComboBox()
        self.step_combo.currentIndexChanged.connect(self._on_step_changed)
        bar.addWidget(self.step_combo)
        bar.addStretch(1)
        self._btn_reset = QPushButton(tr("ui.widgets.viewer.reset_view"))
        self._btn_reset.clicked.connect(self._reset_view)
        bar.addWidget(self._btn_reset)
        outer.addLayout(bar)

        section_bar = QHBoxLayout()
        self.section_enabled = QCheckBox(tr("ui.widgets.viewer.section"))
        section_bar.addWidget(self.section_enabled)
        self.section_axis = QComboBox()
        for axis in "XYZ":
            self.section_axis.addItem(axis)
        section_bar.addWidget(self.section_axis)
        self.section_slider = QSlider(Qt.Orientation.Horizontal)
        self.section_slider.setRange(0, 1000)
        self.section_slider.setValue(500)
        self.section_slider.setToolTip(tr("ui.widgets.viewer.section_position"))
        section_bar.addWidget(self.section_slider, 1)
        self.section_reverse = QCheckBox(tr("ui.widgets.viewer.section_reverse"))
        section_bar.addWidget(self.section_reverse)
        self.section_coordinate = QLabel()
        section_bar.addWidget(self.section_coordinate)
        outer.addLayout(section_bar)
        for control in (self.section_axis, self.section_slider, self.section_reverse):
            control.setEnabled(False)

        self.host = _PlotHost(self)
        outer.addWidget(self.host, 1)
        self._picked_face: FaceSelection | None = None
        self.face_info = QLabel(tr("ui.widgets.viewer.pick_face_hint"))
        self.face_info.setWordWrap(True)
        self.face_info.setTextFormat(Qt.TextFormat.PlainText)
        self.face_info.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        outer.addWidget(self.face_info)

        self._selected_step: int | None = None
        self._problem: ProblemDefinition | None = None
        self._language_pending = False
        self._theme_pending = False
        self._render_pending = False
        self._pending_reset_camera = False
        self.geometry = geometry or PreviewGeometry()
        self.loads = loads or LoadPreviewVisitor()
        self.renderer = PreviewRenderer(
            self.host.plotter,
            on_face_picked=self._show_picked_face,
            track_mouse_events=not isinstance(self.host.plotter, QWidget),
        )
        self._face_click_filter = (
            _FaceClickFilter(self.host.plotter, self.host.plotter, self.renderer)
            if isinstance(self.host.plotter, QWidget)
            else None
        )
        self.section_enabled.toggled.connect(self._section_changed)
        self.section_axis.currentIndexChanged.connect(self._section_changed)
        self.section_slider.valueChanged.connect(self._section_changed)
        self.section_reverse.toggled.connect(self._section_changed)
        self._sync_view_controls()

    def _section_changed(self, *_args) -> None:
        enabled = self.section_enabled.isChecked()
        for control in (self.section_axis, self.section_slider, self.section_reverse):
            control.setEnabled(enabled)
        self.renderer.set_section(
            enabled,
            self.section_axis.currentIndex(),
            self.section_slider.value() / self.section_slider.maximum(),
            self.section_reverse.isChecked(),
            render=self.isVisible(),
        )
        self._update_section_coordinate()

    def _update_section_coordinate(self) -> None:
        position = self.renderer.section_position
        self.section_coordinate.setText(
            ""
            if position is None
            else f"{self.section_axis.currentText()} = {position:.5g}"
        )

    def _show_picked_face(self, selection: FaceSelection | None) -> None:
        self._picked_face = selection
        if selection is None:
            text = tr("ui.widgets.viewer.pick_face_hint")
        else:
            text = tr(
                "ui.widgets.viewer.picked_face",
                part=selection.part_name,
                surfaces=", ".join(selection.surface_names),
            )
            if selection.instance_name is not None:
                text += tr(
                    "ui.widgets.viewer.picked_instance",
                    instance=selection.instance_name,
                )
        self.face_info.setText(text)

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
        self._lbl_view.setText(tr("ui.widgets.viewer.view"))
        self._lbl_part.setText(tr("ui.widgets.viewer.part_2eacf781"))
        self._lbl_step.setText(tr("ui.widgets.viewer.step"))
        self._btn_reset.setText(tr("ui.widgets.viewer.reset_view"))
        self.section_enabled.setText(tr("ui.widgets.viewer.section"))
        self.section_reverse.setText(tr("ui.widgets.viewer.section_reverse"))
        self.section_slider.setToolTip(tr("ui.widgets.viewer.section_position"))
        self._show_picked_face(self._picked_face)
        # Keep whichever load step is selected while re-localizing the combo.
        # Signals are blocked so a hidden viewer is not forced to re-render
        # (rendering a backgrounded viewport is what used to blacken the
        # observer's GL pages during a language switch).
        current_part = self.part_combo.currentData()
        self._sync_part_combo(current_part)
        current_view = self.view_combo.currentData()
        self.view_combo.blockSignals(True)
        self.view_combo.clear()
        self.view_combo.addItem(tr("ui.widgets.viewer.part"), "part")
        self.view_combo.addItem(tr("ui.widgets.viewer.assembly"), "assembly")
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

    def _sync_part_combo(self, selected: PartNode | None = None) -> None:
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
            self.step_combo.addItem(tr("ui.widgets.viewer.no_load_step"), -1)
            for step in range(n):
                self.step_combo.addItem(
                    tr("ui.widgets.viewer.step_value", value_0=step), step
                )
            selected = self.step_combo.findData(self._selected_step)
            self.step_combo.setCurrentIndex(
                selected if selected >= 0 else (1 if n else 0)
            )
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
        scene = self.geometry.build(
            self._problem, self.view_combo.currentData(), self.part_combo.currentData()
        )
        # Prepare geometry and loads before replacing any actors. Incomplete
        # definitions must not erase a working viewport during data preparation.
        loads = self._load_scene()
        self.renderer.draw_scene(scene)
        self._update_section_coordinate()
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
