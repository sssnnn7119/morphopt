"""Use cases for creating, editing and serializing problem definitions."""

from __future__ import annotations

from pathlib import Path

from ..codegen.generator import generate_source
from ..model.loaders import load_morph, save_morph
from ..model.problem import ProblemDefinition
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

    @property
    def problem(self) -> ProblemDefinition:
        return self._problem

    def replace(self, problem: ProblemDefinition) -> None:
        self._problem = problem

    def synchronize(self) -> bool:
        """Normalize derived links after loading or editing the model."""
        self._problem.resolve_references()
        changed = self._problem.sync_imported_part_interfaces()
        self._problem.resolve_references()
        self._problem.align_surface_dependent_state()
        return changed

    def source(self) -> str:
        """Return runnable source for the current, synchronized definition."""
        self.synchronize()
        return generate_source(self._problem)

    def validate_for_run(self) -> None:
        """Raise a user-facing error when the definition cannot be executed."""
        imported = self._problem.imported_model_part_node()
        if imported is not None and self._problem.imported_model_summary() is None:
            raise MissingImportedModelError(
                "Select a valid TorchFEA .npz model for the imported Part first."
            )
        self.source()

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

    def sync_imported_material_targets(self) -> bool:
        """Fill only unambiguous imported Part and element assignments."""
        summary = self._problem.imported_model_summary()
        materials = self._problem.material_nodes()
        if summary is None or not materials:
            return False

        changed = False
        parts = {part.name: part for part in summary.parts}
        for material in materials:
            if material.part is None and len(summary.parts) == 1:
                target = next(
                    (
                        interface
                        for interface in self._problem.part_interfaces()
                        if interface.resolved_part_name() == summary.parts[0].name
                    ),
                    None,
                )
                if target is not None:
                    material.set_part(target)
                    changed = True
            part_name = material.part.resolved_part_name() if material.part else ""
            if part_name not in parts and len(summary.parts) == 1:
                target = next(
                    (
                        interface
                        for interface in self._problem.part_interfaces()
                        if interface.resolved_part_name() == summary.parts[0].name
                    ),
                    None,
                )
                if target is not None:
                    material.set_part(target)
                    part_name = target.resolved_part_name()
                    changed = True
            part = parts.get(part_name)
            if (
                part is not None
                and len(part.element_types) == 1
                and material.elementname not in part.element_types
                and material.elementname
            ):
                material.elementname = part.element_types[0]
                changed = True
        return changed


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
