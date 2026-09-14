"""Security Phase 4: scoped throttles for expensive authenticated operations."""

from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import UserRateThrottle

from core.models import Assignment, Question
from core.models import TestCase as QuestionTestCase


def _judge_outcome():
    return {
        "status": "accepted",
        "tests_passed": 1,
        "total_tests": 1,
        "execution_time": 0.01,
        "memory_used": None,
        "compile_output": "",
        "results": [{"index": 1, "status": "passed", "hidden": False}],
    }


class ExpensiveOperationThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user("rate-admin", password="StrongPass123!")
        self.admin.profile.role = "admin"
        self.admin.profile.save()
        self.student = User.objects.create_user("rate-student", password="StrongPass123!")
        self.question = Question.objects.create(
            title="Rate limited echo",
            difficulty="easy",
            created_by=self.admin,
            deadline=timezone.now() + timedelta(days=1),
        )
        QuestionTestCase.objects.create(
            question=self.question,
            input_data="1\n",
            expected_output="1",
            is_hidden=False,
            order=0,
        )
        Assignment.objects.create(user=self.student, question=self.question, status="assigned")
        self.client = APIClient()

    def _rates(self, **overrides):
        return {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], **overrides}

    def _throttle_settings(self, **overrides):
        rates = self._rates(**overrides)
        return override_settings(
            REST_FRAMEWORK={**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": rates}
        ), rates

    def _assert_throttled(self, response):
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["success"], False)
        self.assertEqual(response.data["error"]["code"], "throttled")
        self.assertNotIn("provider", str(response.data).lower())

    def test_code_execution_is_throttled_before_sandbox_execution(self):
        scope, rates = self._throttle_settings(code_execution="2/min")
        self.client.force_authenticate(self.student)
        payload = {"question_id": self.question.id, "language": "python", "source_code": "print(1)"}
        with scope, patch.object(UserRateThrottle, "THROTTLE_RATES", rates), patch(
            "core.code_views.evaluate_cases", return_value=_judge_outcome()
        ) as evaluate:
            self.assertEqual(self.client.post("/api/code/run/", payload, format="json").status_code, 200)
            self.assertEqual(self.client.post("/api/code/run/", payload, format="json").status_code, 200)
            self._assert_throttled(self.client.post("/api/code/run/", payload, format="json"))
        self.assertEqual(evaluate.call_count, 2)

    def test_code_submission_is_throttled_before_judging_and_persistence(self):
        scope, rates = self._throttle_settings(code_submission="2/min")
        self.client.force_authenticate(self.student)
        payload = {"question_id": self.question.id, "language": "python", "source_code": "print(1)"}
        with scope, patch.object(UserRateThrottle, "THROTTLE_RATES", rates), patch(
            "core.code_views.evaluate_cases", return_value=_judge_outcome()
        ) as evaluate:
            self.assertEqual(self.client.post("/api/code/submit/", payload, format="json").status_code, 201)
            self.assertEqual(self.client.post("/api/code/submit/", payload, format="json").status_code, 201)
            self._assert_throttled(self.client.post("/api/code/submit/", payload, format="json"))
        self.assertEqual(evaluate.call_count, 2)
        self.assertEqual(self.question.code_submissions.count(), 2)

    def test_ai_generation_is_throttled_before_provider_request(self):
        scope, rates = self._throttle_settings(ai_generation="2/min")
        self.client.force_authenticate(self.admin)
        payload = {"title": "Rate test", "problem_statement": "Generate a small valid problem."}
        generated = {
            "difficulty": "Easy",
            "prerequisites": ["Arrays"],
            "examples": [
                {"input": "1", "output": "1", "explanation": "One echoes one."},
                {"input": "2", "output": "2", "explanation": "Two echoes two."},
            ],
            "public_test_cases": [{"input": "1", "output": "1"}, {"input": "2", "output": "2"}],
            "hidden_test_cases": [
                {"input": "3", "output": "3"}, {"input": "4", "output": "4"},
                {"input": "5", "output": "5"}, {"input": "6", "output": "6"},
            ],
        }
        import json
        with scope, patch.object(UserRateThrottle, "THROTTLE_RATES", rates), patch(
            "core.agents.fallback_manager.complete_chat", return_value=json.dumps(generated)
        ) as complete_chat:
            self.assertEqual(self.client.post("/api/admin/ai/generate-question-data/", payload, format="json").status_code, 200)
            payload["problem_statement"] = "Generate a different valid problem."
            self.assertEqual(self.client.post("/api/admin/ai/generate-question-data/", payload, format="json").status_code, 200)
            self._assert_throttled(self.client.post("/api/admin/ai/generate-question-data/", payload, format="json"))
        self.assertEqual(complete_chat.call_count, 2)

    def test_authorization_is_still_enforced_before_expensive_work(self):
        self.client.force_authenticate(self.student)
        with patch("core.agents.fallback_manager.complete_chat") as complete_chat:
            response = self.client.post(
                "/api/admin/ai/generate-question-data/",
                {"problem_statement": "Generate a problem."},
                format="json",
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "permission_denied")
        complete_chat.assert_not_called()
