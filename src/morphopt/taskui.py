from os import path
import sys
import multiprocessing as mp
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget, QTableWidget, QTableWidgetItem, QPushButton, QHBoxLayout, QComboBox
from PyQt6 import QtWidgets
from PyQt6.QtCore import QTimer, QThread, pyqtSignal
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
        self.params = Controller.Params()
        self.params.initialize()
        self.path_result = None
        self.iteration = 0
        self.figure = Figure()
        self.canvas = FigureCanvasQTAgg(self.figure)
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
        
        self.pyvista_container_surface = PyVistaQWidget()
        plots_layout.addWidget(self.pyvista_container_surface)
        
        self.pyvista_container_deformation = PyVistaQWidget()
        plots_layout.addWidget(self.pyvista_container_deformation)
        
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
                self.history_table.setItem(i, 0, QTableWidgetItem(str(i+1)))
                self.history_table.setItem(i, 1, QTableWidgetItem(f'{history.history_objective[i]:.6f}'))
                if i < len(history.history_time):
                    t = history.history_time[i]
                    self.history_table.setItem(i, 2, QTableWidgetItem(f'{t[0]:.2f}'))
                    self.history_table.setItem(i, 3, QTableWidgetItem(f'{t[1]:.2f}'))
                    self.history_table.setItem(i, 4, QTableWidgetItem(f'{t[2]:.2f}'))
                if i < len(history.history_num_elements):
                    self.history_table.setItem(i, 5, QTableWidgetItem(str(history.history_num_elements[i])))
                if i < len(history.history_num_nodes):
                    self.history_table.setItem(i, 6, QTableWidgetItem(str(history.history_num_nodes[i])))
            
            # Update iteration combo
            if self.iteration_combo.findText(str(iteration)) == -1:
                self.iteration_combo.addItem(str(iteration))
            
            # Update case combo if deformation available
            if history.history_deformation and history.history_deformation[-1]:
                num_cases = len(history.history_deformation[-1])
                self.case_combo.clear()
                for j in range(num_cases):
                    self.case_combo.addItem(f'Case {j}')
            
            # Update plot
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            iterations = list(range(1, len(history.history_objective) + 1))
            ax.plot(iterations, history.history_objective, marker='o')
            ax.set_xlabel('Iteration')
            ax.set_ylabel('Objective Function')
            ax.set_title('Objective Function vs Iteration')
            ax.grid(True)
            self.canvas.draw()

    def plot_selected(self):
        selected_iter = int(self.iteration_combo.currentText()) if self.iteration_combo.currentText() else 0
        selected_case = int(self.case_combo.currentText().split()[-1]) if self.case_combo.currentText() else 0
        
        if self.path_result:
            # Plot surface using embedded pyvista
            plotter_surface = self.pyvista_container_surface.get_plotter()
            plotter_surface.clear()
            plotter_surface.set_background('white')
            self.params.geometry.load(foldpath=self.path_result + '/log/', iteration=selected_iter)
            self.params.geometry.plot(plotter=plotter_surface)
            
            # Plot deformation using embedded pyvista with obj file
            plotter_def = self.pyvista_container_deformation.get_plotter()
            plotter_def.clear()
            plotter_def.set_background('white')
            obj_path = f"{self.path_result}/log/deformation/task_{selected_case}_iter_{selected_iter}.obj"
            try:
                mesh = pv.read(obj_path)
                plotter_def.add_mesh(mesh)
            except Exception as e:
                print(f"Error loading OBJ: {e}")


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
    sys.exit(app.exec_())