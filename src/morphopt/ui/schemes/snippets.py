"""Composable, scheme-independent FEA code snippets for the objective editor.

This module intentionally knows neither Qt widgets nor a specific optimization
scheme.  It describes source text plus the values a UI must collect before
insertion.  The Objective editor resolves each parameter against the current
``ProblemDefinition`` and inserts the rendered source at the user's caret.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class SnippetParameter:
    """One model-backed selectable value needed to render a code snippet."""

    key: str
    label: str
    label_en: str
    source: str
    default: Any


@dataclass(frozen=True)
class CodeSnippet:
    """A source fragment that can be inserted into either objective code slot."""

    key: str
    name_zh: str
    name_en: str
    parameters: tuple[SnippetParameter, ...]
    source: str

    def render(self, values: Mapping[str, Any] | None = None) -> str:
        """Fill named source placeholders with UI-selected parameter values."""
        defaults = {parameter.key: parameter.default for parameter in self.parameters}
        return self.source.format(**(defaults | dict(values or {})))


_LOAD_STEP = SnippetParameter("step_index", "载荷步", "Load step",
                              "load_steps", 0)
_INSTANCE = SnippetParameter("instance_name", "实体", "Instance",
                             "instances", "final_model")
_REFERENCE_POINT = SnippetParameter("reference_point_name", "参考点",
                                    "Reference point", "reference_points", "RP_head")
_AXIS = SnippetParameter("axis", "方向", "Axis", "axis", 2)
_TRANSLATION_AXIS = SnippetParameter(
    "axis", "平移方向", "Translation axis", "translation_axis", 2)
_ROTATION_AXIS = SnippetParameter(
    "axis", "旋转方向", "Rotation axis", "rotation_axis", 5)
_COMPONENT = SnippetParameter("component", "分量", "Component",
                              "six_component", 2)
_ELEMENT = SnippetParameter("element_name", "单元类型", "Element type",
                            "elements", "C3D4")
_FORCE_LOAD = SnippetParameter(
    "force_load_name", "集中力载荷", "Concentrated-force load",
    "force_loads", "force_RP_head")
_MOMENT_LOAD = SnippetParameter(
    "moment_load_name", "集中力矩载荷", "Concentrated-moment load",
    "moment_loads", "moment_RP_head")


def shared_fea_snippets() -> tuple[CodeSnippet, ...]:
    """Return the standard snippets available for every optimization scheme."""
    instance_state = _instance_state_source()
    reference_point_state = _reference_point_state_source()
    return (
        CodeSnippet(
            "instance_displacement", "实体节点位移（RGC）",
            "Instance nodal displacement (RGC)",
            (_LOAD_STEP, _INSTANCE),
            instance_state + "# node_displacement: [num_nodes, 3].\n",
        ),
        CodeSnippet(
            "reference_point_motion", "参考点位移 / 转角（RGC）",
            "Reference-point displacement / rotation (RGC)",
            (_LOAD_STEP, _REFERENCE_POINT),
            reference_point_state + "# reference_point_motion: [Ux, Uy, Uz, Rx, Ry, Rz].\n",
        ),
        CodeSnippet(
            "end_effector_translation", "末端执行器平移分量",
            "End-effector translation component",
            (_LOAD_STEP, _REFERENCE_POINT, _TRANSLATION_AXIS),
            reference_point_state + (
                "end_effector_translation = reference_point_motion[{axis}]\n"
                "# Translation component: X/Y/Z = 0/1/2.\n"
            ),
        ),
        CodeSnippet(
            "end_effector_rotation", "末端执行器旋转分量",
            "End-effector rotation component",
            (_LOAD_STEP, _REFERENCE_POINT, _ROTATION_AXIS),
            reference_point_state + (
                "end_effector_rotation = reference_point_motion[{axis}]\n"
                "# Rotation component: Rx/Ry/Rz = 3/4/5.\n"
            ),
        ),
        CodeSnippet(
            "instance_force", "实体节点残余力 / 广义残量（R）",
            "Instance nodal residual force / generalized residual (R)",
            (_LOAD_STEP, _INSTANCE, _AXIS),
            instance_state + (
                "R = assembly._assemble_generalized_Matrix(GC=GC)[0]\n"
                "start = assembly._RGC_list_indexStart[instance._RGC_index]\n"
                "end = assembly._RGC_list_indexStart[instance._RGC_index + 1]\n"
                "node_force = R[start:end].reshape(-1, 3)\n"
                "axis = {axis}  # X/Y/Z = 0/1/2\n"
                "# node_force: [num_nodes, 3].\n"
            ),
        ),
        CodeSnippet(
            "reference_point_force", "参考点残余力 / 力矩（R）",
            "Reference-point residual force / moment (R)",
            (_LOAD_STEP, _REFERENCE_POINT, _COMPONENT),
            reference_point_state + (
                "R = assembly._assemble_generalized_Matrix(GC=GC)[0]\n"
                "start = assembly._RGC_list_indexStart[reference_point._RGC_index]\n"
                "end = assembly._RGC_list_indexStart[reference_point._RGC_index + 1]\n"
                "reference_point_force = R[start:end]\n"
                "component = {component}  # Fx/Fy/Fz/Mx/My/Mz = 0..5\n"
                "# reference_point_force: [Fx, Fy, Fz, Mx, My, Mz].\n"
            ),
        ),
        CodeSnippet(
            "gaussian_energy_density", "实体单元高斯点应变能密度",
            "Instance Gaussian-point strain-energy density",
            (_LOAD_STEP, _INSTANCE, _ELEMENT),
            instance_state + (
                "element_name = {element_name!r}\n"
                "element = instance.elems[element_name]\n"
                "energy_density = element.get_potential_energy_density(U=node_displacement)\n"
                "# energy_density: [num_gaussian, num_elements].\n"
            ),
        ),
        CodeSnippet(
            "gaussian_deformation_gradient", "实体单元高斯点变形梯度 F",
            "Instance Gaussian-point deformation gradient F",
            (_LOAD_STEP, _INSTANCE, _ELEMENT),
            instance_state + (
                "element_name = {element_name!r}\n"
                "element = instance.elems[element_name]\n"
                "deformation_gradient = element.get_deformation_gradient(U=node_displacement)\n"
                "# deformation_gradient: [num_gaussian, num_elements, 3, 3].\n"
            ),
        ),
        CodeSnippet(
            "jacobian_6d_matrix", "末端 6×6 雅可比矩阵",
            "End-effector 6x6 Jacobian matrix",
            (_LOAD_STEP, _REFERENCE_POINT, _FORCE_LOAD, _MOMENT_LOAD),
            _jacobian_6d_source() + (
                "# jacobian_6x6 maps force/moment parameters to the six RP DOFs.\n"
            ),
        ),
        CodeSnippet(
            "jacobian_translation_response", "平移方向雅可比响应范数",
            "Translation Jacobian response norm",
            (_LOAD_STEP, _REFERENCE_POINT, _FORCE_LOAD, _MOMENT_LOAD),
            _jacobian_6d_source() + (
                "translation_jacobian_norm = torch.linalg.matrix_norm(\n"
                "    jacobian_6x6[:3, :3], ord='fro')\n"
                "# Use this scalar in objective_function or get_metrics.\n"
            ),
        ),
        CodeSnippet(
            "jacobian_rotation_response", "旋转方向雅可比响应范数",
            "Rotation Jacobian response norm",
            (_LOAD_STEP, _REFERENCE_POINT, _FORCE_LOAD, _MOMENT_LOAD),
            _jacobian_6d_source() + (
                "rotation_jacobian_norm = torch.linalg.matrix_norm(\n"
                "    jacobian_6x6[3:, 3:], ord='fro')\n"
                "# Use this scalar in objective_function or get_metrics.\n"
            ),
        ),
        CodeSnippet(
            "jacobian_6d_response", "6×6 雅可比整体响应范数",
            "Overall 6x6 Jacobian response norm",
            (_LOAD_STEP, _REFERENCE_POINT, _FORCE_LOAD, _MOMENT_LOAD),
            _jacobian_6d_source() + (
                "jacobian_6d_norm = torch.linalg.matrix_norm(\n"
                "    jacobian_6x6, ord='fro')\n"
                "# Use this scalar in objective_function or get_metrics.\n"
            ),
        ),
    )


def _instance_state_source() -> str:
    return (
        "# Change the load step and instance name for this extraction.\n"
        "step_index = {step_index}\n"
        "instance_name = {instance_name!r}\n"
        "morphopt.controller.params.feamodel.process_fea(self.fe, step_index=step_index)\n"
        "assembly = self.fe.assembly\n"
        "GC = self.fe_results[step_index].GC.to(assembly.device)\n"
        "instance = assembly.get_instance(instance_name)\n"
        "RGC = assembly._GC2RGC(GC)\n"
        "node_displacement = RGC[instance._RGC_index]\n"
    )


def _reference_point_state_source() -> str:
    return (
        "# Change the load step and reference-point name for this extraction.\n"
        "step_index = {step_index}\n"
        "reference_point_name = {reference_point_name!r}\n"
        "morphopt.controller.params.feamodel.process_fea(self.fe, step_index=step_index)\n"
        "assembly = self.fe.assembly\n"
        "GC = self.fe_results[step_index].GC.to(assembly.device)\n"
        "reference_point = assembly.get_reference_point(reference_point_name)\n"
        "RGC = assembly._GC2RGC(GC)\n"
        "reference_point_motion = RGC[reference_point._RGC_index]\n"
    )


def _jacobian_6d_source() -> str:
    """Build the shared force/moment Jacobian extraction fragment."""
    return (
        "# Before using this snippet, add a concentrated force and moment at the selected RP.\n"
        "# The selected RP determines the Jacobian output rows in GC space.\n"
        "# Also select both load names manually in Objective > Jacobian needed.\n"
        "import torch\n"
        "step_index = {step_index}\n"
        "reference_point_name = {reference_point_name!r}\n"
        "force_load_name = {force_load_name!r}\n"
        "moment_load_name = {moment_load_name!r}\n"
        "assembly = self.fe.assembly\n"
        "reference_point = assembly.get_reference_point(reference_point_name)\n"
        "gc_index_start = assembly._GC_list_indexStart\n"
        "reference_point_start = gc_index_start[reference_point._RGC_index]\n"
        "reference_point_end = gc_index_start[reference_point._RGC_index + 1]\n"
        "force_jacobian = self.fe_results[step_index].jacobian[force_load_name][reference_point_start:reference_point_end, :]\n"
        "moment_jacobian = self.fe_results[step_index].jacobian[moment_load_name][reference_point_start:reference_point_end, :]\n"
        "jacobian_6x6 = torch.cat((force_jacobian, moment_jacobian), dim=1)\n"
    )
