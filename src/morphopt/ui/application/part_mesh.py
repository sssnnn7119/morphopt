"""Build the selected kernel Part with the same definitions as script export."""

import runpy
from pathlib import Path
from tempfile import TemporaryDirectory

import torchfea

from ..model.problem import PartNode, ProblemDefinition
from .definitions import ProblemLibrary


def build_part_mesh(node: PartNode, problem: ProblemDefinition) -> torchfea.Part:
    """Mesh one Part on demand, including its custom classes and embedded assets.

    Other incomplete Parts, loads and material assignments do not participate in
    a geometry selection. Temporary assets live until meshing has completed.
    """
    definition = ProblemLibrary.create_blank()
    definition.helper_code = problem.helper_code
    definition.helper_variables = problem.helper_variables
    definition.helper_functions = problem.helper_functions
    definition.custom_classes = problem.custom_classes
    definition.class_bindings = dict(problem.class_bindings)
    definition.add_part(node.clone())
    with TemporaryDirectory(prefix="morphopt-part-sets-") as directory:
        path = Path(
            ProblemLibrary.export_python(definition, Path(directory) / "part.py")
        )
        namespace = runpy.run_path(str(path), run_name="morphopt_part_sets")
        geometry = namespace["ThisController"].Params.GeometryParams()
        geometry.initialize()
        return geometry.interface(node.name).get_part(
            path_result=str(Path(directory) / "mesh")
        )
