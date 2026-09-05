"""Results observer (migrated + redesigned from ``src/morphopt/taskui.py``).

Layout (see UIprompt.md §A):
* top toolbar   -> open results / export the running definition to .py
* top slider    -> sweep optimization iterations
* left options  -> 优化指标 / 几何展示 / 工况 0..N-1
* center stack  -> the page selected on the left, refreshed per iteration

Runs in its own process while the optimization worker writes to ``dataqueue``
({iteration, path_result}), or it can view a finished run (queue pre-loaded
with the last iteration).
"""

from __future__ import annotations

import os
import time

from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QWidget,
    QTableWidget, QTableWidgetItem, QPushButton, QComboBox, QSlider,
    QMessageBox, QListWidget, QStackedWidget, QSplitter, QToolBar, QFileDialog,
)
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor


# ---------------------------------------------------------------------------
# tiny helpers
# ---------------------------------------------------------------------------

class PyVistaQWidget(QWidget):
    """Qt widget wrapping a pyvistaqt ``QtInteractor``."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.plotter = QtInteractor(self)
        layout.addWidget(self.plotter.interactor)
        self.plotter.set_background("black")

    def get_plotter(self):
        return self.plotter

    def rebuild(self, build_fn):
        """Clear the scene and run ``build_fn(plotter)`` to repaint."""
        plotter = self.plotter
        plotter.clear()
        build_fn(plotter)
        plotter.reset_camera()
        plotter.render()


class MonitorThread(QThread):
    update_signal = Signal(dict)

    def __init__(self, dataqueue):
        super().__init__()
        self.dataqueue = dataqueue
        self._quit = False

    def run(self):
        while not self._quit:
            if not self.dataqueue.empty():
                data = self.dataqueue.get()
                self.update_signal.emit({
                    "iteration": data.get("iteration"),
                    "path_result": data.get("path_result"),
                })
            time.sleep(0.1)

    def stop(self):
        self._quit = True


# ---------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------

class _MetricsPage(QWidget):
    """优化指标: history table + objective-vs-iteration curve."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget()
        lay.addWidget(self.table, 3)
        self.figure = Figure(facecolor="#121212")
        self.canvas = FigureCanvasQTAgg(self.figure)
        lay.addWidget(self.canvas, 2)
        self._headers = []
        self._objectives: list[float] = []

    def update_from_history(self, history, iteration: int) -> None:
        obj = list(history.history_objective)
        self._objectives = obj

        # headers -------------------------------------------------------
        num_metrics = 0
        metrics_data = history.history_metrics
        if metrics_data is not None and metrics_data.size > 0:
            num_metrics = metrics_data.shape[-1] if metrics_data.ndim > 1 else 1
        num_def_cols = 0
        def_labels: list[str] = []
        deformation_data_flat = None
        deformation_data = history.history_deformation
        if deformation_data is not None and deformation_data.size > 0:
            if deformation_data.ndim == 2:
                num_def_cols = deformation_data.shape[1]
                def_labels = [f"U0-{d}" for d in range(num_def_cols)]
                deformation_data_flat = deformation_data
            elif deformation_data.ndim == 3:
                nt, nd = deformation_data.shape[1], deformation_data.shape[2]
                num_def_cols = nt * nd
                def_labels = [f"U{t}-{d}" for t in range(nt) for d in range(nd)]
                deformation_data_flat = deformation_data.reshape(deformation_data.shape[0], -1)

        headers = ["Iteration", "Objective"]
        headers += [f"Metric {m}" for m in range(num_metrics)]
        headers += ["Init", "FEA", "Sens", "Update", "Elements", "Nodes"]
        headers += def_labels
        self._headers = headers
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        # rows ----------------------------------------------------------
        n = len(obj)
        self.table.setRowCount(n)
        times = getattr(history, "history_time", None)
        nelems = getattr(history, "history_num_elements", None)
        nnodes = getattr(history, "history_num_nodes", None)
        for i in range(n):
            col = 0
            self.table.setItem(i, col, QTableWidgetItem(str(i + 1))); col += 1
            self.table.setItem(i, col, QTableWidgetItem(f"{obj[i]:.6f}")); col += 1
            for m in range(num_metrics):
                if num_metrics and metrics_data is not None and i < len(metrics_data):
                    row = metrics_data[i] if metrics_data.ndim == 1 else metrics_data[i, :]
                    val = row if np.isscalar(row) else (row[0] if row.size else 0.0)
                    self.table.setItem(i, col, QTableWidgetItem(f"{val:.6f}")); col += 1
                else:
                    col += 1
            if times is not None and i < len(times):
                for t in times[i][:4]:
                    self.table.setItem(i, col, QTableWidgetItem(f"{t:.2f}")); col += 1
            else:
                col += 4
            if nelems is not None and i < len(nelems):
                self.table.setItem(i, col, QTableWidgetItem(str(nelems[i]))); col += 1
            else:
                col += 1
            if nnodes is not None and i < len(nnodes):
                self.table.setItem(i, col, QTableWidgetItem(str(nnodes[i]))); col += 1
            else:
                col += 1
            if num_def_cols and deformation_data_flat is not None and i < len(deformation_data_flat):
                for v in deformation_data_flat[i]:
                    self.table.setItem(i, col, QTableWidgetItem(f"{v:.4e}")); col += 1

        # curve ----------------------------------------------------------
        plt.style.use("dark_background")
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        iters = list(range(1, n + 1))
        ax.plot(iters, obj, marker="o", color="cyan")
        ax.set_xlabel("Iteration")
        ax.set_ylabel("Objective")
        ax.set_title("Objective vs Iteration")
        ax.grid(True, color="white", linestyle="--", linewidth=0.5)
        self.canvas.draw()


