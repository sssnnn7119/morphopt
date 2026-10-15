"""Shared Qt actions for tree menus and editor buttons.

Dialog/selection policy belongs here. Model operations remain on the definition
and construction defaults are supplied by the application editing service.
"""
from __future__ import annotations
from ..i18n import localized_message
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox,
)
from ..i18n import tr
from ..codegen.custom_classes import custom_options
from ..application.editing import CustomClassSession, DefinitionCommands
from ..application.updaters import UpdaterItems
from ..model.problem import (
    Node,
    ProblemDefinition,
    CADOperationNode,
    CustomClassNode,
    InstanceNode,
    FEAComponentNode,
    MaterialNode,
    MethodOverrideNode,
    PartNode,
    SurfaceNode,
)
from ..model.schemas import CAD_OPERATION_TYPES, INTERFACE_TYPES, PART_INTERFACE_TYPES
from ..presentation.navigation import CustomClassesTreeNode, HelperGroupTreeNode, UpdaterItemTreeNode, UpdaterTreeNode
from ..presentation.labels import schema_label, typed_title, node_title


class DefinitionActions(QObject):
    changed = Signal(object)
    selectionRequested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._problem: ProblemDefinition | None = None
        self.commands: DefinitionCommands

    def set_problem(self, problem: ProblemDefinition) -> None:
        self._problem = problem
        self.commands = DefinitionCommands(problem)

    def _select(self, select: Node | None = None) -> None:
        self.selectionRequested.emit(select)

    def add_custom_class(self) -> None:
        if self._problem is None:
            return
        session = CustomClassSession(self._problem)
        try:
            catalog = session.catalog()
        except Exception as exc:
            QMessageBox.warning(self.parent(), tr('ui.widgets.custom_classes.cannot_read_base_classes'), str(exc))
            return
        available = sorted(catalog)
        if not available:
            return
        dialog = QDialog(self.parent())
        dialog.setWindowTitle(tr('ui.widgets.custom_classes.add_custom_class'))
        layout = QFormLayout(dialog)
        name = QLineEdit("CustomClass")
        base = QComboBox()
        base.addItems(available)
        base.setMinimumWidth(400)
        layout.addRow(tr('ui.widgets.custom_classes.class_name'), name)
        layout.addRow(tr('ui.widgets.custom_classes.inherits_from'), base)
        hint = QLabel(tr('ui.widgets.custom_classes.custom_classes_are_module_level_definitions_select_one_using_a_model_nod'))
        hint.setWordWrap(True)
        layout.addRow(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addRow(buttons)
        buttons.rejected.connect(dialog.reject)

        def accept():
            value = name.text().strip()
            try:
                session.validate_name(value)
            except ValueError as exc:
                QMessageBox.warning(dialog, tr('ui.widgets.custom_classes.invalid_class_name'), str(exc))
                return
            dialog.accept()

        buttons.accepted.connect(accept)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        custom = session.add_class(name.text().strip(), base.currentText())
        self._select(custom)
        self.changed.emit(custom)

    def remove_custom_class(self, node: CustomClassNode | MethodOverrideNode) -> None:
        if self._problem is None:
            return
        selected = CustomClassSession(self._problem).remove(node)
        self._select(selected if selected is not None else CustomClassesTreeNode())
        self.changed.emit(node)

    def add_helper(self, kind: str) -> Node | None:
        if self._problem is None:
            return None
        node = self.commands.add_helper(kind)
        self._select(node)
        self.changed.emit(node)
        return node

    def remove_helper(self, node: Node) -> None:
        if self._problem is None or node.kind not in {"helper_variable", "helper_function"}:
            return
        group = self.commands.remove_helper(node)
        self._select(HelperGroupTreeNode(group))
        self.changed.emit(node)

    def move_helper(self, node: Node, delta: int) -> None:
        if self._problem is None or node.kind not in {"helper_variable", "helper_function"}:
            return
        if self.commands.move_helper(node, delta):
            self._select(node)
            self.changed.emit(node)

    def populate_updater_menu(self, menu: QMenu) -> None:
        """List concrete targets, shared by tree and editor creation menus."""
        menu.clear()
        targets = self.commands.available_optimizer_targets() if self._problem is not None else []
        for target in targets:
            action = menu.addAction(node_title(self._problem, target))
            action.triggered.connect(lambda _checked=False, target=target: self.add_updater(target))
        if not targets:
            action = menu.addAction(tr("ui.component.no_available_targets"))
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
            self._problem.add_material_updater(target)
            group, index = "materials", len(self._problem.updater.materials) - 1
        self._select(UpdaterTreeNode(self._problem.updater, group, index))
        self.changed.emit(self._problem.updater)

    def remove_geometry_updater(self, node: Node) -> None:
        if self._problem is None or self._problem.updater is None:
            return
        index = node.config_index if isinstance(node, UpdaterTreeNode) else 0
        if 0 <= index < len(self._problem.updater.geometry):
            del self._problem.updater.geometry[index]
        self._select(select=self._problem.updater)
        self.changed.emit(node)

    def remove_materials_updater(self, node: Node) -> None:
        if self._problem is None or self._problem.updater is None:
            return
        index = node.config_index if isinstance(node, UpdaterTreeNode) else 0
        if 0 <= index < len(self._problem.updater.materials):
            del self._problem.updater.materials[index]
        self._select(select=self._problem.updater)
        self.changed.emit(node)

    def add_updater_item(self, node: UpdaterTreeNode, item_type: str, category: str) -> None:
        config = node.config()
        if config is not None:
            self.commands.add_updater_item(config, item_type, category)
            key = "objective_functions" if category == "objectives" else "constraints"
            self._select(UpdaterItemTreeNode(node.updater_parent, node.group, node.config_index, config[key][-1]))
            self.changed.emit(node)

    def add_symmetry_constraint(self, node: UpdaterTreeNode, item_type: str) -> None:
        config = node.config()
        if self._problem is not None and config is not None and self.commands.add_symmetry_constraint(
            config,
            item_type,
        ):
            self._select(UpdaterItemTreeNode(
                node.updater_parent, node.group, node.config_index, config["symmetry_constraints"][-1]
            ))
            self.changed.emit(node)

    def remove_updater_item(self, node: UpdaterItemTreeNode) -> None:
        config = node.config()
        if self._problem is None or config is None:
            return
        UpdaterItems(config, node.section_group, node.category, self._problem).remove(node.item)
        self._select(UpdaterTreeNode(node.updater_parent, node.group, node.config_index))
        self.changed.emit(node)

    def move_updater_item(self, node: UpdaterItemTreeNode, offset: int) -> None:
        config = node.config()
        if self._problem is None or config is None:
            return
        if UpdaterItems(config, node.section_group, node.category, self._problem).move(node.item, offset):
            self._select(node)
            self.changed.emit(node)

    def custom_add_menu(self, menu, candidates, add):
        sub = menu.addMenu(tr('ui.widgets.model_tree.custom_class'))
        options = custom_options(self._problem, candidates)
        shown = set()
        for kind, custom in options:
            if custom.name in shown:
                continue
            shown.add(custom.name)
            action = sub.addAction(typed_title(custom.name, candidates[kind].rsplit(".", 1)[-1]))
            action.triggered.connect(lambda _=False, kind=kind, name=custom.name: add(kind, name))
        if not options:
            action = sub.addAction(tr('ui.widgets.model_tree.create_a_compatible_custom_class_first'))
            action.setEnabled(False)

    def set_objective_class(self, custom_class):
        if self._problem is None or self._problem.objective is None:
            return
        self._problem.objective.custom_class = custom_class
        self._problem.class_bindings.pop("ThisController.ObjectiveFunction", None)
        self._select(select=self._problem.objective)
        self.changed.emit(self._problem.objective)

    def add_part_interface(self, itype: str, custom_class: str = "") -> None:
        if self._problem is None:
            return
        if PART_INTERFACE_TYPES[itype].get("custom_only") and not custom_class:
            return
        node = self.commands.add_part_interface(itype, custom_class)
        self._select(node)
        self.changed.emit(node)

    def copy_part_interface(self, interface: Node) -> None:
        if self._problem is None or not isinstance(interface, PartNode):
            return
        copy = self._problem.clone_part_interface(interface)
        self._select(select=copy)
        self.changed.emit(copy)

    def remove_part_interface(self, interface: Node) -> None:
        if self._problem is None or not isinstance(interface, PartNode):
            return
        try:
            self._problem.remove_part_interface(interface)
        except ValueError:
            return  # keep at least one geometry interface
        self._select(select=self._problem.geometry)
        self.changed.emit(interface)

    def move_part_interface(self, interface: Node, delta: int) -> None:
        if self._problem is None or not isinstance(interface, PartNode):
            return
        if not self._problem.move_part_interface(interface, delta):
            return
        self._select(select=interface)
        self.changed.emit(interface)

    def move_cad_operation(self, operation: Node, delta: int) -> None:
        if self._problem is None or not isinstance(operation, CADOperationNode):
            return
        if not self._problem.move_cad_operation(operation, delta):
            return
        self._select(select=operation)
        self.changed.emit(operation)

    def add_instance(self, interface: Node) -> None:
        if self._problem is None or not isinstance(interface, PartNode):
            return
        name = self._problem.suggest_instance_name(interface)
        instance = InstanceNode(name=name)
        self._problem.add_instance(interface, instance)
        self._select(select=instance)
        self.changed.emit(instance)

    def remove_instance(self, instance: Node) -> None:
        if self._problem is None or not isinstance(instance, InstanceNode):
            return
        owner = self._problem.owner_of_instance(instance)
        try:
            self._problem.remove_instance(instance)
        except ValueError:
            return
        self._select(select=owner)
        self.changed.emit(instance)

    def move_instance(self, instance: Node, delta: int) -> None:
        if self._problem is None or not isinstance(instance, InstanceNode):
            return
        if not self._problem.move_instance(instance, delta):
            return
        self._select(select=instance)
        self.changed.emit(instance)

    def add_cad_operation_group(
        self, group: str, owner: PartNode
    ) -> None:
        """Choose an operation type from a CAD feature group."""
        if group == "import":
            self.add_cad_operation("StepImport", owner)
            return
        choices = [
            (operation_type, spec)
            for operation_type, spec in CAD_OPERATION_TYPES.items()
            if spec["group"] == group
        ]
        if not choices:
            raise ValueError(localized_message("ui.errors.definition_actions.unknown_cad_operation_group_value", value_0=group))
        labels = [schema_label(spec, operation_type) for operation_type, spec in choices]
        title = {
            "primitive": tr('ui.widgets.model_tree.add_primitive'),
            "boolean": tr('ui.widgets.model_tree.add_boolean_operation'),
            "transform": tr('ui.widgets.model_tree.add_transform'),
        }[group]
        label, accepted = QInputDialog.getItem(
            self.parent(), title, tr('ui.widgets.model_tree.type'), labels, 0, False
        )
        if not accepted:
            return
        operation_type = choices[labels.index(label)][0]
        self.add_cad_operation(operation_type, owner)

    def add_cad_operation(
        self, operation_type: str, owner: Node
    ) -> None:
        if self._problem is None or not isinstance(owner, PartNode):
            return
        spec = CAD_OPERATION_TYPES[operation_type]
        operation_id = self.commands.next_operation_id(owner, operation_type)

        overrides: dict[str, object] = {}
        if spec["group"] == "boolean":
            live_operations = owner.live_cad_operations()
            live_ids = [operation.operation_id for operation in live_operations]
            if len(live_ids) < 2:
                QMessageBox.information(
                    self.parent(),
                    tr('ui.widgets.model_tree.cad_operation'),
                    tr('ui.widgets.model_tree.boolean_operations_need_two_unconsumed_features'),
                )
                return
            object_id, accepted = QInputDialog.getItem(
                self.parent(),
                tr('ui.widgets.model_tree.boolean_operation'),
                tr('ui.widgets.model_tree.object_feature'),
                live_ids,
                0,
                False,
            )
            if not accepted:
                return
            tool_id, accepted = QInputDialog.getItem(
                self.parent(),
                tr('ui.widgets.model_tree.boolean_operation'),
                tr('ui.widgets.model_tree.tool_feature'),
                [item for item in live_ids if item != object_id],
                0,
                False,
            )
            if not accepted:
                return
            overrides = {"object_id": object_id, "tool_id": tool_id}
        elif spec["group"] == "transform":
            live_ids = [
                operation.operation_id
                for operation in owner.live_cad_operations()
            ]
            if not live_ids:
                QMessageBox.information(
                    self.parent(),
                    tr('ui.widgets.model_tree.cad_operation'),
                    tr('ui.widgets.model_tree.add_an_unconsumed_feature_first'),
                )
                return
            input_id, accepted = QInputDialog.getItem(
                self.parent(),
                tr('ui.widgets.model_tree.transform'),
                tr('ui.widgets.model_tree.input_feature'),
                live_ids,
                0,
                False,
            )
            if not accepted:
                return
            overrides = {"input_id": input_id}
        elif operation_type == "StepImport":
            path, _ = QFileDialog.getOpenFileName(
                self.parent(),
                tr('ui.widgets.model_tree.select_step_file'),
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
                    tr('ui.widgets.model_tree.step_import_failed'),
                    str(exc),
                )
                return
            overrides = {
                "filename": imported.filename,
                "data": imported.data,
            }

        operation = self.commands.add_cad_operation(owner, operation_type, operation_id, **overrides)
        self._select(select=operation)
        self.changed.emit(operation)

    def remove_cad_operation(self, operation: Node) -> None:
        if self._problem is None or not isinstance(operation, CADOperationNode):
            return
        owner = self._problem.owner_of_cad_operation(operation)
        if owner is None:
            return
        try:
            self._problem.remove_cad_operation(operation)
        except ValueError as exc:
            QMessageBox.information(
                self.parent(),
                tr('ui.widgets.model_tree.cad_operation'),
                tr('ui.widgets.model_tree.cannot_delete_value', value_0=exc),
            )
            return
        self._select(select=owner)
        self.changed.emit(operation)

    def add_surface(
        self,
        stype: str,
        owner: PartNode | None = None,
        custom_class: str = "",
    ) -> None:
        if self._problem is None:
            return
        owner = owner if owner is not None else self._problem.default_surface_part_node()
        if owner is None:
            return
        node = self.commands.add_surface(stype, owner, custom_class)
        self._select(node)
        self.changed.emit(node)

    def copy_surface(self, srf: Node) -> None:
        if self._problem is None or not isinstance(srf, SurfaceNode):
            return
        copy = self._problem.clone_surface(srf)
        self._select(select=copy)
        self.changed.emit(copy)

    def remove_surface(self, srf: Node) -> None:
        if self._problem is None or not isinstance(srf, SurfaceNode):
            return
        owner = self._problem.owner_of_surface(srf)
        try:
            self._problem.remove_surface(srf)
        except ValueError:
            return  # keep at least one surface
        self._select(select=owner)
        self.changed.emit(srf)

    def move_surface(self, srf: Node, delta: int) -> None:
        if self._problem is None or not isinstance(srf, SurfaceNode):
            return
        if not self._problem.move_surface(srf, delta):
            return
        self._select(select=srf)
        self.changed.emit(srf)

    def add_interface(self, itype: str, custom_class: str = "") -> None:
        if self._problem is None:
            return
        node = self.commands.add_interface(itype, custom_class)
        self._select(node)
        self.changed.emit(node)

    def add_material(self, material_type: str, custom_class: str = "") -> None:
        if self._problem is None:
            return
        node = self.commands.add_material(material_type, custom_class)
        self._select(node)
        self.changed.emit(node)

    def copy_material(self, material: Node) -> None:
        if self._problem is None or not isinstance(material, MaterialNode):
            return
        copy = self._problem.clone_material(material)
        self._select(select=copy)
        self.changed.emit(copy)

    def move_material(self, material: Node, delta: int) -> None:
        if self._problem is None or not isinstance(material, MaterialNode):
            return
        if not self._problem.move_material(material, delta):
            return
        self._select(select=material)
        self.changed.emit(material)

    def remove_material(self, material: Node) -> None:
        if self._problem is None or not isinstance(material, MaterialNode):
            return
        try:
            self._problem.remove_material(material)
        except ValueError:
            return
        self._select(select=self._problem.materials)
        self.changed.emit(material)

    def copy_interface(self, iface: Node) -> None:
        if self._problem is None or not isinstance(iface, FEAComponentNode):
            return
        # a copied load is a new load: give it a fresh unique name so it does
        # not collide with the original (it starts unset / zero in the steps)
        itype = iface.interface_type
        hint = INTERFACE_TYPES.get(itype, {}).get("name_hint", "load_")
        copy = self._problem.clone_interface(iface, hint)
        self._select(select=copy)
        self.changed.emit(copy)

    def move_interface(self, iface: Node, delta: int) -> None:
        if self._problem is None or not isinstance(iface, FEAComponentNode):
            return
        if not self._problem.move_interface(iface, delta):
            return
        self._select(select=iface)
        self.changed.emit(iface)

    def remove_interface(self, iface: Node) -> None:
        if self._problem is None or not isinstance(iface, FEAComponentNode):
            return
        self._problem.remove_interface(iface)
        self._select(select=self._problem.loads)
        self.changed.emit(iface)
