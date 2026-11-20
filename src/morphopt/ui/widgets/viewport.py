"""Shared three-dimensional viewport, camera controls, and deferred rendering."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Hashable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import replace

import numpy as np
from PySide6.QtCore import QElapsedTimer, QEvent, QObject, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from pyvistaqt import QtInteractor
from vtkmodules.vtkRenderingCore import vtkActor, vtkActor2D

from ...constants import CONSTANT
from ..i18n import localization, tr
from ..theme import theme_manager
from ..theme.visualization import VisualizationSettings, visualization_manager
from ..visualization.rendering import (
    apply_visualization,
    configure_plotter,
    fit_camera_to_geometry,
)

VIEWS = {
    "isometric": ((1, 1, 1), (0, 0, 1)),
    "x": ((1, 0, 0), (0, 0, 1)),
    "-x": ((-1, 0, 0), (0, 0, 1)),
    "y": ((0, 1, 0), (0, 0, 1)),
    "-y": ((0, -1, 0), (0, 0, 1)),
    "z": ((0, 0, 1), (0, 1, 0)),
    "-z": ((0, 0, -1), (0, 1, 0)),
}


class PlotViewport(QWidget):
    """Keep one render window and its camera across scene and task changes."""

    viewChanged = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        settings: VisualizationSettings | None = None,
        controls: bool = True,
    ) -> None:
        """Initialize PlotViewport and its configuration state.

        Args:
            parent (QWidget | None): Parent Qt widget; None creates a top-level widget.
            settings (VisualizationSettings | None): Visualization preference snapshot; None uses
                the current global settings.
            controls (bool): Show the shared camera toolbar when True.
        """
        super().__init__(parent)
        self._settings_override = settings
        self._camera_initialized = False
        self._scene_has_geometry = False
        self._geometry_keys: frozenset[Hashable] = frozenset()
        self._style_pending = False
        self._pending_scene: Callable[[QtInteractor], None] | None = None
        self._pending_geometry_keys: frozenset[Hashable] = frozenset()
        self._flight_dialog: FirstPersonDialog | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        layout.setSpacing(theme_manager.palette.layout.zero_spacing)
        self.controls = QWidget(self)
        toolbar = QHBoxLayout(self.controls)
        toolbar.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self.views = QComboBox()
        self.views.activated.connect(self._select_view)
        toolbar.addWidget(self.views)
        toolbar.addStretch(1)
        self.flight_button = QPushButton()
        self.flight_button.clicked.connect(self.open_flight)
        toolbar.addWidget(self.flight_button)
        self.fit_button = QPushButton()
        self.fit_button.clicked.connect(self.fit_view)
        toolbar.addWidget(self.fit_button)
        layout.addWidget(self.controls)
        self.controls.setVisible(controls)
        self.plotter = QtInteractor(self, auto_update=False)
        layout.addWidget(self.plotter.interactor, 1)
        configure_plotter(self.plotter, settings=self.settings)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._refresh_visible_scene)
        visualization_manager.changed.connect(self._settings_changed)
        unsubscribe = localization.subscribe(self.apply_language)
        self.destroyed.connect(lambda *_args: unsubscribe())
        self.apply_language()

    @property
    def settings(self) -> VisualizationSettings:
        """Return settings.

        Returns:
            VisualizationSettings: Settings.
        """
        return self._settings_override or visualization_manager.settings

    def set_style_override(self, settings: VisualizationSettings) -> None:
        """Preview a draft without modifying the application's saved settings.

        Args:
            settings (VisualizationSettings): Visualization preference snapshot; None uses the
                current global settings.
        """
        self._settings_override = settings
        self.apply_theme()

    def _settings_changed(self) -> None:
        if self._settings_override is None:
            self.apply_theme()

    def apply_language(self, *_args) -> None:
        """Update visible labels using the active application locale.

        Args:
            *_args: Additional positional arguments accepted by the shared interface.
        """
        self.views.blockSignals(True)
        self.views.clear()
        self.views.addItem(tr("ui.visualization.choose_view"), None)
        for name in VIEWS:
            label = name.upper().replace("-", "−")
            if name == "isometric":
                label = tr("ui.visualization.isometric")
            elif not name.startswith("-"):
                label = "+" + label
            self.views.addItem(label, name)
        self.views.blockSignals(False)
        self.views.setToolTip(tr("ui.visualization.view_hint"))
        self.fit_button.setText(tr("ui.visualization.fit"))
        self.flight_button.setText(tr("ui.visualization.flythrough"))
        self.flight_button.setToolTip(tr("ui.visualization.flythrough_hint"))

    def _select_view(self, index: int) -> None:
        name = self.views.itemData(index)
        self.views.setCurrentIndex(0)
        if name is not None:
            self.set_view(name)

    def set_view(self, name: str) -> None:
        """Set view.

        Args:
            name (str): Name identifying the item in its owning collection.
        """
        vector, up = VIEWS[name]
        self.plotter.view_vector(vector, viewup=up, render=False)
        self._camera_changed()

    def fit_view(self) -> None:
        """Fit the current viewing direction to the model and viewport aspect ratio."""
        fit_camera_to_geometry(self.plotter)
        self._camera_changed()

    def open_flight(self) -> None:
        """Open one independent perspective snapshot of the current viewport."""
        if self._flight_dialog is None:
            self._flight_dialog = FirstPersonDialog(self)
            self._flight_dialog.finished.connect(self._flight_finished)
        self._flight_dialog.show()
        self._flight_dialog.raise_()
        self._flight_dialog.activateWindow()

    def _flight_finished(self, _result: int) -> None:
        self._flight_dialog = None

    def closeEvent(self, event: QCloseEvent) -> None:
        """Release owned view resources when the widget closes.

        Args:
            event (QCloseEvent): Qt event delivered to this widget or event filter.
        """
        if self._flight_dialog is not None:
            self._flight_dialog.reject()
        super().closeEvent(event)

    def _camera_changed(self) -> None:
        self._camera_initialized = True
        self.plotter.reset_camera_clipping_range()
        self.plotter.render()
        self.viewChanged.emit()

    def showEvent(self, event) -> None:
        """Refresh deferred content when the widget becomes visible.

        Args:
            event: Qt event delivered to this widget or event filter.
        """
        super().showEvent(event)
        self._refresh_timer.start(0)

    def _refresh_visible_scene(self) -> None:
        if not self.isVisible():
            return
        if self._style_pending:
            self._style_pending = False
            parallel = bool(self.plotter.camera.parallel_projection)
            configure_plotter(self.plotter, settings=self.settings)
            apply_visualization(self.plotter, self.settings)
            if parallel != self.settings.parallel_projection:
                self.viewChanged.emit()
        build_scene = self._pending_scene
        self._pending_scene = None
        if build_scene is not None:
            try:
                self._rebuild_scene(build_scene, self._pending_geometry_keys)
            except Exception:
                self._pending_scene = build_scene
                logging.getLogger(__name__).exception("Viewport scene rebuild failed")
        else:
            self.plotter.render()

    def apply_theme(self) -> None:
        """Apply the active theme to this view and its visualization resources."""
        self._style_pending = True
        if self.isVisible():
            self._refresh_timer.start(0)

    def rebuild(
        self,
        build_scene: Callable[[QtInteractor], None],
        *,
        geometry_keys: Iterable[Hashable] = (),
    ) -> None:
        """Return rebuild.

        Args:
            build_scene (Callable[[QtInteractor], None]): Callback adding prepared actors to the
                supplied plotter.
            geometry_keys (Iterable[Hashable]): Stable geometry identities used to distinguish
                additions from redraws.
        """
        self._pending_scene = build_scene
        self._pending_geometry_keys = frozenset(geometry_keys)
        if self.isVisible():
            self._refresh_timer.start(0)

    def _rebuild_scene(
        self,
        build_scene: Callable[[QtInteractor], None],
        geometry_keys: Iterable[Hashable],
    ) -> None:
        with self.scene_update(geometry_keys=geometry_keys):
            self.plotter.clear()
            configure_plotter(self.plotter, settings=self.settings)
            build_scene(self.plotter)
            apply_visualization(self.plotter, self.settings)

    @contextmanager
    def scene_update(
        self,
        *,
        reset_camera: bool = False,
        has_geometry: bool | None = None,
        geometry_keys: Iterable[Hashable] = (),
    ) -> Iterator[None]:
        """Preserve camera state while replacing scene actors and fit newly introduced geometry.

        Stable geometry keys distinguish additions from redraws and parameter edits. Removing
        geometry does not force a refit. A fit retains viewing direction unless an explicit camera
        reset was requested.

        Args:
            reset_camera (bool): Reset the camera orientation and fit the geometry when True.
            has_geometry (bool | None): Whether the scene contains geometry; None determines this
                from visible bounds.
            geometry_keys (Iterable[Hashable]): Stable geometry identities used to distinguish
                additions from redraws.

        Yields:
            None: The caller may add or replace scene actors inside the context. On exit, update clipping, render the scene, and emit viewChanged when fitting occurred.
        """
        camera = self.plotter.camera.copy()
        keys = frozenset(geometry_keys)
        yield
        if has_geometry is None:
            bounds = self.plotter.renderer.ComputeVisiblePropBounds()
            has_geometry = all(
                math.isfinite(low) and math.isfinite(high) and low <= high
                for low, high in zip(bounds[::2], bounds[1::2])
            )
        fit = has_geometry and (
            reset_camera
            or not self._scene_has_geometry
            or not self._camera_initialized
            or not keys.issubset(self._geometry_keys)
        )
        if reset_camera or not self._camera_initialized:
            self.plotter.view_isometric(render=False)
        else:
            self.plotter.camera = camera
        if fit:
            self.plotter.reset_camera(render=False)
        self._camera_initialized |= has_geometry
        self._scene_has_geometry = has_geometry
        self._geometry_keys = keys if has_geometry else frozenset()
        self.plotter.reset_camera_clipping_range()
        self.plotter.render()
        if fit:
            self.viewChanged.emit()


class FirstPersonDialog(QDialog):
    """Display an independent perspective snapshot with first-person keyboard and held-button mouse
    control.

    WASD translates in the XY plane using the current heading; Q/E changes height. Left-button
    dragging changes yaw and pitch without roll. Releasing the button stops mouse look, and
    losing focus clears all movement input. Closing the dialog releases its render window.
    """

    _MOVEMENT_KEYS = {
        Qt.Key.Key_W,
        Qt.Key.Key_S,
        Qt.Key.Key_A,
        Qt.Key.Key_D,
        Qt.Key.Key_Q,
        Qt.Key.Key_E,
    }

    def __init__(self, source: PlotViewport) -> None:
        """Initialize FirstPersonDialog and its configuration state.

        Args:
            source (PlotViewport): Source object, path, or metadata from which the operation reads
                its input.
        """
        super().__init__(source)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(tr("ui.visualization.flythrough_title"))
        self.resize(*theme_manager.palette.layout.widgets.flythrough_size)
        layout = QVBoxLayout(self)
        self.viewport = PlotViewport(
            self,
            settings=replace(source.settings, parallel_projection=False),
            controls=False,
        )
        layout.addWidget(self.viewport, 1)
        footer = QHBoxLayout()
        hint = QLabel(tr("ui.visualization.flythrough_keys"))
        hint.setWordWrap(True)
        footer.addWidget(hint, 1)
        reset = QPushButton(tr("ui.visualization.flythrough_reset"))
        reset.clicked.connect(self.reset_view)
        footer.addWidget(reset)
        close = QPushButton(tr("ui.common.close"))
        close.clicked.connect(self.reject)
        footer.addWidget(close)
        layout.addLayout(footer)

        # Copy view props, including raw VTK scalar bars. The independent
        # renderer and camera never modify the originating viewport.
        props = source.plotter.renderer.GetViewProps()
        props.InitTraversal()
        for _ in range(props.GetNumberOfItems()):
            original = props.GetNextProp()
            actor = original.NewInstance()
            actor.ShallowCopy(original)
            # Each OpenGL window owns its mapper resources; share only the
            # underlying mesh data, never a mapper already used by another window.
            if (
                isinstance(original, (vtkActor, vtkActor2D))
                and original.GetMapper() is not None
            ):
                original_mapper = original.GetMapper()
                mapper = original_mapper.NewInstance()
                mapper.ShallowCopy(original_mapper)
                if original_mapper.GetNumberOfInputPorts():
                    mapper.SetInputConnection(original_mapper.GetInputConnection(0, 0))
                actor.SetMapper(mapper)
            self.viewport.plotter.renderer.AddViewProp(actor)
        camera = source.plotter.camera.copy()
        camera.parallel_projection = False
        self.viewport.plotter.camera = camera
        direction = camera.direction
        self._yaw = math.atan2(direction[1], direction[0])
        limit = math.radians(CONSTANT.UI.CAMERA.PITCH_LIMIT_DEGREES)
        self._pitch = float(np.clip(math.asin(direction[2]), -limit, limit))
        self._focus_distance = camera.distance
        self._home = (tuple(camera.position), self._yaw, self._pitch)
        extent = (
            source.plotter.length
            or theme_manager.palette.viewer.scene_fallback_diagonal
        )
        self._speed = extent * CONSTANT.UI.CAMERA.MOVEMENT_SPEED_RATIO
        self._pressed: set[int] = set()
        self._look_position: QPointF | None = None
        self._input_widget = self.viewport.plotter.interactor
        self._input_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._input_widget.setMouseTracking(True)
        self._clock = QElapsedTimer()
        self._movement = QTimer(self)
        self._movement.setInterval(CONSTANT.UI.CAMERA.FRAME_INTERVAL_MS)
        self._movement.timeout.connect(self._tick)
        self._input_widget.installEventFilter(self)
        self.installEventFilter(self)
        self._apply_pose()

    def _forward(self) -> np.ndarray:
        return np.array(
            [
                math.cos(self._pitch) * math.cos(self._yaw),
                math.cos(self._pitch) * math.sin(self._yaw),
                math.sin(self._pitch),
            ]
        )

    def _apply_pose(self) -> None:
        camera = self.viewport.plotter.camera
        camera.focal_point = (
            np.array(camera.position) + self._focus_distance * self._forward()
        )
        camera.up = (0, 0, 1)
        self.viewport.plotter.reset_camera_clipping_range()
        self.viewport.plotter.render()

    def _advance(self, seconds: float) -> None:
        """Advance keyboard translation using heading-only horizontal directions.

        Normalize combined movement so diagonal travel is not faster. WASD leaves Z unchanged, Q/E
        controls vertical movement, and Shift applies the configured speed multiplier. Pitch affects
        the viewing direction but not horizontal translation.

        Args:
            seconds (float): Elapsed movement time in seconds.
        """
        forward = np.array([math.cos(self._yaw), math.sin(self._yaw), 0.0])
        right = np.cross(forward, [0, 0, 1])
        keys = self._pressed
        velocity = (
            (int(Qt.Key.Key_W in keys) - int(Qt.Key.Key_S in keys)) * forward
            + (int(Qt.Key.Key_D in keys) - int(Qt.Key.Key_A in keys)) * right
            + np.array([0, 0, int(Qt.Key.Key_E in keys) - int(Qt.Key.Key_Q in keys)])
        )
        length = np.linalg.norm(velocity)
        if length:
            speed = self._speed * (
                CONSTANT.UI.CAMERA.FAST_MULTIPLIER if Qt.Key.Key_Shift in keys else 1
            )
            camera = self.viewport.plotter.camera
            camera.position = (
                np.array(camera.position) + seconds * speed * velocity / length
            )
            self._apply_pose()

    def _tick(self) -> None:
        seconds = min(
            self._clock.restart() / 1000, CONSTANT.UI.CAMERA.MAX_FRAME_SECONDS
        )
        self._advance(seconds)

    def _stop_controls(self) -> None:
        self._pressed.clear()
        self._movement.stop()
        self._look_position = None
        self._input_widget.unsetCursor()

    def reset_view(self) -> None:
        """Reset view."""
        self._stop_controls()
        position, self._yaw, self._pitch = self._home
        self.viewport.plotter.camera.position = position
        self._apply_pose()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Handle relevant input events before the receiving Qt object processes them.

        Args:
            watched (QObject): Qt object receiving the filtered event.
            event (QEvent): Qt event delivered to this widget or event filter.

        Returns:
            bool: Handle relevant input events before the receiving Qt object processes them.
        """
        kind = event.type()
        if kind in (
            QEvent.Type.FocusOut,
            QEvent.Type.WindowDeactivate,
            QEvent.Type.Hide,
        ):
            self._stop_controls()
        if watched is self._input_widget:
            if kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
                key = event.key()
                if key in self._MOVEMENT_KEYS or key == Qt.Key.Key_Shift:
                    if not event.isAutoRepeat():
                        if kind == QEvent.Type.KeyPress:
                            self._pressed.add(key)
                        else:
                            self._pressed.discard(key)
                        if self._pressed & self._MOVEMENT_KEYS:
                            if not self._movement.isActive():
                                self._clock.start()
                                self._movement.start()
                        else:
                            self._movement.stop()
                    return True
                if kind == QEvent.Type.KeyPress and key in (
                    Qt.Key.Key_R,
                    Qt.Key.Key_Escape,
                ):
                    self.reset_view() if key == Qt.Key.Key_R else self.reject()
                return True
            if kind == QEvent.Type.MouseButtonPress:
                self._input_widget.setFocus()
                if event.button() == Qt.MouseButton.LeftButton:
                    self._look_position = event.position()
                    self._input_widget.setCursor(Qt.CursorShape.ClosedHandCursor)
                return True
            if kind == QEvent.Type.MouseMove:
                if self._look_position is not None:
                    delta = event.position() - self._look_position
                    self._look_position = event.position()
                    sensitivity = math.radians(
                        CONSTANT.UI.CAMERA.MOUSE_DEGREES_PER_PIXEL
                    )
                    self._yaw -= delta.x() * sensitivity
                    limit = math.radians(CONSTANT.UI.CAMERA.PITCH_LIMIT_DEGREES)
                    self._pitch = float(
                        np.clip(self._pitch - delta.y() * sensitivity, -limit, limit)
                    )
                    self._apply_pose()
                return True
            if kind == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._look_position = None
                    self._input_widget.unsetCursor()
                return True
            if kind == QEvent.Type.Wheel:
                return True
        return super().eventFilter(watched, event)

    def showEvent(self, event) -> None:
        """Refresh deferred content when the widget becomes visible.

        Args:
            event: Qt event delivered to this widget or event filter.
        """
        super().showEvent(event)
        self._input_widget.setFocus()

    def done(self, result: int) -> None:
        """Return done.

        Args:
            result (int): Finite-element solution or completed operation result.
        """
        self._stop_controls()
        self.viewport.plotter.close()
        super().done(result)
