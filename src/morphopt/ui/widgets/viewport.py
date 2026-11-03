"""Shared three-dimensional viewport, camera controls, and deferred rendering."""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QPushButton, QVBoxLayout, QWidget
from pyvistaqt import QtInteractor

from ..i18n import localization, tr
from ..theme import theme_manager
from ..theme.visualization import VisualizationSettings, visualization_manager
from ..visualization.rendering import apply_visualization, configure_plotter

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
    ) -> None:
        super().__init__(parent)
        self._settings_override = settings
        self._camera_initialized = False
        self._style_pending = False
        self._pending_scene: Callable[[QtInteractor], None] | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        layout.setSpacing(theme_manager.palette.layout.zero_spacing)
        toolbar = QHBoxLayout()
        self.views = QComboBox()
        self.views.activated.connect(self._select_view)
        toolbar.addWidget(self.views)
        toolbar.addStretch(1)
        self.fit_button = QPushButton()
        self.fit_button.clicked.connect(self.fit_view)
        toolbar.addWidget(self.fit_button)
        layout.addLayout(toolbar)
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
        return self._settings_override or visualization_manager.settings

    def set_style_override(self, settings: VisualizationSettings) -> None:
        """Preview a draft without modifying the application's saved settings."""
        self._settings_override = settings
        self.apply_theme()

    def _settings_changed(self) -> None:
        if self._settings_override is None:
            self.apply_theme()

    def apply_language(self, *_args) -> None:
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

    def _select_view(self, index: int) -> None:
        name = self.views.itemData(index)
        self.views.setCurrentIndex(0)
        if name is not None:
            self.set_view(name)

    def set_view(self, name: str) -> None:
        vector, up = VIEWS[name]
        self.plotter.view_vector(vector, viewup=up, render=False)
        self._camera_initialized = True
        self.plotter.render()
        self.viewChanged.emit()

    def fit_view(self) -> None:
        self.plotter.reset_camera()
        self.viewChanged.emit()

    def showEvent(self, event) -> None:
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
                self._rebuild_scene(build_scene)
            except Exception:
                self._pending_scene = build_scene
                logging.getLogger(__name__).exception("Viewport scene rebuild failed")
        else:
            self.plotter.render()

    def apply_theme(self) -> None:
        self._style_pending = True
        if self.isVisible():
            self._refresh_timer.start(0)

    def rebuild(self, build_scene: Callable[[QtInteractor], None]) -> None:
        self._pending_scene = build_scene
        if self.isVisible():
            self._refresh_timer.start(0)

    def _rebuild_scene(self, build_scene: Callable[[QtInteractor], None]) -> None:
        camera = self.plotter.camera.copy() if self._camera_initialized else None
        self.plotter.clear()
        configure_plotter(self.plotter, settings=self.settings)
        build_scene(self.plotter)
        apply_visualization(self.plotter, self.settings)
        if camera is None:
            self.plotter.view_isometric(render=False)
            self._camera_initialized = True
        else:
            self.plotter.camera = camera
        self.plotter.reset_camera_clipping_range()
        self.plotter.render()
