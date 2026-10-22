"""Emit explicit Gauss-point displacement/Jacobian sums into task scripts."""
from __future__ import annotations


def workspace_integral_body(
    reference_point_name: str,
    axes: list[int],
    load_groups: list[list[tuple[str, int]]],
    case_names: list[str],
    weights: list[float],
    tangents: list[list[int]],
    orientations: list[float],
) -> str:
    """Render a function body; the emitted script performs the integral itself."""
    planar = len(axes) == 2
    lines = [
        "assembly = self.fe.assembly",
        f"reference_point = assembly.get_reference_point({reference_point_name!r})",
        "start = assembly._GC_list_indexStart[reference_point._RGC_index]",
        f"axes = {axes!r}",
        "# Load case, Gauss weight, orientation, tangent input indices.",
        "samples = [",
    ]
    for name, weight, tangent, orientation in zip(case_names, weights, tangents, orientations, strict=True):
        sample = (name, weight, orientation, tangent[0]) if planar else (name, weight, orientation, *tangent)
        lines.append(f"    {sample!r},")
    columns = "case_name, weight, orientation, tangent_axis" if planar else "case_name, weight, orientation, tangent_a_axis, tangent_b_axis"
    lines.extend([
        "]",
        "integral = 0.0",
        f"for {columns} in samples:",
        "    self.set_step(case_name)",
        "    result = self.fe_results[case_name]",
        "    state = assembly._GC2RGC(result.GC.to(assembly.device))",
        "    motion = state[reference_point._RGC_index].reshape(-1)[axes]",
    ])
    for index, group in enumerate(load_groups):
        lines.append(f"    jacobian_{index} = (")
        for term_index, (load_name, component) in enumerate(group):
            prefix = "" if term_index == 0 else "+ "
            lines.append(f"        {prefix}result.jacobian[{load_name!r}][start:start + 6, {component}].to(motion.device)")
        lines.append("    )[axes]")
    lines.append("    jacobians = [" + ", ".join(f"jacobian_{index}" for index in range(len(load_groups))) + "]")
    if planar:
        lines.extend([
            "    tangent = jacobians[tangent_axis]",
            "    # Counter-clockwise boundary: x dy - y dx.",
            "    integrand = motion[0] * tangent[1] - motion[1] * tangent[0]",
        ])
    else:
        lines.extend([
            "    tangent_a = jacobians[tangent_a_axis]",
            "    tangent_b = jacobians[tangent_b_axis]",
            "    integrand = (",
            "        motion[0] * (tangent_a[1] * tangent_b[2] - tangent_a[2] * tangent_b[1])",
            "        + motion[1] * (tangent_a[2] * tangent_b[0] - tangent_a[0] * tangent_b[2])",
            "        + motion[2] * (tangent_a[0] * tangent_b[1] - tangent_a[1] * tangent_b[0])",
            "    )",
        ])
    divisor = 2.0 if planar else (24.0 if axes == [3, 4, 5] else 3.0)
    lines.extend([
        "    integral = integral + weight * orientation * integrand",
        f"return abs(integral) / {divisor!r}",
    ])
    return "\n".join(lines)
