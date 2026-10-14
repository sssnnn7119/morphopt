"""Shared Qt actions for tree menus and editor buttons.

Dialog/selection policy belongs here. Model operations remain on the definition
and construction defaults are supplied by the application editing service.
"""
from __future__ import annotations
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox
from ..i18n import tr
from ..codegen.custom_classes import custom_options
from ..application.editing import DefinitionCommands
from ..model.problem import (
    Node,
    ProblemDefinition,
    CADOperationNode,
    InstanceNode,
    InterfaceNode,
    MaterialNode,
    PartInterfaceNode,
    SurfaceNode,
)
from ..model.schemas import CAD_OPERATION_TYPES, INTERFACE_TYPES, PART_INTERFACE_TYPES
from ..presentation.navigation import HelperGroupTreeNode, UpdaterTreeNode


class DefinitionActions(QObject):
    changed = Signal()
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

    def add_helper(self, kind: str) -> Node | None:
        if self._problem is None:
            return None
        node = self.commands.add_helper(kind)
        self._select(node)
        self.changed.emit()
        return node

    def remove_helper(self, node: Node) -> None:
        if self._problem is None or node.kind not in {"helper_variable", "helper_function"}:
            return
        group = self.commands.remove_helper(node)
        self._select(HelperGroupTreeNode(group))
        self.changed.emit()

    def add_geometry_updater(self) -> None:
        if self._problem is None or self._problem.updater is None:
            return
        boundary = self._problem.boundary_part_nodes()
        if not boundary:
            QMessageBox.information(
                self.parent(),
                "Geometry optimizer",
                "This model has no boundary part interface (INP / TorchFEA parts "
                "have no design surfaces), so there is nothing to shape-optimize.",
            )
            return
        free = next(iter(self.commands.available_optimizer_targets("geometry")), None)
        if free is None:
            QMessageBox.information(
                self.parent(),
                "Geometry optimizer",
                "Every boundary part already has its own geometry optimizer.",
            )
            return
        self._problem.add_geometry_updater(free)
        index = len(self._problem.updater.geometry) - 1
        self._select(
            select=UpdaterTreeNode(self._problem.updater, "geometry", index)
        )
        self.changed.emit()

    def remove_geometry_updater(self, node: Node) -> None:
        if self._problem is None or self._problem.updater is None:
            return
        index = node.config_index if isinstance(node, UpdaterTreeNode) else 0
        if 0 <= index < len(self._problem.updater.geometry):
            del self._problem.updater.geometry[index]
        self._select(select=self._problem.updater)
        self.changed.emit()

    def add_materials_updater(self) -> None:
        """Add one material optimizer, bound to a free design material interface."""
        if self._problem is None or self._problem.updater is None:
            return
        design = [
            material
            for material in self._problem.material_nodes()
            if material.name in self._problem.design_material_names()
        ]
        if not design:
            QMessageBox.information(
                self.parent(),
                "Material optimizer",
                "This model has no design-carrying material interface (SIMP "
                "density field), so there is nothing to update.",
            )
            return
        free = next(iter(self.commands.available_optimizer_targets("materials")), None)
        if free is None:
            QMessageBox.information(
                self.parent(),
                "Material optimizer",
                "Every design material already has its own material optimizer.",
            )
            return
        self._problem.add_material_updater(free)
        index = len(self._problem.updater.materials) - 1
        self._select(
            select=UpdaterTreeNode(self._problem.updater, "materials", index)
        )
        self.changed.emit()

    def remove_materials_updater(self, node: Node) -> None:
        if self._problem is None or self._problem.updater is None:
            return
        index = node.config_index if isinstance(node, UpdaterTreeNode) else 0
        if 0 <= index < len(self._problem.updater.materials):
            del self._problem.updater.materials[index]
        self._select(select=self._problem.updater)
        self.changed.emit()

    def add_updater_item(self, node: UpdaterTreeNode, item_type: str, category: str) -> None:
        config = node.config()
        if config is not None:
            self.commands.add_updater_item(config, item_type, category)
            self._select(node)
            self.changed.emit()

    def add_symmetry_constraint(self, node: UpdaterTreeNode, item_type: str) -> None:
        config = node.config()
        if self._problem is not None and config is not None and self.commands.add_symmetry_constraint(
            config,
            item_type,
        ):
            self._select(node)
            self.changed.emit()

    def custom_add_menu(self, menu, candidates, add):
        sub = menu.addMenu(tr('ui.widgets.model_tree.custom_class'))
        options = custom_options(self._problem, candidates)
        shown = set()
        for kind, custom in options:
            if custom.name in shown:
                continue
            shown.add(custom.name)
            action = sub.addAction(f"{custom.name} [{kind}]")
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
        self.changed.emit()

    def add_part_interface(self, itype: str, custom_class: str = "") -> None:
        if self._problem is None:
            return
        if PART_INTERFACE_TYPES[itype].get("custom_only") and not custom_class:
            return
        node = self.commands.add_part_interface(itype, custom_class)
        self._select(node)
        self.changed.emit()

    def copy_part_interface(self, interface: Node) -> None:
        if self._problem is None or not isinstance(interface, PartInterfaceNode):
            return
        copy = self._problem.clone_part_interface(interface)
        self._select(select=copy)
        self.changed.emit()

    def remove_part_interface(self, interface: Node) -> None:
        if self._problem is None or not isinstance(interface, PartInterfaceNode):
            return
        try:
            self._problem.remove_part_interface(interface)
        except ValueError:
            return  # keep at least one geometry interface
        self._select(select=self._problem.geometry)
        self.changed.emit()

    def move_part_interface(self, interface: Node, delta: int) -> None:
        if self._problem is None or not isinstance(interface, PartInterfaceNode):
            return
        if not self._problem.move_part_interface(interface, delta):
            return
        self._select(select=interface)
        self.changed.emit()

    def move_cad_operation(self, operation: Node, delta: int) -> None:
        if self._problem is None or not isinstance(operation, CADOperationNode):
            return
        if not self._problem.move_cad_operation(operation, delta):
            return
        self._select(select=operation)
        self.changed.emit()

    def add_instance(self, interface: Node) -> None:
        if self._problem is None or not isinstance(interface, PartInterfaceNode):
            return
        name = self._problem.suggest_instance_name(interface)
        instance = InstanceNode(name=name)
        self._problem.add_instance(interface, instance)
        self._select(select=instance)
        self.changed.emit()

    def remove_instance(self, instance: Node) -> None:
        if self._problem is None or not isinstance(instance, InstanceNode):
            return
        owner = self._problem.owner_of_instance(instance)
        try:
            self._problem.remove_instance(instance)
        except ValueError:
            return
        self._select(select=owner)
        self.changed.emit()

    def move_instance(self, instance: Node, delta: int) -> None:
        if self._problem is None or not isinstance(instance, InstanceNode):
            return
        if not self._problem.move_instance(instance, delta):
            return
        self._select(select=instance)
        self.changed.emit()

    def add_cad_operation_group(
        self, group: str, owner: PartInterfaceNode
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
            raise ValueError(f"Unknown CAD operation group {group!r}.")
        labels = [tr(spec["label_key"]) for _, spec in choices]
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
        if self._problem is None or not isinstance(owner, PartInterfaceNode):
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
                "STEP (*.step *.stp)",
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
        self.changed.emit()

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
        self.changed.emit()

    def add_surface(
        self,
        stype: str,
        owner: PartInterfaceNode | None = None,
        custom_class: str = "",
    ) -> None:
        if self._problem is None:
            return
        owner = owner if owner is not None else self._problem.default_surface_part_node()
        if owner is None:
            return
        node = self.commands.add_surface(stype, owner, custom_class)
        self._select(node)
        self.changed.emit()

    def copy_surface(self, srf: Node) -> None:
        if self._problem is None or not isinstance(srf, SurfaceNode):
            return
        copy = self._problem.clone_surface(srf)
        self._select(select=copy)
        self.changed.emit()

    def remove_surface(self, srf: Node) -> None:
        if self._problem is None or not isinstance(srf, SurfaceNode):
            return
        owner = self._problem.owner_of_surface(srf)
        try:
            self._problem.remove_surface(srf)
        except ValueError:
            return  # keep at least one surface
        self._select(select=owner)
        self.changed.emit()

    def move_surface(self, srf: Node, delta: int) -> None:
        if self._problem is None or not isinstance(srf, SurfaceNode):
            return
        if not self._problem.move_surface(srf, delta):
            return
        self._select(select=srf)
        self.changed.emit()

    def add_interface(self, itype: str, custom_class: str = "") -> None:
        if self._problem is None:
            return
        node = self.commands.add_interface(itype, custom_class)
        self._select(node)
        self.changed.emit()

    def add_material(self, material_type: str, custom_class: str = "") -> None:
        if self._problem is None:
            return
        node = self.commands.add_material(material_type, custom_class)
        self._select(node)
        self.changed.emit()

    def copy_material(self, material: Node) -> None:
        if self._problem is None or not isinstance(material, MaterialNode):
            return
        copy = self._problem.clone_material(material)
        self._select(select=copy)
        self.changed.emit()

    def move_material(self, material: Node, delta: int) -> None:
        if self._problem is None or not isinstance(material, MaterialNode):
            return
        if not self._problem.move_material(material, delta):
            return
        self._select(select=material)
        self.changed.emit()

    def remove_material(self, material: Node) -> None:
        if self._problem is None or not isinstance(material, MaterialNode):
            return
        try:
            self._problem.remove_material(material)
        except ValueError:
            return
        self._select(select=self._problem.materials)
        self.changed.emit()

    def copy_interface(self, iface: Node) -> None:
        if self._problem is None or not isinstance(iface, InterfaceNode):
            return
        # a copied load is a new load: give it a fresh unique name so it does
        # not collide with the original (it starts unset / zero in the steps)
        itype = iface.interface_type
        hint = INTERFACE_TYPES.get(itype, {}).get("name_hint", "load_")
        copy = self._problem.clone_interface(iface, hint)
        self._select(select=copy)
        self.changed.emit()

    def move_interface(self, iface: Node, delta: int) -> None:
        if self._problem is None or not isinstance(iface, InterfaceNode):
            return
        if not self._problem.move_interface(iface, delta):
            return
        self._select(select=iface)
        self.changed.emit()

    def remove_interface(self, iface: Node) -> None:
        if self._problem is None or not isinstance(iface, InterfaceNode):
            return
        self._problem.remove_interface(iface)
        self._select(select=self._problem.loads)
        self.changed.emit()
