"""Wheel gestures scroll forms without silently editing their controls."""

import subprocess
import sys

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDial, QDoubleSpinBox, QFontComboBox,
    QPushButton, QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from morphopt.ui.app import create_application
from morphopt.ui.i18n import localization, set_locale


@pytest.fixture(scope="module")
def app():
    previous = localization.locale
    application = create_application([])
    set_locale(previous)
    return application


def send_wheel(app, widget, *, pixels=False):
    position = widget.rect().center()
    event = QWheelEvent(
        QPointF(position), QPointF(widget.mapToGlobal(position)),
        QPoint(0, -30) if pixels else QPoint(), QPoint(0, -120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate if pixels else Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    app.sendEvent(widget, event)


@pytest.mark.parametrize("kind", ["combo", "editable_combo", "font", "integer", "decimal", "slider", "dial", "date"])
@pytest.mark.parametrize("focused", [False, True])
def test_wheel_preserves_focused_and_unfocused_values_and_scrolls_page(app, kind, focused):
    area = QScrollArea()
    content = QWidget()
    layout = QVBoxLayout(content)
    if kind in ("combo", "editable_combo"):
        control = QComboBox()
        control.addItems(["First", "Second", "Third"])
        control.setCurrentIndex(1)
        control.setEditable(kind == "editable_combo")
        value = control.currentText
        changed = control.currentIndexChanged
    elif kind == "font":
        control = QFontComboBox()
        value = lambda: control.currentFont().family()
        changed = control.currentFontChanged
    elif kind == "date":
        control = QDateEdit()
        value = control.date
        changed = control.dateChanged
    else:
        control = {
            "integer": QSpinBox, "decimal": QDoubleSpinBox,
            "slider": QSlider, "dial": QDial,
        }[kind]()
        control.setValue(50)
        value = control.value
        changed = control.valueChanged
    layout.addWidget(control)
    anchor = QPushButton("Focus elsewhere")
    layout.addWidget(anchor)
    filler = QWidget()
    filler.setFixedHeight(1800)
    layout.addWidget(filler)
    area.setWidget(content)
    area.setWidgetResizable(True)
    area.resize(400, 300)
    area.show()
    area.activateWindow()
    (control if focused else anchor).setFocus()
    app.processEvents()
    initial = value()
    edits = []
    changed.connect(lambda *args: edits.append(args))
    try:
        for pixels in (False, True):
            area.verticalScrollBar().setValue(0)
            send_wheel(app, control, pixels=pixels)
            assert value() == initial
            assert not edits
            assert area.verticalScrollBar().value() > 0
        # Editable fields also receive events through their internal line edit.
        if kind in ("integer", "decimal", "editable_combo", "date"):
            area.verticalScrollBar().setValue(0)
            send_wheel(app, control.lineEdit())
            assert value() == initial
            assert not edits
            assert area.verticalScrollBar().value() > 0
    finally:
        area.close()


def test_keyboard_and_explicit_scrollbar_wheel_still_work(app):
    spin = QSpinBox()
    spin.setValue(50)
    QTest.keyClick(spin, Qt.Key.Key_Up)
    assert spin.value() == 51
    area = QScrollArea()
    content = QWidget()
    content.setFixedHeight(1800)
    area.setWidget(content)
    area.resize(400, 300)
    area.show()
    app.processEvents()
    send_wheel(app, area.verticalScrollBar())
    assert area.verticalScrollBar().value() > 0
    area.close()


def test_one_application_filter_survives_garbage_collection():
    # Repeated full initialization belongs in a fresh application: earlier
    # tests may have many live plots subscribed to font/theme updates.
    code = '''
import gc
from PySide6.QtCore import QObject
from morphopt.ui.app import create_application
app = create_application([])
create_application([])
gc.collect()
assert len(app.findChildren(QObject, "wheelInputFilter")) == 1
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_nested_scroll_area_at_its_limit_passes_wheel_to_outer_page(app):
    outer, inner = QScrollArea(), QScrollArea()
    outer_content, inner_content = QWidget(), QWidget()
    outer_layout, inner_layout = QVBoxLayout(outer_content), QVBoxLayout(inner_content)
    spin = QSpinBox()
    spin.setValue(50)
    for layout in (inner_layout, outer_layout):
        filler = QWidget()
        filler.setFixedHeight(1200)
        layout.addWidget(filler)
    inner_layout.addWidget(spin)
    inner.setWidget(inner_content)
    inner.setWidgetResizable(True)
    inner.setFixedHeight(150)
    outer_layout.insertWidget(0, inner)
    outer.setWidget(outer_content)
    outer.setWidgetResizable(True)
    outer.resize(400, 300)
    outer.show()
    app.processEvents()
    inner.verticalScrollBar().setValue(inner.verticalScrollBar().maximum())
    send_wheel(app, spin)
    assert spin.value() == 50
    assert outer.verticalScrollBar().value() > 0
    outer.close()
