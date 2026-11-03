"""Evaluate definition helper values at the preview boundary."""

from __future__ import annotations

from textwrap import indent

from ..model.problem import ProblemDefinition


class DefinitionValues:
    def __init__(self, problem: ProblemDefinition | None):
        self.problem = problem
        self._namespace: dict[str, object] | None = None

    @property
    def namespace(self) -> dict[str, object]:
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
                exec(compile(source, "<definition preview helpers>", "exec"), namespace)
            self._namespace = namespace
        return self._namespace

    def resolve(self, value):
        if isinstance(value, str):
            return eval(compile(value, "<definition value>", "eval"), self.namespace)
        if isinstance(value, (list, tuple)):
            return [self.resolve(item) for item in value]
        return value
