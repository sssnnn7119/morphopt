"""Capture the actual assets UI with the documentation font policy.

Run from the repository: conda run -n mine python scripts/docs/capture_assets.py
Requires fonttools, fontconfig and the installed Noto Sans CJK SC family.
"""

import base64
import json
from pathlib import Path

from PySide6.QtCore import QTimer

from capture_fonts import CaptureFonts
from morphopt.ui.app import create_application
from morphopt.ui.application import ProblemLibrary
from morphopt.ui.i18n import set_locale
from morphopt.ui.mainwindow import MainWindow
from morphopt.ui.model.node_types.parts import BoundaryPartNode, CADPartNode, INPPartNode
from morphopt.ui.model.node_types.surfaces import MeshSurfaceNode
from morphopt.ui.model.problem import CADOperationNode


class CaptureWindow(MainWindow):
    def closeEvent(self, event):
        # The capture definition is disposable and never starts a worker.
        event.accept()


def main():
    app = create_application([])
    fonts = CaptureFonts(app)
    set_locale("zh-CN")
    root = Path(__file__).resolve().parents[2]
    examples = root / "docs/examples"
    problem = ProblemLibrary.create_blank("资产预览示例")
    operation = CADOperationNode.create("StepImport", operation_id="import_body")
    operation.filename = "PartDesignExample-Body.step"
    operation.data = base64.b64encode(
        (examples / operation.filename).read_bytes()
    ).decode("ascii")
    problem.add_part(CADPartNode(name="cad_body", children=[operation]))
    problem.add_part(BoundaryPartNode(name="stl_boundary", children=[
        MeshSurfaceNode(
            name="fixed_shell", path_stl=str(examples / "reference-boundary.stl")
        )
    ]))
    problem.add_part(INPPartNode(
        name="inp_mesh", mesh_file=str(examples / "reference-box.inp")
    ))
    window = CaptureWindow()
    window.set_problem(problem)
    window.resize(2100, 1200)
    workbench = window._workbench
    workbench._center.setCurrentIndex(2)
    fonts.apply_to_window(window)
    window.show()

    def capture():
        destination = root / "docs/images/ui/assets"
        destination.mkdir(parents=True, exist_ok=True)
        font_policy = fonts.audit(window)
        pixmap = window.grab()
        if not pixmap.save(str(destination / "geometry-assets.png")):
            raise RuntimeError("Could not save assets screenshot")
        manifest = {
            "file": "geometry-assets.png",
            "description": "资产清单与 STEP 原始几何预览，右侧保留定义的装配预览",
            "sources": [f"../../../examples/{name}" for name in (
                operation.filename, "reference-boundary.stl", "reference-box.inp"
            )],
            "capture": "QWidget.grab() from the running MorphOpt UI",
            "platform": app.platformName(),
            "locale": "zh-CN",
            "pixels": [pixmap.width(), pixmap.height()],
            "font_policy": font_policy,
            "scope": "Documentation capture process only; desktop fonts unchanged",
        }
        (destination / "capture-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(destination / "geometry-assets.png")
        for preview in workbench.asset_view._previews.values():
            preview.viewport.plotter.close()
        workbench.viewer.host.plotter.close()
        app.quit()

    QTimer.singleShot(1800, capture)
    app.exec()


if __name__ == "__main__":
    main()
