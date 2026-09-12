from django.test import SimpleTestCase

from core.agents.constraint_validator import (
    STATUS_UNKNOWN,
    ConstraintValidator,
    normalize_candidate_input,
    parse_problem_constraints,
    validate_generated_candidates,
)


class ConstraintValidatorTests(SimpleTestCase):
    def setUp(self):
        self.validator = ConstraintValidator()
        self.scalar_spec = {
            "status": "READY",
            "fields": [{"name": "n", "type": "integer", "min": 1, "max": 5}],
            "relations": [],
            "rules": [],
        }
        self.array_spec = {
            "status": "READY",
            "fields": [
                {"name": "n", "type": "integer", "min": 1, "max": 4},
                {"name": "nums", "type": "array", "length_ref": "n", "element_type": "integer", "element_min": -3, "element_max": 3, "non_empty": True},
            ],
            "relations": [],
            "rules": [],
        }
        self.matrix_spec = {
            "status": "READY",
            "fields": [
                {"name": "n", "type": "integer", "min": 1, "max": 3},
                {"name": "m", "type": "integer", "min": 1, "max": 3},
                {"name": "matrix", "type": "matrix", "rows_ref": "n", "cols_ref": "m", "element_type": "integer", "element_min": 0, "element_max": 9},
            ],
            "relations": [],
            "rules": [],
        }

    def test_integer_within_range_is_valid(self):
        self.assertTrue(self.validator.validate("3", self.scalar_spec).valid)

    def test_integer_below_min_is_invalid(self):
        self.assertFalse(self.validator.validate("0", self.scalar_spec).valid)

    def test_integer_above_max_is_invalid(self):
        self.assertFalse(self.validator.validate("6", self.scalar_spec).valid)

    def test_array_correct_length_is_valid(self):
        self.assertTrue(self.validator.validate("3\n-1 0 3", self.array_spec).valid)

    def test_array_wrong_length_is_invalid(self):
        self.assertFalse(self.validator.validate("3\n1 2", self.array_spec).valid)

    def test_array_element_outside_range_is_invalid(self):
        self.assertFalse(self.validator.validate("2\n1 4", self.array_spec).valid)

    def test_empty_required_array_is_invalid(self):
        spec = {**self.array_spec, "fields": [dict(self.array_spec["fields"][0], min=0), self.array_spec["fields"][1]]}
        self.assertFalse(self.validator.validate("0", spec).valid)

    def test_string_lengths_and_allowed_characters(self):
        spec = {"status": "READY", "fields": [{"name": "s", "type": "string", "min_length": 2, "max_length": 4, "allowed_pattern": "[a-z]+"}], "relations": [], "rules": []}
        self.assertTrue(self.validator.validate("abc", spec).valid)
        self.assertFalse(self.validator.validate("abcdef", spec).valid)
        self.assertFalse(self.validator.validate("A1", spec).valid)

    def test_matrix_valid_dimensions(self):
        self.assertTrue(self.validator.validate("2 2\n1 2\n3 4", self.matrix_spec).valid)

    def test_matrix_invalid_row_count_is_invalid(self):
        self.assertFalse(self.validator.validate("3 2\n1 2\n3 4", self.matrix_spec).valid)

    def test_matrix_invalid_column_count_is_invalid(self):
        self.assertFalse(self.validator.validate("2 3\n1 2\n3 4", self.matrix_spec).valid)

    def test_matrix_non_rectangular_input_is_invalid(self):
        self.assertFalse(self.validator.validate("2 2\n1 2\n3", self.matrix_spec).valid)
        self.assertFalse(self.validator.validate("2 2\n1\n2 3 4", self.matrix_spec).valid)

    def test_relational_constraint_k_le_n(self):
        spec = {"status": "READY", "fields": [{"name": "n", "type": "integer"}, {"name": "k", "type": "integer"}], "relations": [("k", "<=", "n")], "rules": []}
        self.assertTrue(self.validator.validate("5 3", spec).valid)
        self.assertFalse(self.validator.validate("5 6", spec).valid)

    def test_array_length_relation_is_enforced(self):
        self.assertFalse(self.validator.validate("2\n1", self.array_spec).valid)

    def test_duplicate_detection_across_public_and_hidden_cases(self):
        payload = {
            "public_test_cases": [{"input": "3\n1 2 3\n2"}],
            "hidden_test_cases": [{"input": "3  1 2 3  2"}],
        }
        result = validate_generated_candidates(payload, "Binary Search", "1 <= n <= 5. Input array is sorted.")
        self.assertEqual(len(result["public_test_cases"]), 1)
        self.assertEqual(result["hidden_test_cases"], [])

    def test_whitespace_normalized_duplicate_detection(self):
        self.assertEqual(normalize_candidate_input("1  2\r\n3"), normalize_candidate_input("1 2 3"))

    def test_public_and_hidden_cases_are_validated(self):
        statement = "Constraints: 1 <= n <= 5. Input uses n, n sorted integers, then target."
        payload = {
            "public_test_cases": [{"input": "3\n1 2 3\n2"}],
            "hidden_test_cases": [{"input": "3\n3 2 1\n2"}],
        }
        result = validate_generated_candidates(payload, "Binary Search", statement)
        self.assertEqual(len(result["public_test_cases"]), 1)
        self.assertEqual(result["hidden_test_cases"], [])

    def test_unknown_constraints_are_not_silently_valid(self):
        spec = parse_problem_constraints("Novel problem", "Solve this efficiently.")
        result = self.validator.validate("1", spec)
        self.assertFalse(result.valid)
        self.assertEqual(result.status, STATUS_UNKNOWN)

    def test_problem_specific_matrix_rule_hook(self):
        spec = {**self.matrix_spec, "rules": ["matrix_no_adjacent_equal"]}
        self.assertFalse(self.validator.validate("2 2\n1 1\n2 3", spec).valid)
        self.assertTrue(self.validator.validate("2 2\n1 2\n3 4", spec).valid)

    def test_binary_search_constraints(self):
        spec = parse_problem_constraints("Binary Search", "1 <= n <= 5. The input array is sorted.")
        self.assertTrue(self.validator.validate("3\n1 2 3\n2", spec).valid)
        self.assertTrue(self.validator.validate("3 2\n1 2 3", spec).valid)
        self.assertFalse(self.validator.validate("3\n1 3 2\n2", spec).valid)
        self.assertFalse(self.validator.validate("6\n1 2 3 4 5 6\n2", spec).valid)

    def test_two_sum_and_maximum_subarray_formats(self):
        two_sum = parse_problem_constraints("Two Sum", "1 <= n <= 4.")
        maximum = parse_problem_constraints("Maximum Subarray", "1 <= n <= 4.")
        self.assertTrue(self.validator.validate("3\n2 7 11\n9", two_sum).valid)
        self.assertTrue(self.validator.validate("3\n-2 -1 -3", maximum).valid)

    def test_peak_matrix_and_rotate_array_formats(self):
        peak = parse_problem_constraints("Find Peak Element (2D Matrix)", "1 <= n <= 3, 1 <= m <= 3. No two adjacent cells are equal.")
        rotate = parse_problem_constraints("Rotate Array", "1 <= n <= 4, 0 <= k <= n.")
        self.assertTrue(self.validator.validate("2 2\n1 2\n3 4", peak).valid)
        self.assertFalse(self.validator.validate("2 2\n1 1\n3 4", peak).valid)
        self.assertTrue(self.validator.validate("3\n1 2 3\n3", rotate).valid)
        self.assertFalse(self.validator.validate("3\n1 2 3\n4", rotate).valid)
