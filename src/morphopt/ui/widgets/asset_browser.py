"""Definition asset list with a registered preview widget for each category."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit, QPushButton, QSplitter,
    QStackedWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..codegen.assets import DefinitionAsset, collect_python_assets
from ..i18n import tr
from ..model.problem import ProblemDefinition
from ..refresh import RefreshContext
from ..theme import theme_manager
from ..visualization.assets import geometry_asset_scene
from .observation_pages import PlotViewport
from .plot_style import add_orientation_axes
from .preview_renderer import PreviewRenderer


class AssetPreview(QWidget):
    """Implement set_asset to provide the display for another asset category."""

    def set_asset(self, asset: DefinitionAsset, problem: ProblemDefinition) -> None:
        raise NotImplementedError

    def apply_language(self) -> None:
        pass

    def apply_theme(self) -> None:
        pass


class GeometryAssetPreview(AssetPreview):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        header = QHBoxLayout()
        self.summary = QLabel()
        header.addWidget(self.summary, 1)
        self.reset_button = QPushButton()
        self.reset_button.clicked.connect(self._reset_camera)
        header.addWidget(self.reset_button)
        layout.addLayout(header)
        self.viewport = PlotViewport(self)
        layout.addWidget(self.viewport, 1)
        self.renderer = PreviewRenderer(self.viewport.plotter, track_mouse_events=False)
        self._counts = (0, 0)
        self.apply_language()

    def set_asset(self, asset: DefinitionAsset, problem: ProblemDefinition) -> None:
        scene = geometry_asset_scene(asset)
        self.renderer.draw_scene(scene)
        add_orientation_axes(self.viewport.plotter)
        self._counts = (
            sum(mesh.n_points for _, mesh, _ in scene.base_meshes),
            sum(mesh.n_cells for _, mesh, _ in scene.base_meshes),
        )
        self.apply_language()
        self._reset_camera()

    def _reset_camera(self) -> None:
        self.viewport.plotter.reset_camera()
        self.viewport.plotter.render()

    def apply_language(self) -> None:
        self.reset_button.setText(tr("ui.widgets.viewer.reset_view"))
        self.summary.setText(tr("ui.assets.mesh_counts", points=self._counts[0], cells=self._counts[1]))

    def apply_theme(self) -> None:
        self.viewport.apply_theme()


class MetadataAssetPreview(AssetPreview):
    """Display structured asset metadata as text using the application font."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.text = QPlainTextEdit(self)
        self.text.setReadOnly(True)
        layout.addWidget(self.text)

    def set_asset(self, asset: DefinitionAsset, problem: ProblemDefinition) -> None:
        self.text.setPlainText(asset.content.decode("utf-8"))


class AssetBrowser(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._problem: ProblemDefinition | None = None
        self._assets: dict[str, DefinitionAsset] = {}
        self._factories: dict[str, tuple[str, Callable[[QWidget], AssetPreview]]] = {}
        self._previews: dict[str, AssetPreview] = {}
        self._selected_signature = None
        self._layout_initialized = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        header = QHBoxLayout()
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setProperty("textRole", "muted")
        header.addWidget(self.hint, 1)
        self.reload_button = QPushButton()
        self.reload_button.clicked.connect(self._reload)
        header.addWidget(self.reload_button)
        layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter = splitter
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2):
            self.tree.header().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemSelectionChanged.connect(self._show_selected)
        splitter.addWidget(self.tree)
        details = QWidget()
        detail_layout = QVBoxLayout(details)
        detail_layout.setContentsMargins(*theme_manager.palette.layout.zero_margins)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.TextFormat.PlainText)
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail_layout.addWidget(self.info)
        self.stack = QStackedWidget()
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(self.message)
        detail_layout.addWidget(self.stack, 1)
        splitter.addWidget(details)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)
        self.register_preview("geometry", "ui.assets.geometry", GeometryAssetPreview)
        self.register_preview("metadata", "ui.assets.face_map", MetadataAssetPreview)
        self.apply_language()

    def register_preview(
        self, category: str, title_key: str,
        factory: Callable[[QWidget], AssetPreview],
    ) -> None:
        """Register a category's title and lazily constructed preview component."""
        self._factories[category] = (title_key, factory)

    def refresh_ui(self, context: RefreshContext) -> None:
        self._problem = context.problem
        if self.isVisible() and context.geometry_changed:
            self._reload()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reload()
        if not self._layout_initialized:
            self._splitter.setSizes([180, max(360, self.height() - 180)])
            self._layout_initialized = True

    def _reload(self) -> None:
        if self._problem is None:
            return
        current = self.tree.currentItem()
        selected = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        try:
            _, self._assets = collect_python_assets(self._problem)
        except Exception as exc:
            self.tree.clear()
            self.info.clear()
            self.message.setText(tr("ui.assets.load_failed", error=str(exc)))
            self.stack.setCurrentWidget(self.message)
            return
        groups = {}
        items = {}
        with QSignalBlocker(self.tree):
            self.tree.clear()
            for asset in self._assets.values():
                if asset.category not in groups:
                    title = (
                        tr(self._factories[asset.category][0])
                        if asset.category in self._factories else asset.category
                    )
                    group = QTreeWidgetItem(self.tree, [title])
                    group.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    group.setExpanded(True)
                    groups[asset.category] = group
                item = QTreeWidgetItem(groups[asset.category], [
                    asset.name, asset.format.upper(), f"{len(asset.content):,} B",
                ])
                item.setData(0, Qt.ItemDataRole.UserRole, asset.name)
                item.setToolTip(0, asset.relative_path)
                items[asset.name] = item
            if items:
                self.tree.setCurrentItem(items.get(selected, next(iter(items.values()))))
        self._show_selected()

    def _show_selected(self) -> None:
        current = self.tree.currentItem()
        name = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        if name is None:
            self._selected_signature = None
            self.info.clear()
            self.message.setText(tr("ui.assets.empty"))
            self.stack.setCurrentWidget(self.message)
            return
        asset = self._assets[name]
        self.info.setText(tr(
            "ui.assets.details", path=asset.relative_path,
            source=asset.source or tr("ui.assets.embedded"),
            references=", ".join(asset.references),
        ))
        if asset.category not in self._factories:
            self._selected_signature = None
            self.message.setText(tr("ui.assets.no_preview", category=asset.category))
            self.stack.setCurrentWidget(self.message)
            return
        signature = (
            id(self._problem), asset.name, asset.category, asset.format, asset.content,
            asset.node.to_dict(),
        )
        if signature == self._selected_signature:
            self.stack.setCurrentWidget(self._previews[asset.category])
            return
        try:
            if asset.category not in self._previews:
                preview = self._factories[asset.category][1](self.stack)
                self._previews[asset.category] = preview
                self.stack.addWidget(preview)
            preview = self._previews[asset.category]
            self.stack.setCurrentWidget(preview)
            preview.set_asset(asset, self._problem)
        except Exception as exc:
            self.message.setText(tr("ui.assets.preview_failed", error=str(exc)))
            self.stack.setCurrentWidget(self.message)
            self._selected_signature = None
        else:
            self._selected_signature = signature

    def apply_language(self) -> None:
        self.hint.setText(tr("ui.assets.hint"))
        self.reload_button.setText(tr("ui.assets.reload"))
        self.tree.setHeaderLabels([tr("ui.assets.name"), tr("ui.assets.format"), tr("ui.assets.size")])
        for preview in self._previews.values():
            preview.apply_language()
        if self.isVisible():
            self._reload()

    def apply_theme(self) -> None:
        for preview in self._previews.values():
            preview.apply_theme()
