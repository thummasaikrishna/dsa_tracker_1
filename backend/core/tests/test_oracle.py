from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Question, TestCase as QuestionTestCase
from core.oracle import ReferenceSolutionNotVerified, generate_expected_output, validate_reference_solution


def sandbox_result(kind="ok", stdout="42\n"):
    return {"kind": kind, "stdout": stdout, "stderr": "private detail", "compile_output": "private detail"}


class OracleTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("oracle-admin", password="pass12345")
        self.admin.profile.role = "admin"
        self.admin.profile.save()
        self.question = Question.objects.create(
            title="Oracle test",
            difficulty="easy",
            deadline=timezone.now() + timedelta(days=1),
            reference_solution="print(input())",
            examples="Input:\n42\nOutput:\n42\nExplanation:\nSmoke test.",
        )

    def test_reference_solution_starts_draft_and_cannot_be_promoted_directly(self):
        self.assertEqual(self.question.reference_solution_status, Question.REFERENCE_SOLUTION_DRAFT)
        self.question.reference_solution_status = Question.REFERENCE_SOLUTION_VERIFIED
        self.question.save()
        self.question.refresh_from_db()
        self.assertEqual(self.question.reference_solution_status, Question.REFERENCE_SOLUTION_DRAFT)

    def test_unverified_solution_cannot_generate_expected_output(self):
        with self.assertRaises(ReferenceSolutionNotVerified):
            generate_expected_output(self.question, "anything")

    @patch("core.oracle.execute_once", return_value=sandbox_result(stdout="42\n"))
    def test_valid_solution_is_verified_only_after_sandbox_validation(self, executor):
        result = validate_reference_solution(self.question)
        self.question.refresh_from_db()
        self.assertTrue(result.ok)
        self.assertEqual(self.question.reference_solution_status, Question.REFERENCE_SOLUTION_VERIFIED)
        executor.assert_called_once_with("print(input())", "python", "42")

    @patch("core.oracle.execute_once", return_value=sandbox_result(kind="compilation_error"))
    def test_compilation_failure_is_safe_failed_status(self, _executor):
        validate_reference_solution(self.question)
        self.question.refresh_from_db()
        self.assertEqual(self.question.reference_solution_status, Question.REFERENCE_SOLUTION_FAILED)
        self.assertEqual(self.question.reference_solution_error, "Reference solution did not compile.")
        self.assertNotIn("private", self.question.reference_solution_error)

    @patch("core.oracle.execute_once", return_value=sandbox_result(kind="runtime_error"))
    def test_runtime_failure_is_safe_failed_status(self, _executor):
        validate_reference_solution(self.question)
        self.question.refresh_from_db()
        self.assertEqual(self.question.reference_solution_error, "Reference solution failed while running.")

    @patch("core.oracle.execute_once", return_value=sandbox_result(kind="time_limit_exceeded"))
    def test_timeout_is_safe_failed_status(self, _executor):
        validate_reference_solution(self.question)
        self.question.refresh_from_db()
        self.assertEqual(self.question.reference_solution_error, "Reference solution exceeded the execution time limit.")

    @patch("core.oracle.execute_once", return_value=sandbox_result(stdout="trusted\n"))
    def test_oracle_output_is_normalized_and_ignores_ai_candidate_output(self, _executor):
        self.question.examples = "Input:\n42\nOutput:\ntrusted\nExplanation:\nTrusted output."
        self.question.save(update_fields=["examples"])
        validate_reference_solution(self.question)
        self.assertEqual(generate_expected_output(self.question, "input"), "trusted")

    @patch("core.oracle.execute_once", return_value=sandbox_result(stdout="oracle answer\n"))
    def test_oracle_endpoint_stores_only_sandbox_output(self, _executor):
        self.question.title = "Binary Search"
        self.question.description = "Constraints: 1 <= n <= 5. Input array is sorted."
        self.question.examples = "Input:\n1 5\n5\nOutput:\noracle answer\nExplanation:\nSingle element."
        self.question.save(update_fields=["title", "description", "examples"])
        validate_reference_solution(self.question)
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post(
            f"/api/questions/{self.question.id}/generate_oracle_testcase/",
            {"input_data": "1\n5\n5", "expected_output": "WRONG_OUTPUT", "is_hidden": True},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        case = QuestionTestCase.objects.get(question=self.question)
        self.assertEqual(case.expected_output, "oracle answer")
        self.assertEqual(case.verification_status, QuestionTestCase.VERIFICATION_VERIFIED)
        self.assertTrue(case.is_hidden)

    def test_oracle_endpoint_refuses_unverified_reference_solution(self):
        self.question.title = "Binary Search"
        self.question.description = "Constraints: 1 <= n <= 5. Input array is sorted."
        self.question.save(update_fields=["title", "description"])
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post(
            f"/api/questions/{self.question.id}/generate_oracle_testcase/",
            {"input_data": "1\n5\n5", "expected_output": "WRONG_OUTPUT"},
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(QuestionTestCase.objects.count(), 0)

    @patch("core.oracle.execute_once", return_value=sandbox_result(stdout="0\n"))
    def test_oracle_rejects_whitespace_normalized_duplicate_candidate(self, _executor):
        self.question.title = "Binary Search"
        self.question.description = "Constraints: 1 <= n <= 5. Input array is sorted."
        self.question.examples = "Input:\n1 5\n5\nOutput:\n0\nExplanation:\nSingle element."
        self.question.save(update_fields=["title", "description", "examples"])
        self.assertTrue(validate_reference_solution(self.question).ok)
        QuestionTestCase.objects.create(question=self.question, input_data="1 5\n5", expected_output="0")
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post(
            f"/api/questions/{self.question.id}/generate_oracle_testcase/",
            {"input_data": "1   5\r\n5\n"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Duplicate", response.data["input_data"])

    def test_reference_solution_is_admin_only_in_question_api(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        admin_response = client.get(f"/api/questions/{self.question.id}/")
        self.assertEqual(admin_response.status_code, 200)
        self.assertEqual(admin_response.data["reference_solution"], "print(input())")

        student = User.objects.create_user("oracle-student", password="pass12345")
        client.force_authenticate(student)
        student_response = client.get(f"/api/questions/{self.question.id}/")
        self.assertEqual(student_response.status_code, 200)
        self.assertNotIn("reference_solution", student_response.data)
        self.assertNotIn("reference_solution_error", student_response.data)

    @patch("core.oracle.execute_once")
    def test_invalid_phase_two_candidate_never_calls_oracle(self, executor):
        self.question.title = "Binary Search"
        self.question.description = "Input constraints: 1 <= n <= 5."
        self.question.save(update_fields=["title", "description"])
        self.question.reference_solution_status = Question.REFERENCE_SOLUTION_VERIFIED
        self.question._reference_validation_in_progress = True
        self.question.save(update_fields=["reference_solution_status"])
        del self.question._reference_validation_in_progress
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post(
            f"/api/questions/{self.question.id}/generate_oracle_testcase/",
            {"input_data": "0"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["state"], "invalid_candidate")
        executor.assert_not_called()

    @patch("core.oracle.execute_once", return_value=sandbox_result(stdout="3\n"))
    def test_wrong_ai_expected_output_is_replaced_by_oracle_output(self, _executor):
        self.question.title = "Binary Search"
        self.question.description = "Constraints: 1 <= n <= 10. Input array is sorted."
        self.question.examples = "Input:\n5 7\n1 3 5 7 9\nOutput:\n3\nExplanation:\nTarget index."
        self.question.save(update_fields=["title", "description", "examples"])
        self.assertTrue(validate_reference_solution(self.question).ok)
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post(
            f"/api/questions/{self.question.id}/generate_oracle_testcase/",
            {"input_data": "5 7\n1 3 5 7 9", "expected_output": "999"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(QuestionTestCase.objects.get(question=self.question).expected_output, "3")

    @patch("core.oracle.execute_once", return_value=sandbox_result(stdout="0\n"))
    def test_awaiting_candidates_can_be_processed_after_reference_verification(self, _executor):
        self.question.title = "Binary Search"
        self.question.description = "Constraints: 1 <= n <= 10. Input array is sorted."
        self.question.save(update_fields=["title", "description"])
        self.question.reference_solution_status = Question.REFERENCE_SOLUTION_VERIFIED
        self.question._reference_validation_in_progress = True
        self.question.save(update_fields=["reference_solution_status"])
        del self.question._reference_validation_in_progress
        case = QuestionTestCase.objects.create(
            question=self.question,
            input_data="1 5\n5",
            verification_status=QuestionTestCase.VERIFICATION_REQUIRES_REVIEW,
            verification_reason="AI generated candidate input only.",
        )
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post(f"/api/questions/{self.question.id}/generate_expected_outputs/")
        self.assertEqual(response.status_code, 200)
        case.refresh_from_db()
        self.assertEqual(case.expected_output, "0")
        self.assertEqual(case.verification_status, QuestionTestCase.VERIFICATION_VERIFIED)

    def test_awaiting_candidate_is_saved_but_never_visible_or_judged_for_student(self):
        awaiting = QuestionTestCase.objects.create(
            question=self.question,
            input_data="candidate input",
            expected_output="",
            is_hidden=False,
            verification_status=QuestionTestCase.VERIFICATION_REQUIRES_REVIEW,
        )
        student = User.objects.create_user("awaiting-student", password="pass12345")
        client = APIClient()
        client.force_authenticate(student)
        response = client.get(f"/api/questions/{self.question.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(awaiting.input_data, str(response.data))

    @patch("core.oracle.execute_once", return_value=sandbox_result(stdout="7\n"))
    def test_verified_examples_are_checked_without_student_submissions(self, _executor):
        QuestionTestCase.objects.create(
            question=self.question,
            input_data="seven",
            expected_output="7",
            verification_status=QuestionTestCase.VERIFICATION_VERIFIED,
        )
        self.assertTrue(validate_reference_solution(self.question).ok)

    @patch("core.oracle.execute_once", return_value=sandbox_result(stdout="not expected\n"))
    def test_failed_verified_example_does_not_trust_reference_solution(self, _executor):
        QuestionTestCase.objects.create(
            question=self.question,
            input_data="seven",
            expected_output="7",
            verification_status=QuestionTestCase.VERIFICATION_VERIFIED,
        )
        self.assertFalse(validate_reference_solution(self.question).ok)
        self.question.refresh_from_db()
        self.assertEqual(self.question.reference_solution_status, Question.REFERENCE_SOLUTION_FAILED)
