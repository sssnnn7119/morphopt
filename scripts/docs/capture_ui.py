"""Capture current definition and result pages without modifying user settings.

Run with the project's Python environment. Qt's offscreen backend supports
headless capture; VTK additionally requires an available OpenGL/EGL backend.
"""

import argparse
import csv
import hashlib
import json
import os
import tempfile
from dataclasses import MISSING, asdict, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def write_catalog():
    """Record public field metadata from the same registry as the forms."""
    from morphopt.optcore.modelparams.materials import MaterialModels
    from morphopt.ui.i18n import tr
    from morphopt.ui.model import registry
    from morphopt.ui.model.material_models import MATERIAL_MODEL_PARAMETERS
    from morphopt.ui.model.strategies import STRATEGY_CATALOG

    def field_record(field):
        return {**asdict(field), 'label': tr(field.label_key),
                'help': tr(field.doc_key) if field.doc_key else ''}

    catalog = {}
    for group in ('PART_TYPES', 'SURFACE_TYPES', 'CAD_OPERATION_TYPES', 'LOAD_TYPES',
                  'MATERIAL_TYPES', 'UPDATER_OBJECTIVES', 'SURFACE_SYMMETRY_CONSTRAINTS',
                  'UPDATER_CONSTRAINTS'):
        catalog[group] = [
            {'key': key, 'class': node.__name__, 'label': tr(node.label_key),
             'backend': node.backend_class, 'hidden': node.hidden,
             'custom_only': node.custom_only,
             'factory': getattr(node, 'factory', ''),
             'group': getattr(node, 'group', ''),
             'num_values': getattr(node, 'num_values', None),
             'fields': [field_record(field) for field in node.fields],
             'value_fields': [field_record(field) for field in getattr(node, 'value_fields', ())]}
            for key, node in getattr(registry, group).items()
        ]
    catalog['MATERIAL_MODELS'] = [
        {'name': name, 'parameters': list(parameters),
         'fields': [{'key': field.name,
                     'default': 'required' if field.default is MISSING else field.default,
                     'annotation': str(field.type)}
                    for field in fields(getattr(MaterialModels, name + 'Params'))]}
        for name, parameters in MATERIAL_MODEL_PARAMETERS.items()
    ]
    catalog['STRATEGIES'] = {
        key: [asdict(spec) for spec in values] for key, values in STRATEGY_CATALOG.items()
    }
    (ROOT / 'docs/images/ui-reference/interface-catalog.json').write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_manifest(manifest):
    """Keep replaced files' legacy records linked to the current capture set."""
    destination = ROOT / 'docs/images/current-capture-manifest.json'
    destination.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for prefix in ('ui/', 'ui-reference/'):
        path = ROOT / 'docs/images' / prefix / 'capture-manifest.json'
        previous = json.loads(path.read_text(encoding='utf-8'))
        updated = {item['file'].removeprefix(prefix): item for item in manifest['images']
                   if item['file'].startswith(prefix)}
        for item in previous.get('images', []):
            if item['file'] in updated:
                current = updated[item['file']]
                item.update({key: current[key] for key in ('description', 'pixels', 'source', 'dpr')})
                item['recaptured_for_current_branch'] = True
        previous['current_capture_manifest'] = '../current-capture-manifest.json'
        path.write_text(json.dumps(previous, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result', type=Path, help='A completed bending-actuator run')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='morphopt-doc-capture-') as settings:
        os.environ['XDG_CONFIG_HOME'] = settings
        os.environ['MPLCONFIGDIR'] = str(Path(settings) / 'matplotlib')
        from PySide6.QtCore import QEventLoop, QSettings, QTimer
        from capture_fonts import CaptureFonts
        from morphopt.ui.app import create_application
        from morphopt.ui.application import ProblemLibrary
        from morphopt.ui.i18n import set_locale
        from morphopt.ui.mainwindow import MainWindow
        from morphopt.ui.model.problem import FEAComponentNode, LoadCaseNode, SurfaceNode
        from morphopt.ui.presentation.navigation import UpdaterItemTreeNode, UpdaterTreeNode
        from morphopt.ui.widgets.font_settings import FontSettingsDialog
        from morphopt.ui.widgets.visualization_settings import VisualizationSettingsDialog

        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, settings)
        app = create_application([])
        set_locale('zh-CN')
        fonts = CaptureFonts()
        write_catalog()

        class CaptureWindow(MainWindow):
            def closeEvent(self, event):
                event.accept()

        window = CaptureWindow()
        window.resize(1640, 1040)
        window.show()
        manifest = {'capture': 'Actual QWidget.grab(); no image resampling or text replacement',
                    'platform': app.platformName(), 'images': [], 'definition_sha256': {}}
        source = ''

        def settle():
            loop = QEventLoop()
            QTimer.singleShot(220, loop.quit)
            loop.exec()
            app.processEvents()

        def save(name, description, widget=None):
            settle()
            target = ROOT / 'docs/images' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            pixmap = (widget or window).grab()
            if not pixmap.save(str(target)):
                raise RuntimeError(f'Could not save {target}')
            manifest['images'].append({'file': name, 'description': description,
                                       'source': source, 'dpr': pixmap.devicePixelRatio(),
                                       'pixels': [pixmap.width(), pixmap.height()]})
            print(name, flush=True)

        def load(relative):
            nonlocal source
            source = relative
            manifest['definition_sha256'][relative] = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            problem = ProblemLibrary.load(ROOT / relative, issues=[])
            window.set_problem(problem)
            settle()
            window._workbench.tree.expandAll()
            return problem, window._workbench

        def select(wb, node):
            wb._center.setCurrentIndex(0)
            wb.tree.select_node(node)
            wb._on_node_selected(node)
            settle()

        problem, wb = load('examples/bending_actuator/bending_actuator.morph')
        part = problem.parts()[0]
        for node, name, description in [
            (part, 'geometry/boundary-part', 'BoundaryPart, mesh settings and instance'),
            (part.surfaces[0], 'geometry/bsp-outer-surface', 'Outer BSP geometry and update flag'),
            (part.surfaces[1], 'geometry/bsp-inner-cavity', 'Inner BSP geometry and position components'),
            (part.instances[0], 'geometry/instance-pose', 'Instance translation and rotation components'),
            (problem.loads, 'loads/pressure', 'Pressure and assembly'),
            (next(n for n in problem.fea_components() if n.type == 'ReferencePoint'), 'loads/reference-point', 'Reference-point X/Y/Z position'),
            (next(n for n in problem.fea_components() if n.type == 'Couple'), 'loads/coupling', 'Reference-point coupling'),
            (next(n for n in problem.fea_components() if n.type == 'BoundaryCondition'), 'loads/fixed-boundary', 'Fixed displacement directions'),
            (LoadCaseNode(problem, 'load_case_1'), 'loads/pressure-load-case', 'Named load-case interface and pressure amplitude'),
            (problem.material_nodes()[0], 'materials/homogeneous-material', 'Material assignment and constitutive parameters'),
            (problem.objective, 'objectives/displacement-objective-and-metric', 'Squared error to ry=2 and recorded metrics'),
            (problem.solver, 'solver/task-configuration', 'CPU worker and ordered load-case groups'),
            (problem.root, 'solver/run-settings', 'Task name, result directory and device'),
        ]:
            select(wb, node)
            save('ui/' + name + '.png', description)
        updater = problem.updater
        select(wb, UpdaterTreeNode(updater, 'geometry', 0))
        save('ui/updaters/geometry-updater.png', 'Step limits and event-driven penalty strategy')
        save('ui/updaters/geometry-strategies.png', 'AdaptiveShapeWeights with five current parameters')
        config = updater.geometry[0]
        for group, key, filename in [
            ('geometry_objectives', 'objective_functions', 'shape-derivative'),
            ('geometry_symmetry', 'symmetry_constraints', 'mirror-symmetry'),
            ('geometry_penalty', 'constraints', 'fairness'),
        ]:
            select(wb, UpdaterItemTreeNode(updater, group, 0, config[key][0]))
            save('ui/updaters/' + filename + '.png', config[key][0]['type'])
        for item in config['constraints'][1:]:
            select(wb, UpdaterItemTreeNode(updater, 'geometry_penalty', 0, item))
            save('ui/updaters/' + {'Distance': 'minimum-distance', 'Cylinder': 'cylinder-envelope'}[item['type']] + '.png', item['type'])
        original_objective = config['objective_functions'][0]
        linear = {'type': 'ShapeDerivative', 'params': {}}
        config['objective_functions'][0] = linear
        wb.set_problem(problem)
        select(wb, UpdaterItemTreeNode(updater, 'geometry_objectives', 0, linear))
        save('ui-reference/updaters/geometry/linear-shape-derivative.png', 'Original unscaled first-order shape objective')
        config['objective_functions'][0] = original_objective

        # Demonstration interfaces are separate from the solved example.
        penalty = FEAComponentNode.create('PenaltyDoF', name='lock_tip', obj_type='rp',
                                          obj_name='RP_1', s=4)
        problem.loads.add_component(penalty)
        wb.set_problem(problem)
        select(wb, penalty)
        save('ui-reference/loads/penalty-degree-of-freedom.png', 'Reference-point constraint with six named DoFs')
        penalty.obj_type = 'instance'
        penalty.obj_name = 'part1-1'
        penalty.s = 17
        wb.set_problem(problem)
        select(wb, penalty)
        save('ui-reference/loads/penalty-node-direction.png', 'Instance constraint: node 5, Z displacement')
        spring = FEAComponentNode.create('SpringToGround', name='spring_tip', rp_name='RP_1')
        problem.loads.add_component(spring)
        problem.steps.step_values['load_case_1']['spring_tip'] = [1.0, 10.0, 0.0, 0.0, 90.0]
        wb.set_problem(problem)
        select(wb, LoadCaseNode(problem, 'load_case_1'))
        save('ui-reference/loads/spring-load-case.png', 'Named pressure, penalty stiffness/target and spring stiffness/rest length/anchor coordinates')

        problem, wb = load('examples/workspace_objective/workspace_objective.morph')
        select(wb, problem.objective)
        save('ui-reference/objectives/workspace-objective.png', 'Workspace inputs, upper bounds and boundary quadrature')
        select(wb, LoadCaseNode(problem, next(iter(problem.steps.step_values))))
        save('ui-reference/loads/workspace-load-cases.png', 'Generated Gauss-point load cases appear in the model tree')
        select(wb, problem.solver)
        save('ui-reference/solver/process-groups.png', 'Ordered process groups; one case per group by default')

        # Replace the obsolete geometry/fairness fields in earlier illustrations.
        problem, wb = load('examples/bending_actuator/bending_actuator.morph')
        part = problem.parts()[0]
        for kind, filename in [('cpgeo_cylinder', 'cpgeo-cylinder'), ('cpgeo_sphere', 'cpgeo-sphere')]:
            problem.remove_surface(part.surfaces[-1])
            surface = SurfaceNode.create(kind, r0=4.0, seed_size=2.0)
            problem.add_surface(surface, part=part)
            wb.set_problem(problem)
            select(wb, surface)
            save('ui-reference/geometry/' + filename + '.png', 'CPGEO geometry; optimization thresholds belong to Fairness')
        problem, wb = load('examples/bending_actuator/bending_actuator.morph')
        material = problem.material_nodes()[0]
        material.material_model = 'Ogden'
        wb.set_problem(problem)
        select(wb, material)
        save('ui-reference/materials/ogden-model.png', 'Ogden alpha edited as individual list items')

        source = 'Built-in simp template (form demonstration)'
        problem = ProblemLibrary.create('simp')
        material = next(node for node in problem.material_nodes() if node.is_updatable)
        material.elementname = ''
        window.set_problem(problem)
        wb = window._workbench
        wb.viewer.view_combo.setCurrentIndex(wb.viewer.view_combo.findData('part'))
        select(wb, material)
        save('ui-reference/materials/simp-material.png', 'SIMP bounding-box components and constitutive parameters')
        config = problem.updater.materials[0]
        for key, filename in [('objective_functions', 'sensitivity'), ('constraints', 'control-bounds')]:
            group = 'materials_objectives' if key == 'objective_functions' else 'materials_penalty'
            select(wb, UpdaterItemTreeNode(problem.updater, group, 0, config[key][0]))
            save('ui-reference/updaters/material/' + filename + '.png', config[key][0]['type'])
        volume = next(item for item in config['constraints'] if item['type'] == 'VolFrac')
        select(wb, UpdaterItemTreeNode(problem.updater, 'materials_penalty', 0, volume))
        save('ui-reference/updaters/material/volume-fraction.png', 'Volume-fraction constraint and actual element block')

        problem, wb = load('examples/step_face/step_face.morph')
        select(wb, problem.parts()[0].surfaces[0])
        save('ui-reference/geometry/brep-design-face.png', 'Explicit face selection and control-point spacing')
        wb._center.setCurrentIndex(1)
        save('ui/custom-code/generated-source.png', 'Generated script references external STEP and metadata assets')
        wb._center.setCurrentIndex(2)
        save('ui-reference/geometry/brep-assets.png', 'BREP geometry and metadata in the asset browser')

        dialog = FontSettingsDialog(window)
        dialog.show()
        save('ui-reference/appearance/font-settings.png', 'Embedded font selection, preview, Apply/Confirm/Cancel', dialog)
        dialog.reject()
        visual = VisualizationSettingsDialog(window)
        visual.show()
        save('ui-reference/appearance/visualization-settings.png',
             'Global projection, illumination, material and shared view controls', visual)
        visual.reject()

        if args.result:
            problem, wb = load('examples/bending_actuator/bending_actuator.morph')
            source = 'Completed run of examples/bending_actuator/bending_actuator.py; CPU'
            window._ensure_observer()
            observer = window._observer
            observer.open_result(str(args.result.resolve()))
            with (args.result / 'log/history_record.csv').open(encoding='utf-8') as stream:
                manifest['completed_run'] = {
                    'definition': 'examples/bending_actuator/bending_actuator.py',
                    'device': 'cpu', 'completed_iterations': len(list(csv.DictReader(stream))),
                    'objective': '(ry - 2) ** 2',
                    'script_sha256': hashlib.sha256((ROOT / 'examples/bending_actuator/bending_actuator.py').read_bytes()).hexdigest(),
                }
            window._show_analysis()
            panel = observer.panel
            panel.options.setCurrentRow(0)
            save('ui/optimization/history-and-metrics.png', 'Actual completed iterations, named metrics, timing and plot selector')
            panel.options.setCurrentRow(1)
            save('ui/optimization/optimization-log.png', 'Saved .log browser and independent follow control')
            panel.options.setCurrentRow(2)
            save('ui/optimization/saved-design.png', 'Saved boundary design and current-view export controls')
            page = panel._updatable_structure_page
            for index in range(page.view_selector.count()):
                if 'control' in str(page.view_selector.itemData(index)):
                    page.view_selector.setCurrentIndex(index)
                    break
            save('ui/optimization/surface-control-net.png', 'Individual boundary surface and control net')
            from morphopt.ui.widgets.history_export import SurfaceExportDialog, HistoryGifExportDialog
            selections, title = panel._current_surface_export()
            surface_dialog = SurfaceExportDialog(panel.path_result, panel.iteration,
                                                selections, title, window)
            surface_dialog.show()
            save('ui/optimization/export-current-surfaces.png',
                 'Geometry export uses the current component, surface and iteration', surface_dialog)
            surface_dialog.reject()
            gif_dialog = HistoryGifExportDialog(panel.path_result, panel.slider.maximum(),
                                                'design', (), panel._results.fea_components(),
                                                *panel._history_gif_view(), window)
            gif_dialog.show()
            save('ui/optimization/export-history-gif.png',
                 'History GIF target, iteration range and frame rate', gif_dialog)
            gif_dialog.reject()
            panel.options.setCurrentRow(panel.options.count() - 1)
            save('ui/optimization/load-case-deformation.png', 'Saved deformation for the named pressure case')
        manifest['font_policy'] = fonts.audit()
        write_manifest(manifest)
        window.close()
        app.processEvents()
        os._exit(0)


if __name__ == '__main__':
    main()
