"""Preview and apply global three-dimensional visualization preferences."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from pyvista.plotting.plotter import BasePlotter

from ..i18n import tr
from ..theme import theme_manager
from ..theme.visualization import VisualizationSettings, visualization_manager
from ..visualization.rendering import add_orientation_axes
from .viewport import PlotViewport


class VisualizationSettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("ui.visualization.title"))
        self.resize(880, 500)
        layout = QVBoxLayout(self)
        hint = QLabel(tr("ui.visualization.hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        content = QHBoxLayout()
        form = QFormLayout()
        self.projection = QComboBox()
        self.projection.addItem(tr("ui.visualization.parallel"), True)
        self.projection.addItem(tr("ui.visualization.perspective"), False)
        form.addRow(tr("ui.visualization.projection"), self.projection)
        self.values: dict[str, QDoubleSpinBox] = {}
        for key, maximum, step in (
            ("light_intensity", 3, 0.1),
            ("ambient", 1, 0.05),
            ("diffuse", 1, 0.05),
            ("specular", 1, 0.05),
            ("specular_power", 128, 1),
        ):
            editor = QDoubleSpinBox()
            editor.setRange(1 if key == "specular_power" else 0, maximum)
            editor.setDecimals(0 if key == "specular_power" else 2)
            editor.setSingleStep(step)
            editor.setKeyboardTracking(False)
            editor.setToolTip(tr("ui.visualization." + key + "_hint"))
            self.values[key] = editor
            form.addRow(tr("ui.visualization." + key), editor)
        self.smooth = QCheckBox(tr("ui.visualization.smooth_shading"))
        form.addRow(self.smooth)
        controls = QWidget()
        controls.setMinimumWidth(250)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 12, 0)
        controls_layout.addLayout(form)
        controls_layout.addStretch(1)
        content.addWidget(controls)
        self.preview = PlotViewport(self, settings=visualization_manager.settings)
        self.preview.setMinimumSize(350, 300)
        content.addWidget(self.preview, 1)
        layout.addLayout(content, 1)
        footer = QHBoxLayout()
        reset = QPushButton(tr("ui.visualization.reset"))
        reset.clicked.connect(lambda: self._load(VisualizationSettings()))
        footer.addWidget(reset)
        footer.addStretch(1)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        for button, key in (
            (QDialogButtonBox.StandardButton.Apply, "apply"),
            (QDialogButtonBox.StandardButton.Ok, "confirm"),
            (QDialogButtonBox.StandardButton.Cancel, "cancel"),
        ):
            self.buttons.button(button).setText(tr("ui.appearance." + key))
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self._apply
        )
        self.buttons.accepted.connect(self._confirm)
        self.buttons.rejected.connect(self.reject)
        footer.addWidget(self.buttons)
        layout.addLayout(footer)
        self.projection.currentIndexChanged.connect(self._update_preview)
        self.smooth.toggled.connect(self._update_preview)
        for editor in self.values.values():
            editor.valueChanged.connect(self._update_preview)
        self._load(visualization_manager.settings)
        self.preview.rebuild(self._build_preview)

    def _draft(self) -> VisualizationSettings:
        return VisualizationSettings(
            parallel_projection=self.projection.currentData(),
            smooth_shading=self.smooth.isChecked(),
            **{key: editor.value() for key, editor in self.values.items()},
        )

    def _load(self, settings: VisualizationSettings) -> None:
        with QSignalBlocker(self.projection), QSignalBlocker(self.smooth):
            self.projection.setCurrentIndex(
                self.projection.findData(settings.parallel_projection)
            )
            self.smooth.setChecked(settings.smooth_shading)
        for key, editor in self.values.items():
            with QSignalBlocker(editor):
                editor.setValue(getattr(settings, key))
        self._update_preview()

    def _update_preview(self, *_args) -> None:
        self.preview.set_style_override(self._draft())

    def _apply(self) -> None:
        visualization_manager.apply(self._draft())

    def _confirm(self) -> None:
        self._apply()
        self.accept()

    @staticmethod
    def _build_preview(plotter: BasePlotter) -> None:
        import pyvista as pv

        colors = theme_manager.palette.viewer.geometry.instance_colors
        plotter.add_mesh(
            pv.Sphere(center=(-1, 0, 0)), color=colors[0], smooth_shading=True
        )
        plotter.add_mesh(
            pv.Cylinder(
                center=(0.7, 0, 0), radius=0.5, height=1.5, direction=(0, 0, 1)
            ),
            color=colors[1],
            smooth_shading=True,
        )
        add_orientation_axes(plotter)

    def done(self, result: int) -> None:
        self.preview.plotter.close()
        super().done(result)
