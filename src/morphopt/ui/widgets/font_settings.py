"""Font preferences organized by interface location."""

from PySide6.QtCore import QSignalBlocker
from PySide6.QtGui import QFontDatabase, QFontInfo
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from ..theme.fonts import ROLES, font_manager


class FontSettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("ui.appearance.fonts"))
        self.resize(820, 460)
        outer = QVBoxLayout(self)
        hint = QLabel(tr("ui.appearance.window_hint"))
        hint.setWordWrap(True)
        hint.setProperty("textRole", "muted")
        outer.addWidget(hint)
        content = QHBoxLayout()
        self.categories = QListWidget()
        self.categories.setFixedWidth(180)
        self.categories.setSpacing(4)
        self._draft = {role: font_manager.snapshot(role) for role in ROLES}
        for role in ROLES:
            self.categories.addItem(tr("ui.appearance.role_" + role))
        content.addWidget(self.categories)
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        self.title = QLabel()
        self.title.setProperty("textRole", "sectionHeading")
        panel_layout.addWidget(self.title)
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setProperty("textRole", "muted")
        panel_layout.addWidget(self.description)

        form = QFormLayout()
        self.western = self._font_combo(QFontDatabase.WritingSystem.Any)
        self.chinese = self._font_combo(QFontDatabase.WritingSystem.SimplifiedChinese)
        self.style = QComboBox()
        self.size = QDoubleSpinBox()
        self.size.setRange(5, 100)
        self.size.setDecimals(1)
        self.size.setSuffix(" pt")
        self.size.setKeyboardTracking(False)
        form.addRow(tr("ui.appearance.western_label"), self.western)
        form.addRow(tr("ui.appearance.chinese_label"), self.chinese)
        form.addRow(tr("ui.appearance.style_label"), self.style)
        form.addRow(tr("ui.appearance.size_label"), self.size)
        panel_layout.addSpacing(10)
        panel_layout.addLayout(form)
        panel_layout.addSpacing(10)
        preview_label = QLabel(tr("ui.appearance.preview_title"))
        preview_label.setProperty("textRole", "muted")
        panel_layout.addWidget(preview_label)
        self.preview = QLabel()
        self.preview.setWordWrap(True)
        self.preview.setFrameShape(QFrame.Shape.StyledPanel)
        self.preview.setMargin(16)
        self.preview.setMinimumHeight(80)
        panel_layout.addWidget(self.preview)
        panel_layout.addStretch(1)
        reset_row = QHBoxLayout()
        reset_row.addStretch(1)
        reset = QPushButton(tr("ui.appearance.reset_font"))
        reset.clicked.connect(self._reset_current)
        reset_row.addWidget(reset)
        panel_layout.addLayout(reset_row)
        content.addWidget(panel, 1)
        outer.addLayout(content, 1)
        footer = QHBoxLayout()
        reset_all = QPushButton(tr("ui.appearance.reset_all"))
        reset_all.clicked.connect(self._reset_all)
        footer.addWidget(reset_all)
        footer.addStretch(1)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        apply_button = self.buttons.button(QDialogButtonBox.StandardButton.Apply)
        confirm_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        apply_button.setText(tr("ui.appearance.apply"))
        confirm_button.setText(tr("ui.appearance.confirm"))
        cancel_button.setText(tr("ui.appearance.cancel"))
        apply_button.clicked.connect(self._apply_draft)
        self.buttons.accepted.connect(self._commit)
        self.buttons.rejected.connect(self.reject)
        footer.addWidget(self.buttons)
        outer.addLayout(footer)

        self.categories.currentRowChanged.connect(self._select_role)
        self.western.activated.connect(lambda _index: self._set_family(False))
        self.chinese.activated.connect(lambda _index: self._set_family(True))
        self.style.activated.connect(self._set_style)
        self.size.valueChanged.connect(self._set_size)
        self.categories.setCurrentRow(0)

    @staticmethod
    def _font_combo(writing_system: QFontDatabase.WritingSystem) -> QComboBox:
        combo = QComboBox()
        combo.addItem(tr("ui.appearance.default_font"), "")
        for family in QFontDatabase.families(writing_system):
            if not family.startswith("MorphOpt Western "):
                combo.addItem(family, family)
        return combo

    def _role(self) -> str:
        return ROLES[self.categories.currentRow()]

    def _select_role(self, _index: int) -> None:
        role = self._role()
        self.title.setText(tr("ui.appearance.role_" + role))
        self.description.setText(tr("ui.appearance.description_" + role))
        self.preview.setText(tr("ui.appearance.preview_" + role))
        self._refresh(role)

    def _refresh(self, role: str) -> None:
        if self.categories.currentRow() < 0 or role != self._role():
            return
        font, chinese_family = self._draft[role]
        for combo, chinese in ((self.western, False), (self.chinese, True)):
            family = chinese_family if chinese else font.family()
            if (chinese and not chinese_family) or (
                not chinese
                and font.family() == font_manager.default_font(role).family()
            ):
                family = ""
            with QSignalBlocker(combo):
                index = combo.findData(family)
                if index < 0:
                    combo.addItem(family, family)
                    index = combo.count() - 1
                combo.setCurrentIndex(index)
        styles = QFontDatabase.styles(font.family())
        with QSignalBlocker(self.style):
            self.style.clear()
            self.style.addItems(styles)
            index = self.style.findText(font.styleName() or QFontInfo(font).styleName())
            if index < 0:
                index = self.style.findText(QFontDatabase.styleString(font))
            self.style.setCurrentIndex(max(index, 0))
        with QSignalBlocker(self.size):
            self.size.setValue(font.pointSizeF() if font.pointSizeF() > 0 else 10)
        self.preview.setFont(font_manager.compose(font, chinese_family))

    def _set_family(self, chinese: bool) -> None:
        combo = self.chinese if chinese else self.western
        role = self._role()
        western, chinese_family = self._draft[role]
        family = combo.currentData()
        if chinese:
            chinese_family = family
        elif family:
            western.setFamily(family)
        else:
            size = western.pointSizeF()
            western = font_manager.default_font(role)
            if size > 0:
                western.setPointSizeF(size)
        self._draft[role] = western, chinese_family
        self._refresh(role)

    def _set_style(self, _index: int) -> None:
        role = self._role()
        current, chinese = self._draft[role]
        font = QFontDatabase.font(
            current.family(), self.style.currentText(), current.pointSize()
        )
        if current.pointSizeF() > 0:
            font.setPointSizeF(current.pointSizeF())
        self._draft[role] = font, chinese
        self._refresh(role)

    def _set_size(self, size: float) -> None:
        role = self._role()
        font, chinese = self._draft[role]
        font.setPointSizeF(size)
        self._draft[role] = font, chinese
        self._refresh(role)

    def _reset_all(self) -> None:
        for role in ROLES:
            self._draft[role] = font_manager.default_font(role), ""
        self._refresh(self._role())

    def _reset_current(self) -> None:
        role = self._role()
        self._draft[role] = font_manager.default_font(role), ""
        self._refresh(role)

    def _apply_draft(self) -> None:
        for role, (western, chinese) in self._draft.items():
            if font_manager.snapshot(role) != (western, chinese):
                font_manager.set_preferences(role, western, chinese)

    def _commit(self) -> None:
        self._apply_draft()
        self.accept()
