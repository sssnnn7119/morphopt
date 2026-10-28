"""Shared Qt actions for tree menus and editor buttons.

Dialog/selection policy belongs here. Model operations remain on the definition
and construction defaults are supplied by the application editing service.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QObject, QProcess, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressDialog,
)

from ..application.edit_history import EditOperation
from ..application.editing import CustomClassSession, DefinitionCommands
from ..application.updaters import UpdaterItems
from ..codegen.custom_classes import custom_options
from ..i18n import localized_message, tr
from ..model.node_types.parts import BoundaryPartNode, CADPartNode
from ..model.problem import (
    CADOperationNode,
    CustomClassNode,
    CustomFunctionNode,
    FEAComponentNode,
    InstanceNode,
    MaterialNode,
    MethodOverrideNode,
    Node,
    PartNode,
    ProblemDefinition,
    SurfaceNode,
)
from ..model.registry import (
    CAD_OPERATION_TYPES,
    LOAD_TYPES,
    PART_TYPES,
)
from ..presentation.labels import (
    node_title,
    node_type_title,
    typed_title,
    updater_section_title_text,
)
from ..presentation.navigation import (
    CustomClassesTreeNode,
    HelperGroupTreeNode,
    UpdaterItemTreeNode,
    UpdaterTreeNode,
)
from ..processes import start_worker
from ..theme import theme_manager
from .file_dialogs import choose_open_file


class DefinitionActions(QObject):
    changed = Signal(object, str)
    selectionRequested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._problem: ProblemDefinition | None = None
        self.commands: DefinitionCommands
        self._cad_conversion: QProcess | None = None

    def set_problem(self, problem: ProblemDefinition) -> None:
        self._problem = problem
        self.commands = DefinitionCommands(problem)

    def _select(self, select: Node | None = None) -> None:
        self.selectionRequested.emit(select)

    def _emit_change(self, node: Node | None, operation: EditOperation) -> None:
        self.changed.emit(node, operation)

    def add_custom_class(self, class_type: str = "override") -> None:
        if self._problem is None:
            return
        session = CustomClassSession(self._problem)
        try:
            catalog = session.catalog()
        except Exception as exc:
            QMessageBox.warning(
                self.parent(),
                tr("ui.widgets.custom_classes.cannot_read_base_classes"),
                str(exc),
            )
            return
        available = sorted(catalog)
        if class_type == "override" and not available:
            return
        dialog = QDialog(self.parent())
        dialog.setWindowTitle(
            tr(
                "ui.widgets.custom_classes.add_new_class"
                if class_type == "new"
                else "ui.widgets.custom_classes.add_override_class"
            )
        )
        layout = QFormLayout(dialog)
        name = QLineEdit("CustomClass")
        layout.addRow(tr("ui.widgets.custom_classes.class_name"), name)
        if class_type == "override":
            base = QComboBox()
            base.addItems(available)
            base.setMinimumWidth(
                theme_manager.palette.layout.widgets.custom_class_base_minimum_width
            )
            layout.addRow(tr("ui.widgets.custom_classes.inherits_from"), base)
        else:
            base = None
        hint_key = (
            "ui.widgets.custom_classes.new_class_hint"
            if class_type == "new"
            else "ui.widgets.custom_classes.override_class_hint"
        )
        hint = QLabel(tr(hint_key))
        hint.setWordWrap(True)
        layout.addRow(hint)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addRow(buttons)
        buttons.rejected.connect(dialog.reject)

        def accept():
            value = name.text().strip()
            try:
                session.validate_name(value)
            except ValueError as exc:
                QMessageBox.warning(
                    dialog, tr("ui.widgets.custom_classes.invalid_class_name"), str(exc)
                )
                return
            dialog.accept()

        buttons.accepted.connect(accept)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        custom = session.add_class(
            name.text().strip(),
            base.currentText() if base is not None else "",
            class_type,
        )
        self._select(custom)
        self._emit_change(custom, "added")

    def remove_custom_class(
        self, node: CustomClassNode | MethodOverrideNode | CustomFunctionNode
    ) -> None:
        if self._problem is None:
            return
        session = CustomClassSession(self._problem)
        if isinstance(node, CustomClassNode) and not self._confirm_remove_dependencies(
            node.name, [custom.name for custom in session.dependent_classes(node)]
        ):
            return
        selected = session.remove(node)
        self._select(selected if selected is not None else CustomClassesTreeNode())
        self._emit_change(node, "deleted")

    def add_helper(self, kind: str) -> Node | None:
        if self._problem is None:
            return None
        node = self.commands.add_helper(kind)
        self._select(node)
        self._emit_change(node, "added")
        return node

    def remove_helper(self, node: Node) -> None:
        if self._problem is None or node.kind not in {
            "helper_variable",
            "helper_function",
        }:
            return
        group = self.commands.remove_helper(node)
        self._select(HelperGroupTreeNode(group))
        self._emit_change(node, "deleted")

    def move_helper(self, node: Node, delta: int) -> None:
        if self._problem is None or node.kind not in {
            "helper_variable",
            "helper_function",
        }:
            return
        if self.commands.move_helper(node, delta):
            self._select(node)
            self._emit_change(node, "modified")

    def populate_updater_menu(self, menu: QMenu) -> None:
        """List concrete targets, shared by tree and editor creation menus."""
        menu.clear()
        targets = (
            self.commands.available_optimizer_targets()
            if self._problem is not None
            else []
        )
        for target in targets:
            action = QAction(node_title(self._problem, target), menu)
            menu.addAction(action)
            action.triggered.connect(
                lambda _checked=False, target=target: self.add_updater(target)
            )
        if not targets:
            action = QAction(tr("ui.component.no_available_targets"), menu)
            menu.addAction(action)
            action.setEnabled(False)

    def add_updater(self, target: PartNode | MaterialNode) -> None:
        """Create an updater for the component the user explicitly selected."""
        if self._problem is None or self._problem.updater is None:
            return
        if target not in self.commands.available_optimizer_targets():
            return
        if isinstance(target, PartNode):
            self._problem.add_geometry_updater(target)
            group, index = "geometry", len(self._problem.updater.geometry) - 1
        else:
            config = self._problem.add_material_updater(target)
            items = UpdaterItems(config, "materials", "constraints", self._problem)
            for item in items.items:
                if item["type"] == "VolFrac":
                    item["params"]["elementname"] = items.default_element_name()
            group, index = "materials", len(self._problem.updater.materials) - 1
        updater = UpdaterTreeNode(self._problem.updater, group, index)
        self._select(updater)
        self._emit_change(updater, "added")

    def remove_geometry_updater(self, node: Node) -> None:
        if self._problem is None or self._problem.updater is None:
            return
        index = node.config_index if isinstance(node, UpdaterTreeNode) else 0
        if 0 <= index < len(self._problem.updater.geometry):
            del self._problem.updater.geometry[index]
        self._select(select=self._problem.updater)
        self._emit_change(node, "deleted")

    def remove_materials_updater(self, node: Node) -> None:
        if self._problem is None or self._problem.updater is None:
            return
        index = node.config_index if isinstance(node, UpdaterTreeNode) else 0
        if 0 <= index < len(self._problem.updater.materials):
            del self._problem.updater.materials[index]
        self._select(select=self._problem.updater)
        self._emit_change(node, "deleted")

    def add_updater_item(
        self, node: UpdaterTreeNode, item_type: str, category: str
    ) -> None:
        config = node.config()
        if config is not None:
            self.commands.add_updater_item(config, item_type, category)
            key = "objective_functions" if category == "objectives" else "constraints"
            item_node = UpdaterItemTreeNode(
                node.updater_parent, node.group, node.config_index, config[key][-1]
            )
            self._select(item_node)
            self._emit_change(item_node, "added")

    def add_symmetry_constraint(self, node: UpdaterTreeNode, item_type: str) -> None:
        config = node.config()
        if (
            self._problem is not None
            and config is not None
            and self.commands.add_symmetry_constraint(
                config,
                item_type,
            )
        ):
            item_node = UpdaterItemTreeNode(
                node.updater_parent,
                node.group,
                node.config_index,
                config["symmetry_constraints"][-1],
            )
            self._select(item_node)
            self._emit_change(item_node, "added")

    def remove_updater_item(self, node: UpdaterItemTreeNode) -> None:
        config = node.config()
        if self._problem is None or config is None:
            return
        UpdaterItems(config, node.section_group, node.category, self._problem).remove(
            node.item
        )
        self._select(
            UpdaterTreeNode(node.updater_parent, node.group, node.config_index)
        )
        self._emit_change(node, "deleted")

    def move_updater_item(self, node: UpdaterItemTreeNode, offset: int) -> None:
        config = node.config()
        if self._problem is None or config is None:
            return
        if UpdaterItems(config, node.section_group, node.category, self._problem).move(
            node.item, offset
        ):
            self._select(node)
            self._emit_change(node, "modified")

    def custom_add_menu(self, menu, candidates, add):
        sub = menu.addMenu(tr("ui.widgets.model_tree.custom_class"))
        options = custom_options(self._problem, candidates)
        shown = set()
        for kind, custom in options:
            if custom.name in shown:
                continue
            shown.add(custom.name)
            action = QAction(
                typed_title(custom.name, candidates[kind].rsplit(".", 1)[-1]), sub
            )
            sub.addAction(action)
            action.triggered.connect(
                lambda _=False, kind=kind, name=custom.name: add(kind, name)
            )
        if not options:
            action = QAction(
                tr("ui.widgets.model_tree.create_a_compatible_custom_class_first"), sub
            )
            sub.addAction(action)
            action.setEnabled(False)

    def set_objective_class(self, custom_class):
        if self._problem is None or self._problem.objective is None:
            return
        self._problem.objective.custom_class = custom_class
        self._problem.class_bindings.pop("ThisController.ObjectiveFunction", None)
        self._select(select=self._problem.objective)
        self._emit_change(self._problem.objective, "modified")

    def add_part(self, itype: str, custom_class: str = "") -> None:
        if self._problem is None:
            return
        if PART_TYPES[itype].custom_only and not custom_class:
            return
        node = self.commands.add_part(itype, custom_class)
        self._select(node)
        self._emit_change(node, "added")

    def copy_part(self, part: Node) -> None:
        if self._problem is None or not isinstance(part, PartNode):
            return
        copy = self._problem.clone_part(part)
        self._select(select=copy)
        self._emit_change(copy, "added")

    def convert_cad_to_boundary(self, part: CADPartNode) -> None:
        """Convert a snapshot in a subprocess and commit one reversible edit."""
        if self._problem is None or self._cad_conversion is not None:
            return
        title = tr("ui.cad.convert_to_boundary")
        problem = self._problem
        directory = TemporaryDirectory(prefix="morphopt_cad_conversion_")
        request = Path(directory.name) / "request.json"
        request.write_text(
            json.dumps(
                {
                    "action": "convert_cad",
                    "problem": problem.to_dict(),
                    "part": part.name,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        process = QProcess(self)
        self._cad_conversion = process
        progress = QProgressDialog(
            tr("ui.cad.converting_to_boundary"),
            tr("ui.files.cancel"),
            0,
            0,
            self.parent(),
        )
        progress.setWindowTitle(title)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)

        def finish(error: str = "") -> None:
            self._cad_conversion = None
            progress.hide()
            try:
                if progress.wasCanceled():
                    return
                if problem is not self._problem or part not in problem.parts():
                    return
                if error:
                    QMessageBox.warning(self.parent(), title, error)
                    return
                try:
                    data = json.loads(
                        (Path(directory.name) / "boundary.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    replacement = BoundaryPartNode.from_dict(data)
                    problem.replace_part(part, replacement)
                except Exception as exc:
                    QMessageBox.warning(self.parent(), title, str(exc))
                    return
                self._select(replacement)
                self._emit_change(replacement, "modified")
            finally:
                directory.cleanup()
                progress.deleteLater()
                process.deleteLater()

        def completed(exit_code: int, status: QProcess.ExitStatus) -> None:
            error = ""
            if exit_code != 0 or status != QProcess.ExitStatus.NormalExit:
                output = (
                    bytes(process.readAllStandardOutput())
                    .decode("utf-8", errors="replace")
                    .strip()
                )
                error = (
                    output.splitlines()[-1]
                    if output
                    else tr("ui.cad.conversion_failed")
                )
            finish(error)

        def failed(error: QProcess.ProcessError) -> None:
            if error == QProcess.ProcessError.FailedToStart:
                finish(process.errorString())

        process.finished.connect(completed)
        process.errorOccurred.connect(failed)
        progress.canceled.connect(process.kill)
        progress.show()
        start_worker(process, request)

    def remove_part(self, part: Node) -> None:
        if self._problem is None or not isinstance(part, PartNode):
            return
        if not self._confirm_remove_bound_updaters(part, "geometry"):
            return
        self._problem.remove_part(part)
        self._select(select=self._problem.geometry)
        self._emit_change(part, "deleted")

    def _confirm_remove_dependencies(self, name: str, dependencies: list[str]) -> bool:
        if not dependencies:
            return True
        return (
            QMessageBox.warning(
                self.parent(),
                tr("ui.component.delete_dependencies_title"),
                tr(
                    "ui.component.delete_dependencies_message",
                    component=name,
                    dependencies="\n".join(f"• {item}" for item in dependencies),
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            == QMessageBox.StandardButton.Yes
        )

    def _confirm_remove_bound_updaters(
        self, component: PartNode | MaterialNode, group: str
    ) -> bool:
        updater = self._problem.updater
        if updater is None:
            return True
        configs = updater.geometry if group == "geometry" else updater.materials
        titles = [
            updater_section_title_text(self._problem, group, config)
            for config in configs
            if config.get("target") is component
        ]
        if not titles:
            return True
        reply = QMessageBox.warning(
            self.parent(),
            tr("ui.component.delete_bound_updaters_title"),
            tr(
                "ui.component.delete_bound_updaters_message",
                component=component.name,
                updaters="\n".join(f"• {title}" for title in titles),
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return reply == QMessageBox.StandardButton.Yes

    def move_part(self, part: Node, delta: int) -> None:
        if self._problem is None or not isinstance(part, PartNode):
            return
        if not self._problem.move_part(part, delta):
            return
        self._select(select=part)
        self._emit_change(part, "modified")

    def move_cad_operation(self, operation: Node, delta: int) -> None:
        if self._problem is None or not isinstance(operation, CADOperationNode):
            return
        if not self._problem.move_cad_operation(operation, delta):
            return
        self._select(select=operation)
        self._emit_change(operation, "modified")

    def add_instance(self, part: Node) -> None:
        if self._problem is None or not isinstance(part, PartNode):
            return
        name = self._problem.suggest_instance_name(part)
        instance = InstanceNode(name=name)
        self._problem.add_instance(part, instance)
        self._select(select=instance)
        self._emit_change(instance, "added")

    def remove_instance(self, instance: Node) -> None:
        if self._problem is None or not isinstance(instance, InstanceNode):
            return
        owner = self._problem.owner_of_instance(instance)
        if owner is None:
            return
        self._problem.remove_instance(instance)
        self._select(select=owner)
        self._emit_change(instance, "deleted")

    def move_instance(self, instance: Node, delta: int) -> None:
        if self._problem is None or not isinstance(instance, InstanceNode):
            return
        if not self._problem.move_instance(instance, delta):
            return
        self._select(select=instance)
        self._emit_change(instance, "modified")

    def add_cad_operation_group(self, group: str, owner: CADPartNode) -> None:
        """Choose an operation type from a CAD feature group."""
        if group == "import":
            self.add_cad_operation("StepImport", owner)
            return
        choices = [
            (operation_type, spec)
            for operation_type, spec in CAD_OPERATION_TYPES.items()
            if spec.group == group
        ]
        if not choices:
            raise ValueError(
                localized_message(
                    "ui.errors.definition_actions.unknown_cad_operation_group_value",
                    value_0=group,
                )
            )
        labels = [
            node_type_title(spec, operation_type) for operation_type, spec in choices
        ]
        title = {
            "primitive": tr("ui.widgets.model_tree.add_primitive"),
            "boolean": tr("ui.widgets.model_tree.add_boolean_operation"),
            "transform": tr("ui.widgets.model_tree.add_transform"),
        }[group]
        label, accepted = QInputDialog.getItem(
            self.parent(), title, tr("ui.widgets.model_tree.type"), labels, 0, False
        )
        if not accepted:
            return
        operation_type = choices[labels.index(label)][0]
        self.add_cad_operation(operation_type, owner)

    def add_cad_operation(self, operation_type: str, owner: Node) -> None:
        if self._problem is None or not isinstance(owner, CADPartNode):
            return
        spec = CAD_OPERATION_TYPES[operation_type]
        operation_id = self.commands.next_operation_id(owner, operation_type)

        overrides: dict[str, object] = {}
        if spec.group == "boolean":
            live_operations = owner.live_cad_operations()
            live_ids = [operation.operation_id for operation in live_operations]
            if len(live_ids) < 2:
                QMessageBox.information(
                    self.parent(),
                    tr("ui.widgets.model_tree.cad_operation"),
                    tr(
                        "ui.widgets.model_tree.boolean_operations_need_two_unconsumed_features"
                    ),
                )
                return
            object_id, accepted = QInputDialog.getItem(
                self.parent(),
                tr("ui.widgets.model_tree.boolean_operation"),
                tr("ui.widgets.model_tree.object_feature"),
                live_ids,
                0,
                False,
            )
            if not accepted:
                return
            tool_id, accepted = QInputDialog.getItem(
                self.parent(),
                tr("ui.widgets.model_tree.boolean_operation"),
                tr("ui.widgets.model_tree.tool_feature"),
                [item for item in live_ids if item != object_id],
                0,
                False,
            )
            if not accepted:
                return
            overrides = {"object_id": object_id, "tool_id": tool_id}
        elif spec.group == "transform":
            live_ids = [
                operation.operation_id for operation in owner.live_cad_operations()
            ]
            if not live_ids:
                QMessageBox.information(
                    self.parent(),
                    tr("ui.widgets.model_tree.cad_operation"),
                    tr("ui.widgets.model_tree.add_an_unconsumed_feature_first"),
                )
                return
            input_id, accepted = QInputDialog.getItem(
                self.parent(),
                tr("ui.widgets.model_tree.transform"),
                tr("ui.widgets.model_tree.input_feature"),
                live_ids,
                0,
                False,
            )
            if not accepted:
                return
            overrides = {"input_id": input_id}
        elif operation_type == "StepImport":
            path = choose_open_file(
                self.parent(),
                tr("ui.widgets.model_tree.select_step_file"),
                "",
                tr("ui.files.step"),
            )
            if not path:
                return
            from torchfea.cad import StepImport

            try:
                imported = StepImport.from_file(operation_id, path)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(
                    self.parent(),
                    tr("ui.widgets.model_tree.step_import_failed"),
                    str(exc),
                )
                return
            overrides = {
                "filename": imported.filename,
                "data": imported.data,
            }

        operation = self.commands.add_cad_operation(
            owner, operation_type, operation_id, **overrides
        )
        self._select(select=operation)
        self._emit_change(operation, "added")

    def remove_cad_operation(self, operation: Node) -> None:
        if self._problem is None or not isinstance(operation, CADOperationNode):
            return
        owner = self._problem.owner_of_cad_operation(operation)
        if owner is None:
            return
        dependents = self._problem.cad_operation_dependents(operation)
        if not self._confirm_remove_dependencies(
            operation.operation_id, [item.operation_id for item in dependents]
        ):
            return
        self._problem.remove_cad_operation(operation)
        self._select(select=owner)
        self._emit_change(operation, "deleted")

    def add_surface(
        self,
        stype: str,
        owner: BoundaryPartNode | None = None,
        custom_class: str = "",
    ) -> None:
        if self._problem is None:
            return
        owner = (
            owner if owner is not None else self._problem.default_surface_part_node()
        )
        if owner is None:
            return
        imported_step: tuple[str, str, str] | None = None
        if stype == "brep_surface":
            path = choose_open_file(
                self.parent(),
                tr("ui.widgets.model_tree.select_step_file"),
                "",
                tr("ui.files.step"),
            )
            if not path:
                return
            try:
                source = Path(path)
                metadata_path = source.with_suffix(".brep.json")
                metadata = (
                    json.loads(metadata_path.read_text(encoding="utf-8"))
                    if metadata_path.exists()
                    else {}
                )
                imported_step = (
                    source.name,
                    base64.b64encode(source.read_bytes()).decode("ascii"),
                    json.dumps(metadata),
                )
            except (OSError, ValueError) as exc:
                QMessageBox.warning(
                    self.parent(),
                    tr("ui.widgets.model_tree.step_import_failed"),
                    str(exc),
                )
                return
        node = self.commands.add_surface(stype, owner, custom_class)
        if imported_step is not None:
            node.filename, node.data, node.brep_metadata = imported_step
        self._select(node)
        self._emit_change(node, "added")

    def copy_surface(self, srf: Node) -> None:
        if self._problem is None or not isinstance(srf, SurfaceNode):
            return
        copy = self._problem.clone_surface(srf)
        self._select(select=copy)
        self._emit_change(copy, "added")

    def remove_surface(self, srf: Node) -> None:
        if self._problem is None or not isinstance(srf, SurfaceNode):
            return
        owner = self._problem.owner_of_surface(srf)
        if owner is None:
            return
        index = owner.surfaces.index(srf)
        dependencies = [
            item["type"]
            for config in (
                self._problem.updater.geometry if self._problem.updater else []
            )
            if self._problem.config_part_node(config) is owner
            for item in config.get("symmetry_constraints", [])
            if item.get("type") != "Custom"
            and index in (item.get("surface_index"), item.get("related_surface_index"))
        ]
        if not self._confirm_remove_dependencies(srf.name, dependencies):
            return
        self._problem.remove_surface(srf)
        self._select(select=owner)
        self._emit_change(srf, "deleted")

    def move_surface(self, srf: Node, delta: int) -> None:
        if self._problem is None or not isinstance(srf, SurfaceNode):
            return
        if not self._problem.move_surface(srf, delta):
            return
        self._select(select=srf)
        self._emit_change(srf, "modified")

    def add_component(self, itype: str, custom_class: str = "") -> None:
        if self._problem is None:
            return
        node = self.commands.add_component(itype, custom_class)
        self._select(node)
        self._emit_change(node, "added")

    def add_material(self, material_type: str, custom_class: str = "") -> None:
        if self._problem is None:
            return
        node = self.commands.add_material(material_type, custom_class)
        self._select(node)
        self._emit_change(node, "added")

    def copy_material(self, material: Node) -> None:
        if self._problem is None or not isinstance(material, MaterialNode):
            return
        copy = self._problem.clone_material(material)
        self._select(select=copy)
        self._emit_change(copy, "added")

    def move_material(self, material: Node, delta: int) -> None:
        if self._problem is None or not isinstance(material, MaterialNode):
            return
        if not self._problem.move_material(material, delta):
            return
        self._select(select=material)
        self._emit_change(material, "modified")

    def remove_material(self, material: Node) -> None:
        if self._problem is None or not isinstance(material, MaterialNode):
            return
        if not self._confirm_remove_bound_updaters(material, "materials"):
            return
        self._problem.remove_material(material)
        self._select(select=self._problem.materials)
        self._emit_change(material, "deleted")

    def copy_component(self, component: Node) -> None:
        if self._problem is None or not isinstance(component, FEAComponentNode):
            return
        # a copied load is a new load: give it a fresh unique name so it does
        # not collide with the original (it starts unset / zero in the steps)
        hint = LOAD_TYPES[component.type].name_hint
        copy = self._problem.clone_component(component, hint)
        self._select(select=copy)
        self._emit_change(copy, "added")

    def move_component(self, component: Node, delta: int) -> None:
        if self._problem is None or not isinstance(component, FEAComponentNode):
            return
        if not self._problem.move_component(component, delta):
            return
        self._select(select=component)
        self._emit_change(component, "modified")

    def remove_component(self, component: Node) -> None:
        if self._problem is None or not isinstance(component, FEAComponentNode):
            return
        self._problem.remove_component(component)
        self._select(select=self._problem.loads)
        self._emit_change(component, "deleted")
