"""UI session for selecting and displaying archived optimization results."""

from __future__ import annotations

import codecs
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...constants import CONSTANT
from ...postprocess import OptimizationArchive
from ..i18n import localized_message


@dataclass(frozen=True)
class ResultSelection:
    """The saved iteration shared by the observer and finite-element views."""

    folder: str
    iteration: int


class ResultSession:
    """Stateful UI reader for one result directory.

    Archive layout and data restoration live in :mod:`morphopt.postprocess`;
    this session keeps the selected folder, iteration, and loaded history while
    the composed archive service owns initialized model objects.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.folder: str | None = None
        self._archive: OptimizationArchive | None = None
        self.history: Any | None = None
        self.iteration = 0

    @property
    def controller(self) -> type[Any] | None:
        return self._archive.controller_class if self._archive is not None else None

    @property
    def params(self) -> Any | None:
        return self._archive.params if self._archive is not None else None

    def bind(self, folder: str) -> bool:
        normalized = str(Path(folder).resolve())
        if self.folder == normalized and self.controller is not None:
            return True
        self.reset()
        self.folder = normalized
        archive = OptimizationArchive(normalized)
        self._archive = archive
        if archive.controller_class is None:
            return False
        try:
            archive.initialize_params()
        except Exception as exc:
            print(localized_message("ui.messages.parameters_init_failed", error=exc))
        return True

    def load_iteration(self, folder: str, iteration: int) -> Any:
        normalized = str(Path(folder).resolve())
        if normalized != self.folder:
            self.bind(normalized)
        if self._archive is None:
            self._archive = OptimizationArchive(normalized)
        history = self._archive.load_history(int(iteration))
        self.folder = normalized
        self.iteration = int(iteration)
        self.history = history
        return history

    def load_parameters(self, iteration: int) -> Any | None:
        return self._archive.load_parameters(iteration) if self._archive else None

    def fea_components(self) -> tuple[tuple[str, Any], ...]:
        return self._archive.visualizable_components() if self._archive else ()

    def deformation_mesh(self, case: str, iteration: int) -> Any | None:
        return (
            self._archive.deformation_mesh(case, iteration) if self._archive else None
        )

    def deformation_cases(self) -> tuple[str, ...]:
        return self._archive.deformation_cases() if self._archive else ()

    @property
    def log_files(self) -> tuple[Path, ...]:
        return self._archive.log_files if self._archive else ()


class ResultLogReader:
    """Read appended UTF-8 log text without retaining open file handles."""

    def __init__(self) -> None:
        self.clear()

    def clear(self) -> None:
        self.path: Path | None = None
        self._offset = 0
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def read(self, path: Path) -> tuple[bool, str]:
        """Return whether to replace the view and the newly available text.

        A new or truncated file replaces the view. Large files start at their
        last complete lines; each poll reads a bounded amount of recent text.
        The decoder retains UTF-8 characters split across writes.
        """
        with path.open("rb") as stream:
            size = stream.seek(0, 2)
            replace = path != self.path or size < self._offset
            offset = 0 if replace else self._offset
            clipped = size - offset > CONSTANT.UI.OBSERVER.LOG_READ_MAXIMUM_BYTES
            if clipped:
                offset = size - CONSTANT.UI.OBSERVER.LOG_READ_MAXIMUM_BYTES
                replace = True
            stream.seek(offset)
            data = stream.read(CONSTANT.UI.OBSERVER.LOG_READ_MAXIMUM_BYTES)
            self._offset = stream.tell()
        self.path = path
        if replace:
            self._decoder.reset()
        if clipped:
            data = data.split(b"\n", 1)[-1]
        return replace, self._decoder.decode(data)
