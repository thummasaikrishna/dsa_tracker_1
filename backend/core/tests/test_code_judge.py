from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Assignment, CodeSubmission, Question
from core.models import TestCase as QuestionTestCase


def _outcome(status="accepted", passed=2, total=2, results=None):
    return {
        "status": status,
        "tests_passed": passed,
        "total_tests": total,
        "execution_time": 0.01,
        "memory_used": None,
        "compile_output": "",
        "results": results or [
            {"index": 1, "status": "passed", "hidden": False, "input": "1", "expected": "1", "actual": "1"},
            {"index": 2, "status": "passed", "hidden": True},
        ],
    }


class CodeJudgeApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user("admincj", password="pass12345")
        self.admin.profile.role = "admin"
        self.admin.profile.save()
        self.student = User.objects.create_user("alice", password="pass12345", first_name="Alice")
        self.other = User.objects.create_user("bob", password="pass12345")
        now = timezone.now()
        self.question = Question.objects.create(
            title="Echo",
            difficulty="easy",
            created_by=self.admin,
            deadline=now + timedelta(days=3),
        )
        QuestionTestCase.objects.create(question=self.question, input_data="1\n", expected_output="1", is_hidden=False, order=0)
        QuestionTestCase.objects.create(question=self.question, input_data="secret\n", expected_output="ok", is_hidden=True, order=1)
        self.client = APIClient()
        self.client.force_authenticate(self.student)

    def test_student_question_hides_hidden_cases(self):
        res = self.client.get(f"/api/questions/{self.question.id}/")
        self.assertEqual(res.status_code, 200)
        cases = res.data["test_cases"]
        self.assertEqual(len(cases), 1)
        self.assertNotIn("is_hidden", cases[0])
        self.assertNotIn("secret", str(cases))
        self.assertIsNone(res.data.get("my_assignment_id"))

    def test_run_rejected_without_assignment(self):
        res = self.client.post(
            "/api/code/run/",
            {"question_id": self.question.id, "language": "python", "source_code": "print(1)"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertFalse(res.data.get("success", True))
        self.assertIn("assign this question", res.data.get("message", "").lower())

    def test_submit_rejected_without_assignment(self):
        res = self.client.post(
            "/api/code/submit/",
            {"question_id": self.question.id, "language": "python", "source_code": "print(1)"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(CodeSubmission.objects.count(), 0)
        self.assertFalse(Assignment.objects.filter(user=self.student, question=self.question).exists())

    def test_question_includes_assignment_id_after_assign(self):
        assignment = Assignment.objects.create(user=self.student, question=self.question, status="assigned")
        res = self.client.get(f"/api/questions/{self.question.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["is_assigned_to_me"])
        self.assertEqual(res.data["my_assignment_id"], assignment.id)

    @patch("core.code_views.evaluate_cases", return_value=_outcome())
    def test_submit_hides_hidden_io(self, mock_eval):
        Assignment.objects.create(user=self.student, question=self.question, status="assigned")
        mock_eval.return_value = _outcome(
            results=[
                {
                    "index": 1,
                    "status": "passed",
                    "hidden": False,
                    "input": "1",
                    "expected": "1",
                    "actual": "1",
                },
                {
                    "index": 2,
                    "status": "passed",
                    "hidden": True,
                    "input": "secret",
                    "expected": "ok",
                    "actual": "ok",
                    "stderr": "leak",
                },
            ]
        )
        res = self.client.post(
            "/api/code/submit/",
            {"question_id": self.question.id, "language": "python", "source_code": "print(1)"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        blob = str(res.data)
        self.assertNotIn("secret", blob)
        hidden = [r for r in res.data["public_results"] if r.get("hidden")]
        self.assertEqual(len(hidden), 1)
        self.assertNotIn("input", hidden[0])
        self.assertNotIn("expected", hidden[0])
        self.assertNotIn("actual", hidden[0])
        self.assertNotIn("stderr", hidden[0])

    @patch("core.code_views.evaluate_cases", return_value=_outcome())
    def test_run_does_not_create_submission_or_notify(self, _mock):
        Assignment.objects.create(user=self.student, question=self.question, status="assigned")
        res = self.client.post(
            "/api/code/run/",
            {"question_id": self.question.id, "language": "python", "source_code": "print(1)"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(CodeSubmission.objects.count(), 0)
        self.assertEqual(self.admin.notifications.filter(event="code_submitted").count(), 0)

    @patch("core.code_views.evaluate_cases", return_value=_outcome())
    def test_submit_stores_code_awards_once_and_notifies(self, _mock):
        Assignment.objects.create(user=self.student, question=self.question, status="assigned")
        res = self.client.post(
            "/api/code/submit/",
            {"question_id": self.question.id, "language": "python", "source_code": "print('full source')"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        sub = CodeSubmission.objects.get()
        self.assertEqual(sub.source_code, "print('full source')")
        self.assertEqual(sub.status, "accepted")
        self.assertEqual(sub.points_awarded, 10)
        assignment = Assignment.objects.get(user=self.student, question=self.question)
        self.assertEqual(assignment.points_awarded, 10)
        self.assertEqual(assignment.status, "completed")
        self.assertEqual(self.admin.notifications.filter(event="code_submitted").count(), 1)
        self.assertEqual(self.student.notifications.filter(event="code_result").count(), 1)

        res2 = self.client.post(
            "/api/code/submit/",
            {"question_id": self.question.id, "language": "python", "source_code": "print('again')"},
            format="json",
        )
        self.assertEqual(res2.status_code, 201)
        self.assertEqual(CodeSubmission.objects.count(), 2)
        self.assertEqual(CodeSubmission.objects.order_by("id").last().points_awarded, 0)
        assignment.refresh_from_db()
        self.assertEqual(assignment.points_awarded, 10)

    def test_student_cannot_read_other_submission(self):
        other_sub = CodeSubmission.objects.create(
            user=self.other,
            question=self.question,
            language="python",
            source_code="secret-code",
            status="accepted",
        )
        res = self.client.get(f"/api/code/submissions/{other_sub.id}/")
        self.assertEqual(res.status_code, 404)
