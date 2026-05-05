"""
Minimal test: just create and show the UI, no optimization.
"""
import sys
import os

# Force Qt to use XCB (X11) to fix VTK+Wayland X11 BadWindow error
os.environ.setdefault('QT_QPA_PLATFORM', 'xcb')

print(f"DISPLAY={os.environ.get('DISPLAY', 'NOT SET')}")
print(f"QT_QPA_PLATFORM={os.environ.get('QT_QPA_PLATFORM', 'NOT SET')}")

# Step 1: Just import PyQt6 and create QApplication
print("Step 1: Importing PyQt6...")
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PyQt6.QtCore import QTimer
print("Step 1 OK")

app = QApplication(sys.argv)

# Step 2: Import pyvistaqt and create a simple widget
print("Step 2: Importing pyvistaqt...")
import pyvista as pv
from pyvistaqt import QtInteractor
print("Step 2 OK")

# Step 3: Create a simple window with pyvista
print("Step 3: Creating window...")
window = QWidget()
window.setWindowTitle("UI Test")
window.setGeometry(100, 100, 800, 600)
layout = QVBoxLayout(window)

try:
    plotter = QtInteractor(window)
    layout.addWidget(plotter.interactor)
    plotter.set_background('black')
    print("Step 3 OK")
except Exception as e:
    print(f"Step 3 FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Show after setup
window.show()
plotter.interactor.show()
app.processEvents()

# Auto-close after 3 seconds
QTimer.singleShot(3000, app.quit)

print("Starting event loop...")
sys.exit(app.exec())
