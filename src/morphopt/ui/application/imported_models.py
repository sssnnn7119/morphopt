"""TorchFEA archive discovery and external modeling-tool launch."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import sys

from ..model.modelinfo import TorchFEAModelSummary, inspect_model
from ..model.problem import PartInterfaceNode, resolve_model_directory


@dataclass(frozen=True)
class ModelScan:
    names: tuple[str, ...]
    changed: tuple[str, ...]
    selected: str
    directory_exists: bool


class ImportedModelLibrary:
    """Track exported archives; Qt only supplies file-change notifications."""

    def __init__(self):
        self._mtimes: dict[str, int] = {}

    @staticmethod
    def mtimes(directory: str) -> dict[str, int]:
        path = Path(resolve_model_directory(directory))
        if not directory or not path.is_dir():
            return {}
        return {item.name: item.stat().st_mtime_ns for item in path.glob("*.npz") if item.is_file()}

    def watch(self, directory: str) -> None:
        self._mtimes = self.mtimes(directory)

    def scan(self, directory: str, current: str, *, auto_import: bool = False) -> ModelScan:
        mtimes = self.mtimes(directory)
        names = tuple(sorted(mtimes, key=mtimes.get, reverse=True))
        changed = tuple(name for name in names if mtimes[name] > self._mtimes.get(name, -1))
        self._mtimes = mtimes
        selected = changed[0] if auto_import and changed else current
        if not selected and names:
            selected = names[0]
        return ModelScan(
            names,
            changed,
            selected,
            bool(directory) and Path(resolve_model_directory(directory)).is_dir(),
        )

    @staticmethod
    def inspect(directory: str, filename: str) -> TorchFEAModelSummary:
        return inspect_model(resolve_model_directory(directory), filename)

    @staticmethod
    def validate_link(node: PartInterfaceNode) -> str | None:
        if not node.model_directory or not node.model_filename:
            return None
        directory = resolve_model_directory(node.model_directory)
        try:
            inspect_model(directory, node.model_filename)
        except Exception as exc:
            node.model_filename = ""
            if not Path(directory).is_dir():
                node.model_directory = ""
            return str(exc)
        return None

    @staticmethod
    def launch(directory: str) -> None:
        """Start the external editor detached, reaping its process off the UI thread."""
        import threading
        executable = shutil.which("torchfea-ui")
        command = [executable] if executable else [sys.executable, "-m", "torchfea.ui"]
        process = subprocess.Popen(command, cwd=resolve_model_directory(directory), start_new_session=True)
        threading.Thread(target=process.wait, daemon=True).start()
