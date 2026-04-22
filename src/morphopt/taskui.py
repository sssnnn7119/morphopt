from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from pyvista.plotting import plotter

if TYPE_CHECKING:
    import morphopt


import multiprocessing as mp
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget, QTableWidget, QTableWidgetItem, QPushButton, QHBoxLayout, QComboBox, QMessageBox, QSlider
from PyQt6 import QtWidgets
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, Qt
import time
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor

class PyVistaQWidget(QWidget):
    """Qt widget to hold the PyVista visualization"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # PyVista visualization
        self.plotter = QtInteractor(self)
        layout.addWidget(self.plotter.interactor)
        self.layout = layout

        self.plotter.set_background('black')
        
    def get_plotter(self):
        return self.plotter



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
        self.params: morphopt.GeometryParams
        self.params = Controller.Params().geometry
        self.path_result = None
        self.iteration = 0
        self.last_plotted_iteration = -1
        self.surface_cache = {}
        self.deformation_cache = {}
        self.figure = Figure(facecolor='#121212')  # Match app background
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setStyleSheet("background-color: #121212;") # Ensure widget bg is also dark
        self.initUI()
        self.monitor_thread = MonitorThread(self.dataqueue)
        self.monitor_thread.update_signal.connect(self.update_ui)
        self.monitor_thread.start()

    def initUI(self):
        self.setWindowTitle('Optimization Monitor')
        self.setGeometry(100, 100, 1400, 800)
        
        main_layout = QVBoxLayout()
        
        # Top half: Table and plot
        top_layout = QHBoxLayout()
        
        # Left top: History table
        left_layout = QVBoxLayout()
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(7)
        self.history_table.setHorizontalHeaderLabels(['Iteration', 'Objective', 'Init Time', 'FEA Time', 'Update Time', 'Num Elements', 'Num Nodes'])
        left_layout.addWidget(self.history_table)
        top_layout.addLayout(left_layout)
        
        # Right top: Plot
        right_layout = QVBoxLayout()
        right_layout.addWidget(self.canvas)
        top_layout.addLayout(right_layout)
        
        main_layout.addLayout(top_layout)
        
        # Bottom: Controls and plots
        bottom_layout = QVBoxLayout()
        
        # Controls
        controls_layout = QHBoxLayout()
        
        controls_layout.addWidget(QLabel('Iteration:'))
        self.iteration_label = QLabel('0')
        self.iteration_label.setFixedWidth(30)
        controls_layout.addWidget(self.iteration_label)
        
        self.iteration_slider = QSlider(Qt.Orientation.Horizontal)
        self.iteration_slider.setToolTip('Select Iteration')
        self.iteration_slider.setMinimum(1)
        self.iteration_slider.setMaximum(1)
        self.iteration_slider.valueChanged.connect(self.on_slider_change)
        controls_layout.addWidget(self.iteration_slider)
        
        self.slider_timer = QTimer()
        self.slider_timer.timeout.connect(self.check_slider_update)
        self.slider_timer.start(100) # Check every 0.1s
        
        self.case_combo = QComboBox()
        self.case_combo.setToolTip('Select Deformation Case')
        controls_layout.addWidget(QLabel('Case:'))
        controls_layout.addWidget(self.case_combo)
        
        bottom_layout.addLayout(controls_layout)
        
        # Plots
        plots_layout = QHBoxLayout()  # Horizontal layout for surface and deformation plots
        
        self.pyvista_container_surface = PyVistaQWidget()
        plots_layout.addWidget(self.pyvista_container_surface)
        
        self.pyvista_container_deformation = PyVistaQWidget()
        plots_layout.addWidget(self.pyvista_container_deformation)
        
        bottom_layout.addLayout(plots_layout)
        
        main_layout.addLayout(bottom_layout)
        
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def closeEvent(self, event):
        reply = QMessageBox.question(self, 'Exit Confirmation',
                                     "Are you sure you want to exit the optimization monitor?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()

    def update_ui(self, data):
        iteration = data['iteration']
        path_result = data['path_result']
        if path_result:
            self.path_result = path_result

            # Cache meshes
            import glob
            import os
            
            # Surface Cache
            if iteration not in self.surface_cache:
                # try:
                    self.params.load(foldpath=self.path_result + '/log/', iteration=iteration)
                    self.surface_cache[iteration] = self.params.get_meshes()
                # except Exception as e:
                #     print(f"Error caching surface for iteration {iteration}: {e}")

            # Deformation Cache
            if iteration not in self.deformation_cache:
                self.deformation_cache[iteration] = {}
            
            def_pattern = f"{self.path_result}/log/deformation/task_*_iter_{iteration}.stl"
            def_files = glob.glob(def_pattern)
            
            found_cases = set()
            for fpath in def_files:
                try:
                    basename = os.path.basename(fpath)
                    parts = basename.split('_')
                    # Expected: task_{case}_iter_{iter}.obj
                    if len(parts) >= 4 and parts[0] == 'task':
                        case_idx = int(parts[1])
                        found_cases.add(case_idx)
                        if case_idx not in self.deformation_cache[iteration]:
                            mesh = pv.read(fpath)
                            self.deformation_cache[iteration][case_idx] = mesh
                except Exception as e:
                    print(f"Error caching deformation {fpath}: {e}")
            
            # Update Case Combo
            current_cases = set()
            for i in range(self.case_combo.count()):
                try:
                    txt = self.case_combo.itemText(i)
                    if txt:
                        c = int(txt.split()[-1])
                        current_cases.add(c)
                except:
                    pass
            
            for c in sorted(list(found_cases)):
                if c not in current_cases:
                    self.case_combo.addItem(f"Task {c}")

            # load history
            from .optcore.history import History
            history = History()
            history.load(foldpath=self.path_result + '/log/', iteration=iteration)
            
            # Update table
            # Detect metrics
            metrics_data = history.history_metrics
            num_metrics = 0
            if metrics_data.size > 0:
                 if metrics_data.ndim == 1:
                     num_metrics = 1
                     metrics_data = metrics_data.reshape(-1, 1)
                 else:
                     num_metrics = metrics_data.shape[1]
            
            # Detect deformation
            deformation_data = history.history_deformation
            num_def_cols = 0
            def_labels = []
            
            # We need a flattened version for the table
            deformation_data_flat = None

            if deformation_data.size > 0:
                 if deformation_data.ndim == 2:
                     # (iter, dofs)
                     num_def_cols = deformation_data.shape[1]
                     for d in range(num_def_cols):
                         def_labels.append(f'U0-{d}')
                     deformation_data_flat = deformation_data
                 elif deformation_data.ndim == 3:
                     # (iter, tasks, dofs)
                     n_tasks = deformation_data.shape[1]
                     n_dofs = deformation_data.shape[2]
                     num_def_cols = n_tasks * n_dofs
                     for t in range(n_tasks):
                         for d in range(n_dofs):
                             def_labels.append(f'U{t}-{d}')
                     deformation_data_flat = deformation_data.reshape(deformation_data.shape[0], -1)

            # Base headers
            headers = ['Iteration', 'Objective']
            for m in range(num_metrics):
                headers.append(f'Metric {m}')
            headers.extend(['Init Time', 'FEA Time', 'Update Time', 'Num Elements', 'Num Nodes'])
            headers.extend(def_labels)
            
            self.history_table.setColumnCount(len(headers))
            self.history_table.setHorizontalHeaderLabels(headers)

            self.history_table.setRowCount(len(history.history_objective))
            for i in range(len(history.history_objective)):
                col = 0
                # Iteration
                self.history_table.setItem(i, col, QTableWidgetItem(str(i+1))); col += 1
                # Objective
                self.history_table.setItem(i, col, QTableWidgetItem(f'{history.history_objective[i]:.6f}')); col += 1
                
                # Metrics
                if num_metrics > 0:
                     if i < len(metrics_data):
                        for m in range(num_metrics):
                            val = metrics_data[i, m]
                            self.history_table.setItem(i, col, QTableWidgetItem(f'{val:.6f}')); col += 1
                     else: col += num_metrics

                # Time
                if i < len(history.history_time):
                    t = history.history_time[i]
                    self.history_table.setItem(i, col, QTableWidgetItem(f'{t[0]:.2f}')); col += 1
                    self.history_table.setItem(i, col, QTableWidgetItem(f'{t[1]:.2f}')); col += 1
                    self.history_table.setItem(i, col, QTableWidgetItem(f'{t[2]:.2f}')); col += 1
                else: col += 3
                
                # Elements/Nodes
                if i < len(history.history_num_elements):
                    self.history_table.setItem(i, col, QTableWidgetItem(str(history.history_num_elements[i]))); col += 1
                else: col += 1
                if i < len(history.history_num_nodes):
                    self.history_table.setItem(i, col, QTableWidgetItem(str(history.history_num_nodes[i]))); col += 1
                else: col += 1

                # Deformation
                if num_def_cols > 0:
                     if deformation_data_flat is not None and i < len(deformation_data_flat):
                        for d in range(num_def_cols):
                            val = deformation_data_flat[i, d]
                            self.history_table.setItem(i, col, QTableWidgetItem(f'{val:.4e}')); col += 1
                     else: col += num_def_cols
            
            # Update iteration slider
            if iteration > self.iteration_slider.maximum():
                self.iteration_slider.setMaximum(iteration)
                # If we are strictly following (at max-1 since max just increased by 1), update
                if self.iteration_slider.value() == iteration - 1:
                    self.iteration_slider.setValue(iteration)
            
            # Update plot
            plt.style.use('dark_background')  # Set dark theme for black background and white text
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            iterations = list(range(1, len(history.history_objective) + 1))
            ax.plot(iterations, history.history_objective, marker='o', color='cyan')  # Optional: set line color for better visibility
            ax.set_xlabel('Iteration')
            ax.set_ylabel('Objective Function')
            ax.set_title('Objective Function vs Iteration')
            ax.grid(True, color='white', linestyle='--', linewidth=0.5)
            self.canvas.draw()

    def on_slider_change(self, value):
        self.iteration_label.setText(str(value))

    def check_slider_update(self):
        val = self.iteration_slider.value()
        if val != self.last_plotted_iteration:
            self.plot_selected()

    def plot_selected(self):
        selected_iter = self.iteration_slider.value()
        self.last_plotted_iteration = selected_iter
        
        txt = self.case_combo.currentText()
        selected_case = int(txt.split()[-1]) if txt else 0
        
        if self.path_result:
            # Plot surface using cache
            plotter_surface = self.pyvista_container_surface.get_plotter()
            surface_camera = plotter_surface.camera_position

            plotter_surface.clear()
            plotter_surface.enable_lightkit()
            plotter_surface.set_background('black')
            
            meshes = []
            if selected_iter in self.surface_cache:
                meshes = self.surface_cache[selected_iter]
            else:
                try:
                    self.params.load(foldpath=self.path_result + '/log/', iteration=selected_iter)
                    meshes = self.params.get_meshes()
                    self.surface_cache[selected_iter] = meshes
                    import gc
                    gc.collect()
                except Exception as e:
                    print(f"Error loading geometry: {e}")

            for i, mesh in enumerate(meshes):
                alpha = 0.6 if i == 0 else 1.0
                plotter_surface.add_mesh(mesh, opacity=alpha, color=(40.0 / 255, 120.0 / 255, 181.0 / 255),
                           diffuse=0.8, specular=0.2, ambient=0.3, specular_power=10,
                           smooth_shading=True, show_edges=False)

            plotter_surface.show_axes()
            plotter_surface.camera_position = surface_camera
            
            # Plot deformation using cache
            plotter_def = self.pyvista_container_deformation.get_plotter()
            def_camera = plotter_def.camera_position

            plotter_def.clear()
            plotter_def.enable_lightkit()
            plotter_def.set_background('black')
            
            mesh_def = None
            if selected_iter in self.deformation_cache and selected_case in self.deformation_cache[selected_iter]:
                mesh_def = self.deformation_cache[selected_iter][selected_case]
            else:
                # Fallback to file reading if not cached
                obj_path = f"{self.path_result}/log/deformation/task_{selected_case}_iter_{selected_iter}.obj"
                try:
                    import os
                    if os.path.exists(obj_path):
                         mesh_def = pv.read(obj_path)
                except Exception as e:
                    print(f"Error loading OBJ: {e}")
            
            if mesh_def:
                plotter_def.add_mesh(mesh_def, color=(40.0/255, 120.0/255, 181.0/255), opacity=1.0, show_edges=True)
                plotter_def.show_axes()
                
            plotter_def.camera_position = def_camera


def run_ui(dataqueue: mp.Queue, main_filepath: str = None):
    import os
    
    os.environ['KMP_DUPLICATE_LIB_OK']='True'
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
    
    # Set dark stylesheet for the entire application
    app.setStyleSheet("""
        QMainWindow, QWidget {
            background-color: #121212;
            color: #ffffff;
        }
        QTableWidget {
            background-color: #1e1e1e;
            color: #ffffff;
            gridline-color: #333333;
            border: 1px solid #333333;
        }
        QHeaderView::section {
            background-color: #2d2d2d;
            color: #ffffff;
            border: 1px solid #333333;
            padding: 4px;
        }
        QComboBox {
            background-color: #2d2d2d;
            color: #ffffff;
            border: 1px solid #333333;
            padding: 5px;
        }
        QComboBox::drop-down {
            border: none;
        }
        QPushButton {
            background-color: #0d47a1;
            color: #ffffff;
            border: none;
            padding: 5px 15px;
            border-radius: 3px;
        }
        QPushButton:hover {
            background-color: #1565c0;
        }
        QLabel {
            color: #e0e0e0;
        }
    """)
    
    ui = OptimizationMonitorUI(dataqueue, Controller)
    ui.show()
    sys.exit(app.exec_())