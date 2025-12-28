from os import path
import sys
import multiprocessing as mp
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget, QTableWidget, QTableWidgetItem, QPushButton, QHBoxLayout, QComboBox
from PyQt5 import QtWidgets
from PyQt5.QtCore import QTimer, QThread, pyqtSignal
import time
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import numpy as np
from traits.api import HasTraits, Instance, on_trait_change
from traitsui.api import View, Item
from tvtk.pyface.scene_editor import SceneEditor
from mayavi.tools.mlab_scene_model import MlabSceneModel
from mayavi.core.ui.mayavi_scene import MayaviScene
from tvtk.pyface.api import Scene
import mayavi.mlab as mlab
mlab.options.backend = 'auto'

class MayaviQWidget(QWidget):
    """Qt widget to hold the Mayavi visualization"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Mayavi visualization
        self.visualization = MayaviVisualizer()
        self.ui = self.visualization.edit_traits(
            parent=self, kind='subpanel').control
        layout.addWidget(self.ui)
        self.layout = layout
        
    def get_scene(self):
        return self.visualization.scene

    def get_mlab(self):
        return self.visualization.scene.mlab

class MayaviVisualizer(HasTraits):
    """Mayavi scene wrapper"""
    
    scene = Instance(MlabSceneModel, ())
    
    view = View(Item('scene', editor=SceneEditor(scene_class=MayaviScene),
                   height=400, width=600, show_label=False),
              resizable=True)
    
    def __init__(self):
        super().__init__()
        # Initialize with background only
        # Don't access scene yet, defer until Qt main thread is ready
        self._scene_initialized = False
    
    def _initialize_scene(self):
        """Initialize the scene in the main thread when ready"""
        if not self._scene_initialized:
            self.scene.background = (1, 1, 1)  # white background
            # Set text color to black for better visibility against white background
            self.scene.foreground = (0, 0, 0)  # black text
            self.scene.mlab.clf()
            self._scene_initialized = True
            
    def start_scene(self):
        """Start scene in the Qt main thread context"""
        # Use QTimer to ensure this runs in the main thread
        QTimer.singleShot(0, self._initialize_scene)


class MonitorThread(QThread):
    update_signal = pyqtSignal(dict)

    def __init__(self, dataqueue):
        super().__init__()
        self.dataqueue = dataqueue

    def run(self):
        while True:
            if not self.dataqueue.empty():
                data = self.dataqueue.get()
                iteration = data['iteration']
                path_result = data['path_result']
                self.update_signal.emit({'iteration': iteration, 'path_result': path_result})
            time.sleep(0.1)  # poll

class OptimizationMonitorUI(QMainWindow):
    def __init__(self, dataqueue, Controller):
        super().__init__()
        self.dataqueue = dataqueue
        self.Controller = Controller
        self.params = Controller.Params()
        self.params.initialize()
        self.path_result = None
        self.iteration = 0
        self.initUI()
        self.monitor_thread = MonitorThread(self.dataqueue)
        self.monitor_thread.update_signal.connect(self.update_ui)
        self.monitor_thread.start()

    def initUI(self):
        self.setWindowTitle('Optimization Monitor')
        self.setGeometry(100, 100, 1400, 800)
        
        main_layout = QVBoxLayout()
        
        # Top: History table
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels(['Iteration', 'Objective', 'Init Time', 'FEA Time', 'Update Time'])
        main_layout.addWidget(self.history_table)
        
        # Bottom: Controls and plots
        bottom_layout = QVBoxLayout()
        
        # Controls
        controls_layout = QHBoxLayout()
        self.iteration_combo = QComboBox()
        self.iteration_combo.setToolTip('Select Iteration')
        controls_layout.addWidget(QLabel('Iteration:'))
        controls_layout.addWidget(self.iteration_combo)
        
        self.case_combo = QComboBox()
        self.case_combo.setToolTip('Select Deformation Case')
        controls_layout.addWidget(QLabel('Case:'))
        controls_layout.addWidget(self.case_combo)
        
        self.plot_button = QPushButton('Plot')
        self.plot_button.clicked.connect(self.plot_selected)
        controls_layout.addWidget(self.plot_button)
        
        bottom_layout.addLayout(controls_layout)
        
        # Plots
        plots_layout = QHBoxLayout()  # Horizontal layout for surface and deformation plots
        
        self.mayavi_container_surface = MayaviQWidget()
        plots_layout.addWidget(self.mayavi_container_surface)
        
        self.mayavi_container_deformation = MayaviQWidget()
        plots_layout.addWidget(self.mayavi_container_deformation)
        
        bottom_layout.addLayout(plots_layout)
        
        main_layout.addLayout(bottom_layout)
        
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def update_ui(self, data):
        iteration = data['iteration']
        path_result = data['path_result']
        if path_result:
            self.path_result = path_result
            # load history
            from .optcore.history import History
            history = History()
            history.load(foldpath=self.path_result + '/log/', iteration=iteration)
            
            # Update table
            self.history_table.setRowCount(len(history.history_objective))
            for i in range(len(history.history_objective)):
                self.history_table.setItem(i, 0, QTableWidgetItem(str(i)))
                self.history_table.setItem(i, 1, QTableWidgetItem(f'{history.history_objective[i]:.6f}'))
                if i < len(history.history_time):
                    t = history.history_time[i]
                    self.history_table.setItem(i, 2, QTableWidgetItem(f'{t[0]:.2f}'))
                    self.history_table.setItem(i, 3, QTableWidgetItem(f'{t[1]:.2f}'))
                    self.history_table.setItem(i, 4, QTableWidgetItem(f'{t[2]:.2f}'))
            
            # Update iteration combo
            if self.iteration_combo.findText(str(iteration)) == -1:
                self.iteration_combo.addItem(str(iteration))
            
            # Update case combo if deformation available
            if history.history_deformation and history.history_deformation[-1]:
                num_cases = len(history.history_deformation[-1])
                self.case_combo.clear()
                for j in range(num_cases):
                    self.case_combo.addItem(f'Case {j}')

    def plot_selected(self):
        selected_iter = int(self.iteration_combo.currentText()) if self.iteration_combo.currentText() else 0
        selected_case = int(self.case_combo.currentText().split()[-1]) if self.case_combo.currentText() else 0
        
        if self.path_result:
            # Plot surface using embedded mayavi
            mlab.figure(figure=self.mayavi_container_surface.get_scene().mayavi_scene)
            mlab.clf()  # Clear figure
            self.params.geometry.load(foldpath=self.path_result + '/log/', iteration=selected_iter)
            self.params.geometry.plot()
            
            # Plot deformation using embedded mayavi with obj file
            mlab.figure(figure=self.mayavi_container_deformation.get_scene().mayavi_scene)
            mlab.clf()  # Clear figure
            obj_path = f"{self.path_result}/log/deformation/task_{selected_case}_iter_{selected_iter}.obj"
            try:
                vertices, faces = self.load_obj(obj_path)
                # Convert faces to triangles
                triangles = []
                for face in faces:
                    if len(face) >= 3:
                        triangles.extend(face[:3])  # take first 3 for triangulation
                triangles = np.array(triangles).reshape(-1, 3)
                self.mayavi_container_deformation.get_mlab().triangular_mesh(vertices[:,0], vertices[:,1], vertices[:,2], triangles)
            except Exception as e:
                print(f"Error loading OBJ: {e}")

    def load_obj(self, filepath):
        vertices = []
        faces = []
        with open(filepath, 'r') as f:
            for line in f:
                if line.startswith('v '):
                    parts = line.split()
                    vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
                elif line.startswith('f '):
                    parts = line.split()
                    face = [int(p.split('/')[0]) - 1 for p in parts[1:]]
                    faces.append(face)
        return np.array(vertices), faces

def run_ui(dataqueue: mp.Queue, main_filepath: str = None):
    import os
    import torch
    torch.set_default_dtype(torch.float64)
    torch.set_default_device('cpu')
    filename = os.path.splitext(os.path.basename(main_filepath))[0] 
    filepath = os.path.dirname(main_filepath)
    os.chdir(filepath)
    import sys
    sys.path.append(os.getcwd())

    Controller = getattr(__import__(filename), 'ThisController')

    app = QApplication(sys.argv)
    ui = OptimizationMonitorUI(dataqueue, Controller)
    ui.show()
    ui.mayavi_container_surface.visualization.start_scene()
    ui.mayavi_container_deformation.visualization.start_scene()
    sys.exit(app.exec_())