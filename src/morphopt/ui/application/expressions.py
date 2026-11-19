"""Evaluate definition helper values at the preview boundary."""

from __future__ import annotations

import linecache
import sys
from textwrap import indent
from types import ModuleType
from uuid import uuid4

from ..model.problem import ProblemDefinition


class DefinitionValues:
    """Evaluate parameter expressions against the auxiliary definitions without creating UI
    widgets.
    """
    def __init__(self, problem: ProblemDefinition | None):
        """Initialize DefinitionValues and its configuration state.

        Args:
            problem (ProblemDefinition | None): Editable problem definition shared by the UI
                application services.
        """
        self.problem = problem
        self._namespace: dict[str, object] | None = None

    @property
    def namespace(self) -> dict[str, object]:
        """Evaluate the model's helper definitions once for this preview.

        Returns:
            dict[str, object]: Shared globals for helper functions and parameter expressions.
        """
        if self._namespace is None:
            import numpy as np
            import torch
            import torchfea

            import morphopt

            namespace = {
                "morphopt": morphopt,
                "torchfea": torchfea,
                "np": np,
                "torch": torch,
            }
            blocks = []
            if self.problem is not None:
                blocks.append(self.problem.helper_code)
                blocks.extend(
                    f"{v.name} = {v.value}" for v in self.problem.helper_variables
                )
                blocks.extend(
                    f"def {f.name}({f.parameters}):\n{indent(f.body or 'pass', '    ')}"
                    for f in self.problem.helper_functions
                )
            source = "\n\n".join(block for block in blocks if block.strip())
            if source:
                name = f"_morphopt_preview_{uuid4().hex}"
                module = ModuleType(name)
                filename = f"<{name}>"
                module.__file__ = filename
                module.__dict__.update(namespace)
                code = compile(source, filename, "exec")
                # TorchFEA reads the source of Serializable subclasses as they are defined.
                linecache.cache[filename] = (
                    len(source), None, source.splitlines(keepends=True), filename
                )
                sys.modules[name] = module
                try:
                    exec(code, module.__dict__)
                finally:
                    sys.modules.pop(name, None)
                    linecache.cache.pop(filename, None)
                namespace = module.__dict__
            self._namespace = namespace
        return self._namespace

    def resolve(self, value):
        """Resolve the DefinitionValues state.

        Args:
            value: Value assigned to or evaluated for the selected field.
        """
        if isinstance(value, str):
            return eval(compile(value, "<definition value>", "eval"), self.namespace)
        if isinstance(value, (list, tuple)):
            return [self.resolve(item) for item in value]
        return value
