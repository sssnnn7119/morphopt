"""Use cases for creating, editing and serializing problem definitions."""

from __future__ import annotations
from ..i18n import localized_message

from pathlib import Path
import json

from .edit_history import EditHistory, EditSnapshot

from ..codegen.generator import generate_source
from ..model.loaders import load_morph, save_morph
from ..model.problem import (
    GeometryNode,
    LoadsNode,
    MaterialsNode,
    ObjectiveNode,
    ProblemDefinition,
    ProblemNode,
    SolverNode,
    StepsNode,
    UpdaterNode,
)
from ..schemes.base import SchemeTemplate, available_templates, get_template


class MissingImportedModelError(ValueError):
    """The definition references an imported Part without a readable archive."""


class ProblemSession:
    """Single application-level owner of the definition being edited.

    The domain objects stay plain Python objects.  This session gathers the
    cross-object operations which previously lived in individual widgets, so
    every view follows the same synchronization and validation rules.
    """

    def __init__(self, problem: ProblemDefinition):
        self._problem = problem
        self.history = EditHistory()
        self.reset_history()

    @property
    def problem(self) -> ProblemDefinition:
        return self._problem

    def replace(self, problem: ProblemDefinition) -> None:
        self._problem = problem
        self.reset_history()

    def snapshot(
        self, description: str = "", selection: tuple[int, ...] | None = None,
    ) -> EditSnapshot:
        state = json.dumps(
            self._problem.to_dict(), ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        return EditSnapshot(state, description, selection)

    def reset_history(self) -> None:
        self.history.reset(self.snapshot())

    def record_edit(
        self, description: str, *, selection: tuple[int, ...] | None = None,
        merge_key: object | None = None,
    ) -> bool:
        return self.history.commit(self.snapshot(description, selection), merge_key=merge_key)

    def restore_edit(self, offset: int) -> EditSnapshot:
        return self.restore_edit_step(self.history.target(offset).step_id)

    def restore_edit_step(self, step_id: int) -> EditSnapshot:
        """Decode before moving the cursor, so invalid snapshots cannot lose history."""
        snapshot = self.history.node(step_id).snapshot
        problem = ProblemDefinition.from_dict(json.loads(snapshot.state))
        self._problem = problem
        self.history.select(step_id)
        return snapshot

    def synchronize(self) -> bool:
        """Normalize derived links after loading or editing the model."""
        self._problem.resolve_references()
        changed = self._problem.sync_imported_part_interfaces()
        self._problem.resolve_references()
        self._problem.align_surface_dependent_state()
        return changed

    def source(self, *, synchronize: bool = True) -> str:
        """Return runnable source for the current, synchronized definition."""
        if synchronize:
            self.synchronize()
        return generate_source(self._problem)

    def validate_for_run(self) -> None:
        """Raise a user-facing error when the definition cannot be executed."""
        imported = self._problem.imported_model_part_node()
        if imported is not None and self._problem.imported_model_summary() is None:
            raise MissingImportedModelError(
                localized_message("ui.errors.definitions.select_a_valid_torchfea_npz_model_for_the_imported_part")
            )
        self.source()
        reference_fields = {
            "instance_name", "instance_name1", "instance_name2", "rp_name",
            "rp_name1", "rp_name2", "surface_name", "surface_name1",
            "surface_name2", "set_nodes_name", "element_name", "obj_name",
        }
        from ..model.schemas import INTERFACE_TYPES

        for interface in self._problem.interfaces():
            for field in INTERFACE_TYPES[interface.interface_type]["params"]:
                key = field["key"]
                if key in reference_fields and not interface.get_field(key):
                    raise ValueError(localized_message(
                        "ui.errors.generator.interface_value_must_select_value",
                        value_0=interface.name, value_1=key,
                    ))
        for material in self._problem.material_nodes():
            if material.part is None:
                raise ValueError(localized_message(
                    "ui.errors.generator.interface_value_must_select_value",
                    value_0=material.name, value_1="part_name",
                ))

    def set_label(self, value: str) -> bool:
        value = value.strip()
        if not value or value == self._problem.label:
            return False
        self._problem.label = value
        self._problem.root.name = value
        return True

    def set_result_folder(self, value: str) -> bool:
        value = value.strip()
        if value == self._problem.result_folder:
            return False
        self._problem.result_folder = value
        return True

    def set_device(self, value: str) -> bool:
        value = value.strip()
        if not value or value == self._problem.device:
            return False
        self._problem.device = value
        return True



class ProblemLibrary:
    """File/template gateway used by the top-level window.

    Dialog ownership remains in the Qt window; all actual definition IO goes
    through this class, which keeps the serialization policy in one place.
    """

    @staticmethod
    def templates() -> tuple[SchemeTemplate, ...]:
        return tuple(available_templates())

    @staticmethod
    def create(template_id: str, label: str | None = None) -> ProblemDefinition:
        template = get_template(template_id)
        problem = template.create_problem(label or f"{template_id}_untitled")
        ProblemSession(problem).synchronize()
        return problem

    @staticmethod
    def create_blank(label: str = "Untitled") -> ProblemDefinition:
        """Create an empty editable definition with the standard tree sections."""
        problem = ProblemDefinition(scheme="shapeopt", label=label)
        problem.root = ProblemNode(
            name=label,
            children=[
                GeometryNode(),
                LoadsNode(),
                StepsNode(params={"num_steps": 1, "step_values": [{}]}),
                MaterialsNode(), ObjectiveNode(), SolverNode(), UpdaterNode(),
            ],
        )
        return problem

    @staticmethod
    def load(path: str | Path) -> ProblemDefinition:
        problem = load_morph(str(path))
        ProblemSession(problem).synchronize()
        return problem

    @staticmethod
    def save(problem: ProblemDefinition, path: str | Path) -> str:
        ProblemSession(problem).synchronize()
        return save_morph(problem, str(path))

    @staticmethod
    def export_python(problem: ProblemDefinition, path: str | Path) -> str:
        source = ProblemSession(problem).source()
        output = Path(path)
        output.write_text(source, encoding="utf-8")
        return str(output)

    @staticmethod
    def save_result_copy(problem: ProblemDefinition, folder: str | Path) -> str:
        """Save the editable definition beside a run's frozen Python script."""
        result = Path(folder)
        scripts = result / "scripts"
        destination = scripts if scripts.is_dir() else result
        return ProblemLibrary.save(
            problem, destination / "MAIN_SCRIPT_FOR_RESTART.morph"
        )
