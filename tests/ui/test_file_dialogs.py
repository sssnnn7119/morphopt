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


@pytest.mark.parametrize('accepted', [False, True])
def test_open_file_selection_preserves_step_filter_and_cancel(monkeypatch, tmp_path, accepted):
    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    path = tmp_path / 'geometry.stp'
    path.write_text('STEP selection fixture')
    name_filter = tr('ui.files.step')

    def choose(dialog):
        assert dialog.testOption(QFileDialog.Option.DontUseNativeDialog)
        assert dialog.fileMode() is QFileDialog.FileMode.ExistingFile
        assert dialog.acceptMode() is QFileDialog.AcceptMode.AcceptOpen
        assert dialog.nameFilters() == [name_filter]
        assert dialog.labelText(QFileDialog.DialogLabel.Accept) == tr('ui.files.open')
        assert not dialog.findChild(QToolButton, 'toParentButton').icon().isNull()
        dialog.selectFile(str(path))
        return (QFileDialog.DialogCode.Accepted if accepted
                else QFileDialog.DialogCode.Rejected)

    monkeypatch.setattr(QFileDialog, 'exec', choose)
    try:
        assert file_dialogs.choose_open_file(parent, 'STEP', str(tmp_path), name_filter) == (
            str(path) if accepted else ''
        )
    finally:
        parent.deleteLater()
        app.processEvents()


def test_directory_selection_uses_shared_navigation_and_directory_mode(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    parent = QWidget()

    def choose(dialog):
        assert dialog.testOption(QFileDialog.Option.DontUseNativeDialog)
        assert dialog.fileMode() is QFileDialog.FileMode.Directory
        assert dialog.testOption(QFileDialog.Option.ShowDirsOnly)
        assert dialog.labelText(QFileDialog.DialogLabel.FileName) == tr('ui.files.directory')
        assert not dialog.findChild(QToolButton, 'toParentButton').icon().isNull()
        dialog.selectFile(str(tmp_path))
        return QFileDialog.DialogCode.Accepted

    monkeypatch.setattr(QFileDialog, 'exec', choose)
    try:
        assert file_dialogs.choose_directory(parent, 'Directory', str(tmp_path)) == str(tmp_path)
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
