"""Shared file and directory selectors with localized labels and navigation icons."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QDir, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFileDialog, QMessageBox, QToolButton, QWidget

from ..i18n import tr
from ..theme import theme_manager


def confirm_overwrite(
    parent: QWidget,
    path: Path,
    *,
    message_key: str = "ui.mainwindow.overwrite_existing_file_value",
) -> bool:
    """Ask for overwrite confirmation using the active UI language."""
    message_box = QMessageBox(parent)
    message_box.setIcon(QMessageBox.Icon.Warning)
    message_box.setWindowTitle(tr("ui.mainwindow.overwrite_confirmation"))
    message_box.setText(tr(message_key, value_0=path.name))
    replace_button = message_box.addButton(
        tr("ui.mainwindow.overwrite_yes"), QMessageBox.ButtonRole.YesRole
    )
    cancel_button = message_box.addButton(
        tr("ui.mainwindow.overwrite_no"), QMessageBox.ButtonRole.NoRole
    )
    message_box.setDefaultButton(cancel_button)
    message_box.setEscapeButton(cancel_button)
    message_box.exec()
    return message_box.clickedButton() is replace_button


def set_file_dialog_icons(dialog: QFileDialog) -> None:
    """Draw visible navigation icons instead of relying on the desktop theme."""
    icons = {
        "backButton": "back",
        "forwardButton": "forward",
        "toParentButton": "up",
        "newFolderButton": "new_folder",
        "listModeButton": "list",
        "detailModeButton": "details",
    }
    for button in dialog.findChildren(QToolButton):
        name = icons.get(button.objectName())
        if name is None:
            continue

        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(
            QPen(
                QColor(theme_manager.palette.text),
                2.0,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if name == "back":
            painter.drawLine(15, 5, 8, 12)
            painter.drawLine(8, 12, 15, 19)
            painter.drawLine(8, 12, 21, 12)
        elif name == "forward":
            painter.drawLine(9, 5, 16, 12)
            painter.drawLine(16, 12, 9, 19)
            painter.drawLine(3, 12, 16, 12)
        elif name == "up":
            painter.drawLine(12, 20, 12, 7)
            painter.drawLine(7, 12, 12, 7)
            painter.drawLine(12, 7, 17, 12)
        elif name in {"new_folder", "list", "details"}:
            if name == "new_folder":
                painter.drawLine(3, 7, 9, 7)
                painter.drawLine(9, 7, 11, 10)
                painter.drawLine(11, 10, 21, 10)
                painter.drawLine(21, 10, 21, 19)
                painter.drawLine(21, 19, 3, 19)
                painter.drawLine(3, 19, 3, 7)
                painter.drawLine(12, 12, 12, 17)
                painter.drawLine(9, 14, 15, 14)
            elif name == "list":
                for y in (6, 12, 18):
                    painter.drawEllipse(3, y - 1, 2, 2)
                    painter.drawLine(9, y, 21, y)
            else:
                painter.drawRect(3, 4, 18, 16)
                painter.drawLine(3, 10, 21, 10)
                painter.drawLine(3, 15, 21, 15)
                painter.drawLine(9, 4, 9, 20)
        painter.end()
        button.setIcon(QIcon(pixmap))
        button.setIconSize(QSize(*theme_manager.palette.layout.toolbar_icon_size))
        button.setProperty("buttonLayout", "navigation")
        button.style().unpolish(button)
        button.style().polish(button)


def create_file_dialog(
    parent: QWidget, title: str, directory: str, *, save: bool
) -> QFileDialog:
    dialog = QFileDialog(parent, title, directory)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setOption(QFileDialog.Option.DontConfirmOverwrite, save)
    dialog.setAcceptMode(
        QFileDialog.AcceptMode.AcceptSave if save else QFileDialog.AcceptMode.AcceptOpen
    )
    dialog.setFileMode(
        QFileDialog.FileMode.AnyFile if save else QFileDialog.FileMode.ExistingFile
    )
    dialog.setFilter(
        QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot
    )
    for label, key in (
        (QFileDialog.DialogLabel.LookIn, "look_in"),
        (QFileDialog.DialogLabel.FileName, "file_name"),
        (QFileDialog.DialogLabel.FileType, "file_type"),
        (QFileDialog.DialogLabel.Accept, "save" if save else "open"),
        (QFileDialog.DialogLabel.Reject, "cancel"),
    ):
        dialog.setLabelText(label, tr("ui.files." + key))
    set_file_dialog_icons(dialog)
    QTimer.singleShot(0, dialog, lambda: set_file_dialog_icons(dialog))
    return dialog


def choose_open_file(
    parent: QWidget, title: str, directory: str, name_filter: str
) -> str:
    """Choose one existing file with the shared appearance and file filters."""
    dialog = create_file_dialog(parent, title, directory, save=False)
    dialog.setNameFilter(name_filter)
    if dialog.exec() != QFileDialog.DialogCode.Accepted:
        return ""
    selected = dialog.selectedFiles()
    return selected[0] if selected else ""


def choose_directory(parent: QWidget, title: str, directory: str) -> str:
    """Choose a directory with the shared icons, labels and theme."""
    dialog = create_file_dialog(parent, title, directory, save=False)
    dialog.setFileMode(QFileDialog.FileMode.Directory)
    dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
    dialog.setLabelText(QFileDialog.DialogLabel.FileName, tr("ui.files.directory"))
    if dialog.exec() != QFileDialog.DialogCode.Accepted:
        return ""
    selected = dialog.selectedFiles()
    return selected[0] if selected else ""


def choose_save_directory(
    parent: QWidget, title: str, directory: str, name: str
) -> str:
    """Choose a new or existing output directory by entering its name."""
    dialog = create_file_dialog(parent, title, directory, save=True)
    dialog.setFilter(QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot)
    dialog.setLabelText(QFileDialog.DialogLabel.FileName, tr("ui.files.directory_name"))
    dialog.selectFile(name)
    if dialog.exec() != QFileDialog.DialogCode.Accepted:
        return ""
    selected = dialog.selectedFiles()
    return selected[0] if selected else ""


@dataclass(frozen=True)
class SaveFileSelection:
    path: Path
    format: str
    overwrite: bool = False


def choose_save_file(
    parent: QWidget, title: str, directory: str, name: str, formats: dict[str, str]
) -> SaveFileSelection | None:
    """Choose a filename and format in one dialog; approve replacement exactly once."""
    dialog = create_file_dialog(parent, title, directory, save=True)
    filters = {label: key for key, label in formats.items()}
    dialog.setNameFilters(list(filters))
    first = next(iter(formats))
    dialog.setDefaultSuffix(first)
    dialog.selectFile(name + "." + first)

    def change_format(label: str) -> None:
        suffix = filters[label]
        dialog.setDefaultSuffix(suffix)
        selected = dialog.selectedFiles()
        if selected:
            path = Path(selected[0])
            if path.suffix.lstrip(".").lower() in formats:
                dialog.selectFile(path.with_suffix("." + suffix).name)

    dialog.filterSelected.connect(change_format)
    if dialog.exec() != QFileDialog.DialogCode.Accepted or not dialog.selectedFiles():
        return None
    key = filters[dialog.selectedNameFilter()]
    path = Path(dialog.selectedFiles()[0])
    if path.suffix.lower() != "." + key:
        path = (
            path.with_suffix("." + key)
            if path.suffix.lstrip(".").lower() in formats
            else Path(str(path) + "." + key)
        )
    exists = path.exists()
    if exists and not confirm_overwrite(parent, path):
        return None
    return SaveFileSelection(path, key, exists)
