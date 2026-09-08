"""Regression tests for dependency-free code-slot completions."""

import unittest

from morphopt.ui.schemes.base import get_template
from morphopt.ui.widgets.code_completion import completion_items
from morphopt.ui.widgets.codeeditor import _CodeEdit


class CodeCompletionTests(unittest.TestCase):
    def setUp(self):
        self.problem = get_template("shapeopt").create_problem("completion")

    def test_objective_candidates_include_current_interface_names(self):
        items = completion_items("_objective_function", self.problem)
        inserted = {item.insert_text for item in items}

        self.assertIn("self.fe_results", inserted)
        self.assertIn("self.fe_results[0].GC[-2]", inserted)
        self.assertIn("self.fe_results[0].jacobian['pressure_1']", inserted)

    def test_surface_constraint_candidates_follow_current_surface_count(self):
        items = completion_items("_apply_surface_constraints", self.problem)
        inserted = {item.insert_text for item in items}

        self.assertIn("self.surface_list[0]", inserted)
        self.assertIn("self.surface_list[1]", inserted)

    def test_objective_candidates_follow_current_load_step_count(self):
        problem = get_template("codesign").create_problem("two-steps")
        inserted = {item.insert_text
                    for item in completion_items("_objective_function", problem)}

        self.assertIn("self.fe_results[0].GC[-2]", inserted)
        self.assertIn("self.fe_results[1].GC[-2]", inserted)
        self.assertIn("self.fe_results[1].jacobian", inserted)

    def test_member_completion_inserts_only_the_suffix(self):
        items = completion_items("_objective_function", self.problem)
        members = _CodeEdit._member_candidates(items, "self")

        self.assertIn("fe_results", {item.insert_text for item in members})
        self.assertNotIn("self.fe_results", {item.insert_text for item in members})

    def test_gc_tensor_members_are_offered_for_each_result_expression(self):
        expression = "self.fe_results[0].GC[-2]"
        items = completion_items(
            "_objective_function", self.problem, member_expression=expression)
        members = _CodeEdit._member_candidates(items, expression)

        self.assertIn("mean()", {item.insert_text for item in members})
        self.assertIn("reshape()", {item.insert_text for item in members})
        self.assertIn("shape", {item.insert_text for item in members})
