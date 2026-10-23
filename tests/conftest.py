"""Small exact CAD assets shared by geometry and persistence regressions."""

from collections.abc import Callable
from pathlib import Path

import gmsh
import pytest
from torchfea import cad


@pytest.fixture
def step_factory(tmp_path: Path) -> Callable[[str], Path]:
    def create(kind: str) -> Path:
        path = tmp_path / f"{kind}.step"
        with cad.occ_session(f"test_{kind}") as context:
            if kind == "box":
                context.occ.addBox(0, 0, 0, 6, 4, 3)
            elif kind == "cylinder":
                context.occ.addCylinder(0, 0, 0, 0, 0, 5, 2)
            elif kind == "hole":
                box = context.occ.addBox(0, 0, 0, 6, 4, 3)
                hole = context.occ.addCylinder(2, 2, -1, 0, 0, 5, 0.6)
                context.occ.cut([(3, box)], [(3, hole)])
            elif kind == "triangle":
                points = [context.occ.addPoint(*xyz) for xyz in
                          ((0, 0, 0), (6, 0, 0), (0, 4, 0))]
                lines = [context.occ.addLine(points[i], points[(i + 1) % 3]) for i in range(3)]
                wire = context.occ.addCurveLoop(lines)
                face = context.occ.addPlaneSurface([wire])
                context.occ.extrude([(2, face)], 0, 0, 3)
            else:
                raise ValueError(kind)
            context.occ.synchronize()
            gmsh.write(str(path))
        return path
    return create

