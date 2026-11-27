"""Capture current definition and result pages without modifying user settings.

The default command captures both UI languages on a private virtual display.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import ExitStack
from dataclasses import MISSING, asdict, fields
from pathlib import Path

from number_docs import render, sections

ROOT = Path(__file__).resolve().parents[2]

def write_catalog(directory):
    """Record public field metadata from the same registry as the forms."""
    from morphopt.optcore.modelparams.materials import MaterialModels
    from morphopt.ui.i18n import tr
    from morphopt.ui.model import registry
    from morphopt.ui.model.material_models import MATERIAL_MODEL_PARAMETERS
    from morphopt.ui.model.strategies import STRATEGY_CATALOG

    def field_record(field):
        return {
            **asdict(field),
            "label": tr(field.label_key),
            "help": tr(field.doc_key) if field.doc_key else "",
        }

    catalog = {}
    for group in (
        "PART_TYPES",
        "SURFACE_TYPES",
        "CAD_OPERATION_TYPES",
        "LOAD_TYPES",
        "MATERIAL_TYPES",
        "UPDATER_OBJECTIVES",
        "SURFACE_SYMMETRY_CONSTRAINTS",
        "UPDATER_CONSTRAINTS",
    ):
        catalog[group] = [
            {
                "key": key,
                "class": node.__name__,
                "label": tr(node.label_key),
                "backend": node.backend_class,
                "hidden": node.hidden,
                "custom_only": node.custom_only,
                "factory": getattr(node, "factory", ""),
                "group": getattr(node, "group", ""),
                "num_values": getattr(node, "num_values", None),
                "fields": [field_record(field) for field in node.fields],
                "value_fields": [
                    field_record(field) for field in getattr(node, "value_fields", ())
                ],
            }
            for key, node in getattr(registry, group).items()
        ]
    catalog["MATERIAL_MODELS"] = [
        {
            "name": name,
            "parameters": list(parameters),
            "fields": [
                {
                    "key": field.name,
                    "default": "required"
                    if field.default is MISSING
                    else field.default,
                    "annotation": str(field.type),
                }
                for field in fields(getattr(MaterialModels, name + "Params"))
            ],
        }
        for name, parameters in MATERIAL_MODEL_PARAMETERS.items()
    ]
    catalog["STRATEGIES"] = [asdict(spec) for spec in STRATEGY_CATALOG]
    (directory / "ui-reference/interface-catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def finish_manifest(directory, manifest):
    """Record a language only after checking all guide references."""
    images = {item["file"] for item in manifest["images"]}
    guides = ROOT / "docs" / manifest["locale"]
    for guide in ("ui-quickstart.md", "ui-reference.md"):
        references = re.findall(
            r"!\[[^\]]*\]\(images/([^)]*\.png)\)", (guides / guide).read_text(encoding="utf-8")
        )
        missing = set(references) - images
        if missing:
            raise ValueError(f"{guide}: missing captures: {sorted(missing)}")
    (directory / "current-capture-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

def write_gallery(directory: Path, english: bool) -> None:
    manifest = json.loads((directory / "current-capture-manifest.json").read_text(encoding="utf-8"))
    images = {record["file"] for record in manifest["images"]}
    other = "../../zh-CN/images" if english else "../../en-US/images"
    other_label = "中文" if english else "English"
    title = "UI screenshot gallery" if english else "UI 截图索引"
    lines = [f"# {title}", "", f"[{other_label}]({other}/gallery.md)", ""]
    section_titles = {
        "ui-quickstart": "UI quick start" if english else "UI 快速开始",
        "ui-reference": "UI module reference" if english else "UI 模块与接口参考",
    }
    previous = ""
    previous_section = ""
    for path in sorted(images, key=lambda p: (p.rsplit("/", 1)[0], p)):
        section, group = path.rsplit("/", 1)[0].split("/", 1)
        if section != previous_section:
            lines.extend(["", "## " + section_titles[section], ""])
            previous_section, previous = section, ""
        if previous != group:
            lines.extend(["", "### " + group, ""])
            previous = group
        link = f"- [{Path(path).stem}]({path})"
        if (directory / other / path).is_file():
            link += f" · [{other_label}]({other}/{path})"
        lines.append(link)
    gallery = directory / "gallery.md"
    content = "\n".join(lines) + "\n"
    entries, _ = sections(content, gallery)
    gallery.write_text(render(content, entries), encoding="utf-8")


def capture(locale, archive, output):
    with tempfile.TemporaryDirectory(prefix="morphopt-doc-capture-") as settings, ExitStack() as cleanup:
        os.environ["XDG_CONFIG_HOME"] = settings
        os.environ["MPLCONFIGDIR"] = str(Path(settings) / "matplotlib")
        from capture_fonts import CaptureFonts
        from PySide6.QtCore import QEventLoop, QSettings, QTimer

        from morphopt.ui.app import create_application
        from morphopt.ui.application import ProblemLibrary
        from capture_results import capture_result, capture_simp
        from morphopt.ui.i18n import set_locale
        from morphopt.ui.mainwindow import MainWindow
        from morphopt.ui.model.problem import (
            FEAComponentNode,
            LoadCaseNode,
            SurfaceNode,
        )
        from morphopt.ui.presentation.navigation import (
            UpdaterItemTreeNode,
            UpdaterTreeNode,
        )
        from morphopt.ui.widgets.font_settings import FontSettingsDialog
        from morphopt.ui.widgets.updater_editor import UpdaterStrategyEditor
        from morphopt.ui.widgets.visualization_settings import (
            VisualizationSettingsDialog,
        )

        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(
            QSettings.Format.IniFormat, QSettings.Scope.UserScope, settings
        )
        bending = "examples/bending_actuator/bending_actuator.morph"
        app = create_application([])
        set_locale(locale)
        fonts = CaptureFonts(Path(settings))
        (output / "ui-reference").mkdir(parents=True)
        write_catalog(output)

        class CaptureWindow(MainWindow):
            closed = False

            def closeEvent(self, event):
                if self._observer is not None and not self._observer.close_cleanup():
                    event.ignore()
                    return
                if self._finite_element is not None:
                    self._finite_element.close_cleanup()
                self.closed = True
                event.accept()

        window = CaptureWindow()
        cleanup.callback(lambda: window.close() if not window.closed else None)
        window.resize(1640, 1040)
        window.show()
        manifest = {
            "capture": "Actual QWidget.grab(); no image resampling or text replacement",
            "platform": app.platformName(),
            "locale": locale,
            "images": [],
            "definition_sha256": {},
        }
        source = ""

        def settle():
            loop = QEventLoop()
            QTimer.singleShot(220, loop.quit)
            loop.exec()
            app.processEvents()
            if window.closed:
                raise SystemExit("Screenshot capture cancelled.")

        def save(name, description, widget=None):
            settle()
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            subject = widget or window
            if not subject.isVisible():
                raise ValueError(f"Cannot capture hidden widget: {name}")
            pixmap = subject.grab()
            if not pixmap.save(str(target)):
                raise RuntimeError(f"Could not save {target}")
            manifest["images"].append(
                {
                    "file": name,
                    "description": description,
                    "source": source,
                    "dpr": pixmap.devicePixelRatio(),
                    "pixels": [pixmap.width(), pixmap.height()],
                }
            )
            print(name, flush=True)

        def load(relative):
            nonlocal source
            source = relative
            manifest["definition_sha256"][relative] = hashlib.sha256(
                (ROOT / relative).read_bytes()
            ).hexdigest()
            problem = ProblemLibrary.load(ROOT / relative, issues=[])
            window.set_problem(problem, path=str(ROOT / relative))
            settle()
            window._workbench.tree.expandAll()
            return problem, window._workbench

        def select(wb, node):
            wb._center.setCurrentIndex(0)
            wb.tree.select_node(node)
            wb._on_node_selected(node)
            settle()

        problem, wb = load("examples/bending_actuator/bending_actuator.morph")
        part = problem.parts()[0]
        for node, name, description in [
            (
                part,
                "geometry/boundary-part",
                "BoundaryPart, mesh settings and instance",
            ),
            (
                part.surfaces[0],
                "geometry/bsp-outer-surface",
                "Outer BSP geometry and update flag",
            ),
            (
                part.surfaces[1],
                "geometry/bsp-inner-cavity",
                "Inner BSP geometry and position components",
            ),
            (
                part.instances[0],
                "geometry/instance-pose",
                "Instance translation and rotation components",
            ),
            (problem.loads, "loads/pressure", "Pressure and assembly"),
            (
                next(n for n in problem.fea_components() if n.type == "ReferencePoint"),
                "loads/reference-point",
                "Reference-point X/Y/Z position",
            ),
            (
                next(n for n in problem.fea_components() if n.type == "Couple"),
                "loads/coupling",
                "Reference-point coupling",
            ),
            (
                next(
                    n for n in problem.fea_components() if n.type == "BoundaryCondition"
                ),
                "loads/fixed-boundary",
                "Fixed displacement directions",
            ),
            (
                LoadCaseNode(problem, "load_case_1"),
                "loads/pressure-load-case",
                "Named load-case interface and pressure amplitude",
            ),
            (
                problem.material_nodes()[0],
                "materials/homogeneous-material",
                "Material assignment and constitutive parameters",
            ),
            (
                problem.objective,
                "objectives/displacement-objective-and-metric",
                "Squared error to ry=2 and recorded metrics",
            ),
            (
                problem.solver,
                "solver/task-configuration",
                "Worker devices and ordered load-case groups",
            ),
            (
                problem.root,
                "solver/run-settings",
                "Task name, result directory and device",
            ),
        ]:
            select(wb, node)
            save("ui-quickstart/" + name + ".png", description)
        updater = problem.updater
        select(wb, UpdaterTreeNode(updater, "geometry", 0))
        save(
            "ui-quickstart/updaters/geometry-updater.png",
            "Geometry updater, maximum step length and update strategy",
            wb.updater_editor,
        )
        save(
            "ui-quickstart/updaters/geometry-strategies.png",
            "AdaptiveShapeUpdate parameters",
            wb.updater_editor.findChild(UpdaterStrategyEditor),
        )
        config = updater.geometry[0]
        for group, key, filename in [
            ("geometry_objectives", "objective_functions", "shape-derivative"),
            ("geometry_symmetry", "symmetry_constraints", "mirror-symmetry"),
            ("geometry_penalty", "constraints", "fairness"),
        ]:
            select(wb, UpdaterItemTreeNode(updater, group, 0, config[key][0]))
            save("ui-quickstart/updaters/" + filename + ".png", config[key][0]["type"])
        for item in config["constraints"][1:]:
            select(wb, UpdaterItemTreeNode(updater, "geometry_penalty", 0, item))
            save(
                "ui-quickstart/updaters/"
                + {"Distance": "minimum-distance", "Cylinder": "cylinder-envelope"}[
                    item["type"]
                ]
                + ".png",
                item["type"],
            )
        original_objective = config["objective_functions"][0]
        linear = {"type": "ShapeDerivative", "params": {}}
        config["objective_functions"][0] = linear
        wb.set_problem(problem)
        select(wb, UpdaterItemTreeNode(updater, "geometry_objectives", 0, linear))
        save(
            "ui-reference/updaters/geometry/linear-shape-derivative.png",
            "Original unscaled first-order shape objective",
        )
        config["objective_functions"][0] = original_objective

        # Demonstration interfaces are separate from the solved example.
        penalty = FEAComponentNode.create(
            "PenaltyDoF", name="lock_tip", obj_type="rp", obj_name="RP_1", s=4
        )
        problem.loads.add_component(penalty)
        wb.set_problem(problem)
        select(wb, penalty)
        save(
            "ui-reference/loads/penalty-degree-of-freedom.png",
            "Reference-point constraint with six named DoFs",
        )
        penalty.obj_type = "instance"
        penalty.obj_name = "part1-1"
        penalty.s = 17
        wb.set_problem(problem)
        select(wb, penalty)
        save(
            "ui-reference/loads/penalty-node-direction.png",
            "Instance constraint: node 5, Z displacement",
        )
        spring = FEAComponentNode.create(
            "SpringToGround", name="spring_tip", rp_name="RP_1"
        )
        problem.loads.add_component(spring)
        problem.steps.step_values["load_case_1"]["spring_tip"] = [
            1.0,
            10.0,
            0.0,
            0.0,
            90.0,
        ]
        wb.set_problem(problem)
        select(wb, LoadCaseNode(problem, "load_case_1"))
        save(
            "ui-reference/loads/spring-load-case.png",
            "Named pressure, penalty stiffness/target and spring stiffness/rest length/anchor coordinates",
        )

        problem, wb = load("examples/workspace_objective/workspace_objective.morph")
        select(wb, problem.objective)
        save(
            "ui-reference/objectives/workspace-objective.png",
            "Workspace inputs, upper bounds and boundary quadrature",
        )
        select(wb, LoadCaseNode(problem, next(iter(problem.steps.step_values))))
        save(
            "ui-reference/loads/workspace-load-cases.png",
            "Generated Gauss-point load cases appear in the model tree",
        )
        select(wb, problem.solver)
        save(
            "ui-reference/solver/process-groups.png",
            "Ordered process groups; one case per group by default",
        )

        # Replace the obsolete geometry/fairness fields in earlier illustrations.
        problem, wb = load("examples/bending_actuator/bending_actuator.morph")
        part = problem.parts()[0]
        for kind, filename, options in [
            ("cpgeo_cylinder", "cpgeo-cylinder", {"fix_end_caps": False}),
            ("cpgeo_sphere", "cpgeo-sphere", {}),
        ]:
            problem.remove_surface(part.surfaces[-1])
            surface = SurfaceNode.create(kind, r0=4.0, seed_size=2.0, **options)
            problem.add_surface(surface, part=part)
            wb.set_problem(problem)
            select(wb, surface)
            save(
                "ui-reference/geometry/" + filename + ".png",
                "CPGEO geometry; optimization thresholds belong to Fairness",
            )
        problem, wb = load("examples/bending_actuator/bending_actuator.morph")
        material = problem.material_nodes()[0]
        material.material_model = "Ogden"
        wb.set_problem(problem)
        select(wb, material)
        save(
            "ui-reference/materials/ogden-model.png",
            "Ogden alpha edited as individual list items",
        )

        source = "Built-in simp template (form demonstration)"
        problem = ProblemLibrary.create("simp")
        material = next(node for node in problem.material_nodes() if node.is_updatable)
        material.elementname = ""
        window.set_problem(problem)
        wb = window._workbench
        wb.viewer.view_combo.setCurrentIndex(wb.viewer.view_combo.findData("part"))
        select(wb, material)
        save(
            "ui-reference/materials/simp-material.png",
            "SIMP bounding-box components and constitutive parameters",
        )
        config = problem.updater.materials[0]
        for key, filename in [
            ("objective_functions", "sensitivity"),
            ("constraints", "control-bounds"),
        ]:
            group = (
                "materials_objectives"
                if key == "objective_functions"
                else "materials_penalty"
            )
            select(wb, UpdaterItemTreeNode(problem.updater, group, 0, config[key][0]))
            save(
                "ui-reference/updaters/material/" + filename + ".png",
                config[key][0]["type"],
            )
        volume = next(
            item for item in config["constraints"] if item["type"] == "VolFrac"
        )
        select(wb, UpdaterItemTreeNode(problem.updater, "materials_penalty", 0, volume))
        save(
            "ui-reference/updaters/material/volume-fraction.png",
            "Volume-fraction constraint and actual element block",
        )

        problem, wb = load("examples/step_face/step_face.morph")
        select(wb, problem.parts()[0].surfaces[0])
        save(
            "ui-reference/geometry/brep-design-face.png",
            "Explicit face selection and control-point spacing",
        )
        wb._center.setCurrentIndex(1)
        save(
            "ui-quickstart/custom-code/generated-source.png",
            "Generated script references external STEP and metadata assets",
        )
        wb._center.setCurrentIndex(2)
        save(
            "ui-reference/geometry/brep-assets.png",
            "BREP geometry and metadata in the asset browser",
        )

        dialog = FontSettingsDialog(window)
        dialog.show()
        save(
            "ui-reference/appearance/font-settings.png",
            "Embedded font selection, preview, Apply/Confirm/Cancel",
            dialog,
        )
        dialog.reject()
        visual = VisualizationSettingsDialog(window)
        visual.show()
        save(
            "ui-reference/appearance/visualization-settings.png",
            "Global projection, illumination, material and shared view controls",
            visual,
        )
        visual.reject()

        from capture_reference import capture_reference
        def show(problem, description):
            nonlocal source
            source = description
            window.set_problem(problem)
            settle()
            wb.tree.expandAll()

        capture_reference(window, ROOT, show, select, save)
        source = "CPU SIMP quick start, mesh size 4"
        capture_simp(window, Path(settings) / "simp", save, settle)
        window.show_definition()
        problem, wb = load(bending)
        source = archive.name
        count = capture_result(window, archive, save, settle)
        manifest["completed_run"] = {
            "source": source, "completed_iterations": count,
            "script_sha256": hashlib.sha256(
                (archive / "scripts/MAIN_SCRIPT_FOR_RESTART.py").read_bytes()
            ).hexdigest(),
        }
        manifest["font_policy"] = fonts.audit()
        finish_manifest(output, manifest)
        print(f"Captured {len(manifest['images'])} screenshots ({locale})", flush=True)
        window.close()
        app.processEvents()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, help="Reuse a completed bending-actuator archive")
    parser.add_argument("--language", choices=("both", "zh-CN", "en-US"), default="both")
    parser.add_argument("--visible", action="store_true", help="Show capture on the current desktop")
    parser.add_argument("--stage", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    archive = args.result.resolve() if args.result else None
    if archive and not (archive / "log/history_record.csv").is_file():
        parser.error("--result must be a completed bending-actuator archive")
    os.chdir(ROOT)
    if args.stage:
        capture(args.language, archive, args.stage)
        return
    command = [sys.executable, str(Path(__file__).resolve())]
    if not args.visible:
        from capture_display import run_hidden

        options = ["--language", args.language, "--visible"]
        if archive:
            options += ["--result", str(archive)]
        run_hidden(command + options)
        return

    with tempfile.TemporaryDirectory(prefix="morphopt-doc-run-") as tmp:
        directory = Path(tmp)
        env = dict(os.environ, OMP_NUM_THREADS="2", MKL_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2")
        if archive is None:
            print("Preparing two CPU iterations before capturing the UI…", flush=True)
            bending = directory / "bending"
            bending.mkdir()
            definition = ROOT / "examples/bending_actuator/bending_actuator.morph"
            subprocess.run([sys.executable, str(Path(__file__).with_name("capture_results.py")), str(definition)],
                           cwd=bending, env=env, check=True)
            archive, = (bending / "results").iterdir()
        languages = ("zh-CN", "en-US") if args.language == "both" else (args.language,)
        for language in languages:
            subprocess.run(command + ["--stage", str(directory / language), "--language", language,
                                      "--result", str(archive)], env=env, check=True)
        if len(languages) == 2:
            def image_paths(language):
                return {p.relative_to(directory / language) for p in (directory / language).rglob("*.png")}
            if image_paths("zh-CN") != image_paths("en-US"):
                raise ValueError("The two languages produced different screenshot sets")
        for language in languages:
            dest = ROOT / "docs" / language / "images"
            shutil.copytree(directory / language, dest, dirs_exist_ok=True)
            print(f"Saved {language} screenshots to {dest}", flush=True)
        for language in ("zh-CN", "en-US"):
            destination = ROOT / "docs" / language / "images"
            if (destination / "current-capture-manifest.json").is_file():
                write_gallery(destination, english=language == "en-US")


if __name__ == "__main__":
    main()
