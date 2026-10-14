"""Data model for the MorphOpt UI.

The problem is held as a generic, schema-tagged node tree (``Node``) that
mirrors the Params / Geometry / Loads / Steps / Materials / Objective /
 Solver / Updater hierarchy of a morphopt ``ThisController``.  The model is
deliberately generic: every node carries a ``kind`` that resolves to a field
schema (see :mod:`morphopt.ui.model.schemas`) and typed attributes that match
the backend constructor arguments. File-backed templates provide the starter
tree and backend metadata used to emit valid morphopt code.
"""

from .problem import (
    Node, ProblemDefinition, MaterialsNode, MaterialNode, InstanceNode,
    CADOperationNode,
    CustomClassNode, MethodOverrideNode, HelperVariableNode, HelperFunctionNode,
    find_node, list_node_paths,
)
from .chamberlayout import ChamberLayer, CavitySpec, LayeredChambers
from . import schemas
from . import loaders

__all__ = ["Node", "ProblemDefinition", "MaterialsNode", "MaterialNode", "InstanceNode",
           "CADOperationNode",
           "CustomClassNode", "MethodOverrideNode", "HelperVariableNode", "HelperFunctionNode",
           "find_node", "list_node_paths", "ChamberLayer", "CavitySpec",
           "LayeredChambers", "schemas", "loaders"]