class _GeometryPage(QWidget):
    """几何展示: current geometry of the selected iteration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.view = PyVistaQWidget(self)
        lay.addWidget(self.view)
        self._built_iter = -1
        self._params = None
        self._path_result = None

    def build(self, params, path_result: str, iteration: int) -> None:
        if (self._built_iter == iteration and self._path_result == path_result):
            return
        self._built_iter = iteration
        self._path_result = path_result

        def _build(plotter):
            plotter.enable_lightkit()
            params.load(foldpath=path_result + "/log/", iteration=iteration)
            params.plot(plotter=plotter)
            plotter.show_axes()

        try:
            self.view.rebuild(_build)
        except Exception as exc:  # pragma: no cover - best effort rendering
            print(f"Geometry preview failed at iter {iteration}: {exc}")


class _CasePage(QWidget):
    """工况 k: deformed geometry for one load case at the selected iteration."""

    def __init__(self, case: int, parent=None):
        super().__init__(parent)
        self.case = case
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.view = PyVistaQWidget(self)
        lay.addWidget(self.view)
        self._built = (-1, None)

    def build(self, path_result: str, iteration: int) -> None:
        if self._built == (iteration, path_result):
            return
        self._built = (iteration, path_result)
        stl = f"{path_result}/log/deformation/task_{self.case}_iter_{iteration}.stl"

        def _build(plotter):
            plotter.enable_lightkit()
            if os.path.exists(stl):
                mesh = pv.read(stl)
                plotter.add_mesh(mesh, color=(40 / 255, 120 / 255, 181 / 255),
                                 opacity=1.0, show_edges=True)
                plotter.show_axes()

        self.view.rebuild(_build)


# ---------------------------------------------------------------------------
# observer main window
# ---------------------------------------------------------------------------

class ObserverUI(QMainWindow):
    """Redesigned results observer (see module docstring)."""

    def __init__(self, dataqueue, Controller=None, main_filepath: str = None):
        super().__init__()
        self.dataqueue = dataqueue
        self.Controller = Controller
        self.main_filepath = main_filepath
        self.path_result = None
        self.iteration = 0
        self.last_shown = -1
        self._cases: dict[int, int] = {}          # option row -> case index
        self._params = None
        self._history = None
        self._geometry_page = _GeometryPage()
        self._metrics_page = _MetricsPage()
        self._case_pages: dict[int, _CasePage] = {}

        self._build_toolbar()
        self._build_ui()
        self._apply_dark_theme(self)

        self._thread = MonitorThread(self.dataqueue)
        self._thread.update_signal.connect(self.update_ui)
        self._thread.start()

    # ------------------------------------------------------------------ ui
    def _build_toolbar(self) -> None:
        tb = QToolBar("Main", self)
        tb.setMovable(False)
        self.addToolBar(tb)

        act_open = QAction("打开结果…", self)
        act_open.triggered.connect(self._open_result_folder)
        tb.addAction(act_open)
        tb.addSeparator()

        act_export = QAction("导出当前定义 .py", self)
        act_export.triggered.connect(self._export_definition)
        tb.addAction(act_export)
        tb.addSeparator()

        self.follow_btn = QPushButton("跟随运行")
        self.follow_btn.setCheckable(True)
        self.follow_btn.setChecked(True)
        self.follow_btn.setToolTip("自动跳到最新迭代（运行中）")
        tb.addWidget(self.follow_btn)

    def _build_ui(self) -> None:
        self.setWindowTitle("MorphOpt — Optimization Observer")
        self.resize(1500, 850)

        central = QWidget()
        main = QVBoxLayout(central)
        main.setContentsMargins(4, 4, 4, 4)

        # top iteration slider -------------------------------------------
        top = QHBoxLayout()
        self.btn_prev = QPushButton("◀")
        self.btn_prev.setFixedWidth(32)
        self.btn_prev.clicked.connect(lambda: self._nudge(-1))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(1)
        self.slider.setMaximum(1)
        self.slider.valueChanged.connect(self._on_slider)
        self.btn_next = QPushButton("▶")
        self.btn_next.setFixedWidth(32)
        self.btn_next.clicked.connect(lambda: self._nudge(1))
        self.iter_label = QLabel("0 / 0")
        self.iter_label.setMinimumWidth(70)
        top.addWidget(self.btn_prev)
        top.addWidget(self.slider, 1)
        top.addWidget(self.btn_next)
        top.addWidget(self.iter_label)
        main.addLayout(top)

        # left options + center stack ------------------------------------
        split = QSplitter(Qt.Orientation.Horizontal)
        self.options = QListWidget()
        self.options.setFixedWidth(170)
        self.options.addItem("优化指标")
        self.options.addItem("几何展示")
        self.options.currentRowChanged.connect(self._on_option)
        split.addWidget(self.options)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._metrics_page)
        self.stack.addWidget(self._geometry_page)
        split.addWidget(self.stack)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([170, 1200])
        main.addWidget(split, 1)

        self.setCentralWidget(central)
        self.options.setCurrentRow(0)

    # ------------------------------------------------------------ options
    def _on_option(self, row: int) -> None:
        if row < 0 or row >= self.stack.count():
            return
        if row == 1:  # 几何展示
            self._refresh_geometry()
        elif row >= 2 and row - 2 in self._case_pages:  # 工况 k
            self._refresh_case(row - 2)
        self.stack.setCurrentIndex(row)

    def _refresh_geometry(self) -> None:
        if self.path_result and self._params is not None:
            self._geometry_page.build(self._params, self.path_result, self.slider.value())

    def _refresh_case(self, case: int) -> None:
        page = self._case_pages.get(case)
        if page is not None and self.path_result:
            page.build(self.path_result, self.slider.value())

    # -------------------------------------------------------------- slider
    def _nudge(self, delta: int) -> None:
        self.slider.setValue(self.slider.value() + delta)

    def _on_slider(self, value: int) -> None:
        self.iter_label.setText(f"{value} / {self.slider.maximum()}")
        if self.slider.maximum() > 0:
            self.last_shown = value
            row = self.options.currentRow()
            if row == 1:
                self._refresh_geometry()
            elif row >= 2:
                self._refresh_case(row - 2)

    # ------------------------------------------------------------- updates
    def update_ui(self, data: dict) -> None:
        iteration = data.get("iteration")
        path_result = data.get("path_result")
        if not path_result:
            return
        self.path_result = path_result

        from ..optcore.history import History
        history = History()
        try:
            history.load(foldpath=path_result + "/log/", iteration=iteration)
        except Exception as exc:
            print(f"history load failed: {exc}")
            return
        self._history = history

        from ..optcore.modelparams import Params
        try:
            if self._params is None:
                # build empty params from the controller (mirrors taskui)
                if self.Controller is not None:
                    self._params = self.Controller.Params()
                    self._params.initialize()
                else:
                    self._params = Params(surfaces=None, feamodel=None, materials=None)
            self.iteration = iteration
        except Exception as exc:
            print(f"params init failed: {exc}")

        # discover load cases from deformation folder
        self._discover_cases(path_result, iteration)

        # metrics page
        self._metrics_page.update_from_history(history, iteration)

        # slider range ----------------------------------------------------
        max_iter = max(1, int(getattr(history, "iteration", iteration) or iteration))
        self.slider.blockSignals(True)
        self.slider.setMaximum(max_iter)
        if self.follow_btn.isChecked():
            self.slider.setValue(max_iter)
        self.slider.blockSignals(False)
        self.iter_label.setText(f"{self.slider.value()} / {max_iter}")

        # refresh whatever option is currently shown
        row = self.options.currentRow()
        if row == 0:
            pass  # metrics already updated
        elif row == 1:
            self._refresh_geometry()
        elif row - 2 in self._case_pages:
            self._refresh_case(row - 2)

    def _discover_cases(self, path_result: str, iteration: int) -> None:
        import glob
        files = glob.glob(f"{path_result}/log/deformation/task_*_iter_{iteration}.stl")
        found = set()
        for fpath in files:
            base = os.path.basename(fpath)
            parts = base.split("_")
            if len(parts) >= 4 and parts[0] == "task":
                try:
                    found.add(int(parts[1]))
                except ValueError:
                    pass
        existing = set(self._case_pages)
        for case in sorted(found - existing):
            page = _CasePage(case)
            self._case_pages[case] = page
            self.stack.addWidget(page)
            self.options.addItem(f"工况 {case}")

    # -------------------------------------------------------------- actions
    def _open_result_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择结果文件夹", os.getcwd())
        if folder:
            self.path_result = folder
            # reload as the last iteration of that run
            from ..optcore.history import History
            h = History()
            try:
                h.load(foldpath=folder + "/log/")
                last = h.iteration
            except Exception:
                last = 1
            self.dataqueue.put({"iteration": last, "path_result": folder})

    def _export_definition(self) -> None:
        if not self.path_result:
            QMessageBox.information(self, "导出", "还没有可导出的优化定义。")
            return
        src = os.path.join(self.path_result, "scripts", "MAIN_SCRIPT_FOR_RESTART.py")
        if not os.path.exists(src):
            QMessageBox.warning(self, "导出", f"未找到定义脚本：{src}")
            return
        out, _ = QFileDialog.getSaveFileName(
            self, "导出当前优化定义", os.path.basename(src) + ".py", "Python (*.py)")
        if out:
            with open(src, "r", encoding="utf-8") as f:
                text = f.read()
            with open(out, "w", encoding="utf-8") as f:
                f.write(text)
            self.statusBar().showMessage(f"已导出：{out}", 4000)

    def closeEvent(self, event):  # noqa: N802
        reply = QMessageBox.question(self, "退出确认", "确定要关闭观察器吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._thread.stop()
            event.accept()
        else:
            event.ignore()

    # ---------------------------------------------------------------- style
    @staticmethod
    def _apply_dark_theme(app) -> None:
        app.setStyleSheet("""
        QMainWindow, QWidget { background-color: #121212; color: #e0e0e0; }
        QTableWidget { background-color: #1e1e1e; color: #e0e0e0;
                       gridline-color: #333; border: 1px solid #333; }
        QHeaderView::section { background-color: #2d2d2d; color: #e0e0e0;
                               border: 1px solid #333; padding: 4px; }
        QListWidget { background-color: #1a1a1a; border: 1px solid #333; }
        QListWidget::item { padding: 8px; }
        QListWidget::item:selected { background-color: #0d47a1; }
        QComboBox, QLineEdit { background-color: #2d2d2d; border: 1px solid #444; }
        QPushButton { background-color: #0d47a1; color: #fff; border: none;
                      padding: 4px 12px; border-radius: 3px; }
        QPushButton:hover { background-color: #1565c0; }
        QPushButton:checked { background-color: #00695c; }
        QToolBar { background-color: #1a1a1a; border-bottom: 1px solid #333; spacing: 6px; }
        """)


# ---------------------------------------------------------------------------
# process entry
# ---------------------------------------------------------------------------

def run_ui(dataqueue, main_filepath: str = None):
    """Run the observer (call from its own process)."""
    import sys
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    os.environ["KMP_DUPLICATE_LIB_OK"] = "True"

    Controller = None
    if main_filepath:
        import torch
        torch.set_default_dtype(torch.float64)
        torch.set_default_device("cpu")
        filename = os.path.splitext(os.path.basename(main_filepath))[0]
        filepath = os.path.dirname(main_filepath)
        os.chdir(filepath)
        sys.path.append(os.getcwd())
        Controller = getattr(__import__(filename), "ThisController")

    app = QApplication.instance() or QApplication(sys.argv)
    ui = ObserverUI(dataqueue, Controller=Controller, main_filepath=main_filepath)
    ui.show()
    sys.exit(app.exec())


def view_optimization_result(path_result: str):
    """Open the observer on an already finished optimization run."""
    import multiprocessing as mp
    from ..optcore.history import History

    if not os.path.exists(os.path.join(path_result, "scripts", "MAIN_SCRIPT_FOR_RESTART.py")):
        raise FileNotFoundError(f"{path_result} is not a morphopt result folder")

    h = History()
    try:
        h.load(foldpath=os.path.join(path_result, "log"))
        last = h.iteration
    except Exception:
        last = 1

    dataqueue = mp.Queue()
    dataqueue.put({"iteration": last, "path_result": path_result})
    main_filepath = os.path.join(path_result, "scripts", "MAIN_SCRIPT_FOR_RESTART.py")
    run_ui(dataqueue, main_filepath)
