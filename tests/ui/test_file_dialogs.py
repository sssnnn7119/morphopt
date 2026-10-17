import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QToolButton, QWidget

from morphopt.ui.i18n import tr
from morphopt.ui.widgets import file_dialogs


def test_file_dialog_uses_shared_labels_file_filters_and_visible_icons(tmp_path):
    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    dialog = file_dialogs.create_file_dialog(parent, 'Save', str(tmp_path), save=True)
    try:
        dialog.setNameFilters([tr('ui.files.csv'), tr('ui.files.npz')])
        file_dialogs.set_file_dialog_icons(dialog)
        assert dialog.fileMode() is QFileDialog.FileMode.AnyFile
        assert dialog.acceptMode() is QFileDialog.AcceptMode.AcceptSave
        assert dialog.labelText(QFileDialog.DialogLabel.FileName) == tr('ui.files.file_name')
        assert dialog.nameFilters() == [tr('ui.files.csv'), tr('ui.files.npz')]
        navigation = [button for button in dialog.findChildren(QToolButton)
                      if button.objectName() in ('backButton', 'forwardButton', 'toParentButton',
                                                 'newFolderButton', 'listModeButton', 'detailModeButton')]
        assert len(navigation) == 6
        assert all(not button.icon().isNull() for button in navigation)
    finally:
        parent.deleteLater()
        app.processEvents()


@pytest.mark.parametrize('format,typed,expected', [
    ('csv', 'my nodal result', 'my nodal result.csv'),
    ('npz', 'my element result.csv', 'my element result.npz'),
])
def test_save_file_selection_uses_chosen_name_and_filter(monkeypatch, tmp_path, format, typed, expected):
    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    formats = {key: tr('ui.files.' + key) for key in ('csv', 'npz')}
    def accept(dialog):
        assert dialog.selectedNameFilter() == formats['csv']
        dialog.selectNameFilter(formats[format])
        dialog.filterSelected.emit(formats[format])
        assert dialog.defaultSuffix() == format
        dialog.selectFile(typed)
        return QFileDialog.DialogCode.Accepted
    monkeypatch.setattr(QFileDialog, 'exec', accept)
    try:
        choice = file_dialogs.choose_save_file(parent, 'Save', str(tmp_path), 'default', formats)
        assert choice == file_dialogs.SaveFileSelection(tmp_path / expected, format)
    finally:
        parent.deleteLater()
        app.processEvents()


@pytest.mark.parametrize('approved', [False, True])
def test_save_file_selection_confirms_existing_file(monkeypatch, tmp_path, approved):
    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    path = tmp_path / 'existing.csv'
    path.write_text('keep me')
    def accept(dialog):
        dialog.selectFile(path.name)
        return QFileDialog.DialogCode.Accepted
    asked = []
    monkeypatch.setattr(QFileDialog, 'exec', accept)
    monkeypatch.setattr(file_dialogs, 'confirm_overwrite', lambda owner, chosen: asked.append(chosen) or approved)
    try:
        choice = file_dialogs.choose_save_file(parent, 'Save', str(tmp_path), 'default', {'csv': tr('ui.files.csv')})
        assert asked == [path]
        assert path.read_text() == 'keep me'
        assert choice == (file_dialogs.SaveFileSelection(path, 'csv', True) if approved else None)
    finally:
        parent.deleteLater()
        app.processEvents()
