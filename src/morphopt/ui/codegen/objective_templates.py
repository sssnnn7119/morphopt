"""Objective-function wizard templates (inserted into the objective code slot)."""

from __future__ import annotations

#: scheme -> list of (name, objective_body, metrics_body)
OBJECTIVE_TEMPLATES: dict[str, list[dict]] = {
    "shapeopt": [
        {
            "name": "Tip displacement (single step)",
            "objective": "return self.fe_results[0].GC[-2]\n",
            "metrics": "return [self.fe_results[0].GC[-2]]\n",
            "jacobian_needed": [],
        },
        {
            "name": "Mean of all load steps",
            "objective": "vals = [r.GC[-2] for r in self.fe_results]\nreturn sum(vals) / len(vals)\n",
            "metrics": "return [r.GC[-2] for r in self.fe_results]\n",
            "jacobian_needed": [],
        },
    ],
    "simp": [
        {
            "name": "Strain energy / compliance",
            "objective": (
                "RGC = self.fe.assembly._GC2RGC(self.fe_results[0].GC)\n"
                "return self.fe.assembly.get_instance('final_model').potential_energy(RGC=RGC)\n"
            ),
            "metrics": "return []\n",
            "jacobian_needed": [],
        },
    ],
    "codesign": [
        {
            "name": "Tip motion between steps (pressurised)",
            "objective": "return self.fe_results[1].GC[-2] - self.fe_results[0].GC[-2]\n",
            "metrics": "return [self.fe_results[1].GC[-2]]\n",
            "jacobian_needed": [],
        },
        {
            "name": "Motion + stiffness from RP jacobians",
            "objective": (
                "# motion + stiffness objective; adapt load names to your problem\n"
                "jac_end = torch.cat([self.fe_results[0].jacobian['force_RP_head'][-6:],\n"
                "                     self.fe_results[0].jacobian['moment_RP_head'][-6:]])\n"
                "motion = self.fe_results[1].GC[-2] - self.fe_results[0].GC[-2]\n"
                "return motion + 1e-6 * jac_end.abs().sum()\n"
            ),
            "metrics": "return [self.fe_results[1].GC[-2]]\n",
            "jacobian_needed": ["force_RP_head", "moment_RP_head"],
        },
    ],
}
