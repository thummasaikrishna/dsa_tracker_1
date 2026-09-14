"""Security Phase 5 audit, abuse, and regression coverage."""

from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import UserRateThrottle
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from core.audit import audit_event
from core.exception_handler import api_exception_handler
from core.executor import ExecutorUnavailable
from core.models import Assignment, AuditLog, Question
from core.models import TestCase as QuestionTestCase


class SecurityPhase5Tests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.admin = User.objects.create_user("phase5-admin", password="StrongPass123!")
        self.admin.profile.role = "admin"
        self.admin.profile.save(update_fields=["role"])
        self.student = User.objects.create_user("phase5-student", password="StrongPass123!")
        self.other = User.objects.create_user("phase5-other", password="StrongPass123!")
        self.question = Question.objects.create(
            title="Phase 5 echo", difficulty="easy", created_by=self.admin,
            deadline=timezone.now() + timedelta(days=1),
        )
        QuestionTestCase.objects.create(question=self.question, input_data="1\n", expected_output="1", order=0)
        self.assignment = Assignment.objects.create(user=self.student, question=self.question)
        self.other_assignment = Assignment.objects.create(user=self.other, question=self.question)

    def _error(self, response, status_code, code):
        self.assertEqual(response.status_code, status_code)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], code)

    def test_login_logout_and_failed_login_are_audited_without_credentials(self):
        failed = self.client.post("/api/auth/login/", {"username": "phase5-student", "password": "wrong"}, format="json")
        self._error(failed, 401, "authentication_failed")
        self.assertTrue(AuditLog.objects.filter(event_type=AuditLog.AUTH_LOGIN_FAILURE, success=False).exists())

        success = self.client.post("/api/auth/login/", {"username": "phase5-student", "password": "StrongPass123!"}, format="json")
        self.assertEqual(success.status_code, 200)
        self.assertTrue(AuditLog.objects.filter(event_type=AuditLog.AUTH_LOGIN_SUCCESS, user=self.student, success=True).exists())
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {success.data['access']}")
        self.assertEqual(self.client.post("/api/auth/logout/", {"refresh": success.data["refresh"]}, format="json").status_code, 200)
        self.assertTrue(AuditLog.objects.filter(event_type=AuditLog.AUTH_LOGOUT, user=self.student).exists())
        stored = str(AuditLog.objects.values_list("metadata", flat=True))
        self.assertNotIn("StrongPass123", stored)
        self.assertNotIn(success.data["refresh"], stored)
        self.assertNotIn(success.data["access"], stored)

    def test_refresh_reuse_invalid_and_removed_account_access_are_audited(self):
        refresh = str(RefreshToken.for_user(self.student))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.student)}")
        self.client.post("/api/auth/logout/", {"refresh": refresh}, format="json")
        self.client.credentials()
        response = self.client.post("/api/auth/refresh/", {"refresh": refresh}, format="json")
        self._error(response, 401, "authentication_failed")
        self.assertTrue(AuditLog.objects.filter(event_type=AuditLog.AUTH_REFRESH_FAILURE).exists())

        expired = AccessToken.for_user(self.student)
        expired.set_exp(lifetime=timedelta(seconds=-1))
        self._error(self.client.get("/api/auth/me/", HTTP_AUTHORIZATION=f"Bearer {expired}"), 401, "authentication_failed")
        self.assertTrue(AuditLog.objects.filter(event_type=AuditLog.AUTH_TOKEN_FAILURE).exists())

        self.student.profile.is_removed = True
        self.student.profile.save(update_fields=["is_removed"])
        valid = AccessToken.for_user(self.student)
        self._error(self.client.get("/api/auth/me/", HTTP_AUTHORIZATION=f"Bearer {valid}"), 401, "authentication_failed")
        self.assertTrue(AuditLog.objects.filter(event_type=AuditLog.AUTH_REMOVED_ACCOUNT_ACCESS).exists())

    def test_permission_denial_and_idor_remain_protected_and_audited(self):
        self.client.force_authenticate(self.student)
        denied = self.client.post(
            "/api/admin/ai/generate-question-data/", {"problem_statement": "Generate a problem."}, format="json"
        )
        self._error(denied, 403, "permission_denied")
        self.assertTrue(AuditLog.objects.filter(event_type=AuditLog.AUTH_PERMISSION_DENIED, user=self.student).exists())
        self._error(self.client.get(f"/api/assignments/{self.other_assignment.id}/"), 404, "not_found")
        self._error(self.client.patch(f"/api/assignments/{self.other_assignment.id}/status_update/", {"status": "completed"}, format="json"), 404, "not_found")
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(f"/api/assignments/{self.other_assignment.id}/").status_code, 200)

    def test_input_attacks_keep_the_existing_safe_error_contract(self):
        self._error(self.client.generic("POST", "/api/auth/register/", b"{", content_type="application/json"), 400, "parse_error")
        self.client.force_authenticate(self.admin)
        self._error(self.client.get("/api/questions/", {"ordering": "unknown"}), 400, "validation_error")
        self._error(self.client.get("/api/questions/", {"page_size": "999"}), 400, "validation_error")
        self.assertTrue(AuditLog.objects.filter(event_type=AuditLog.VALIDATION_FAILURE).exists())

    def test_code_execution_throttle_is_audited_before_sandbox_work(self):
        rates = {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "code_execution": "1/min"}
        self.client.force_authenticate(self.student)
        payload = {"question_id": self.question.id, "language": "python", "source_code": "print(1)"}
        outcome = {"status": "accepted", "tests_passed": 1, "total_tests": 1, "execution_time": 0, "memory_used": None, "compile_output": "", "results": []}
        with override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": rates}), patch.object(UserRateThrottle, "THROTTLE_RATES", rates), patch("core.code_views.evaluate_cases", return_value=outcome) as evaluate:
            self.assertEqual(self.client.post("/api/code/run/", payload, format="json").status_code, 200)
            self._error(self.client.post("/api/code/run/", payload, format="json"), 429, "throttled")
        evaluate.assert_called_once()
        self.assertTrue(AuditLog.objects.filter(event_type=AuditLog.CODE_EXECUTION_THROTTLED).exists())

    def test_submission_and_ai_throttles_are_audited_before_expensive_work(self):
        submission_rates = {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "code_submission": "1/min"}
        self.client.force_authenticate(self.student)
        payload = {"question_id": self.question.id, "language": "python", "source_code": "print(1)"}
        outcome = {"status": "accepted", "tests_passed": 1, "total_tests": 1, "execution_time": 0, "memory_used": None, "compile_output": "", "results": []}
        with override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": submission_rates}), patch.object(UserRateThrottle, "THROTTLE_RATES", submission_rates), patch("core.code_views.evaluate_cases", return_value=outcome) as evaluate:
            self.assertEqual(self.client.post("/api/code/submit/", payload, format="json").status_code, 201)
            self._error(self.client.post("/api/code/submit/", payload, format="json"), 429, "throttled")
        evaluate.assert_called_once()
        self.assertTrue(AuditLog.objects.filter(event_type=AuditLog.CODE_SUBMISSION_THROTTLED).exists())

        cache.clear()
        ai_rates = {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "ai_generation": "1/min"}
        self.client.force_authenticate(self.admin)
        generated = {
            "difficulty": "Easy", "prerequisites": ["Arrays"],
            "examples": [
                {"input": "1", "output": "1", "explanation": "Echo one."},
                {"input": "2", "output": "2", "explanation": "Echo two."},
            ],
            "public_test_cases": [{"input": "1", "output": "1"}, {"input": "2", "output": "2"}],
            "hidden_test_cases": [{"input": str(value), "output": str(value)} for value in range(3, 7)],
        }
        import json
        ai_payload = {"title": "Rate test", "problem_statement": "Generate a valid problem."}
        with override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": ai_rates}), patch.object(UserRateThrottle, "THROTTLE_RATES", ai_rates), patch("core.agents.fallback_manager.complete_chat", return_value=json.dumps(generated)) as complete_chat:
            self.assertEqual(self.client.post("/api/admin/ai/generate-question-data/", ai_payload, format="json").status_code, 200)
            self._error(self.client.post("/api/admin/ai/generate-question-data/", ai_payload, format="json"), 429, "throttled")
        complete_chat.assert_called_once()
        self.assertTrue(AuditLog.objects.filter(event_type=AuditLog.AI_GENERATION_THROTTLED).exists())

    def test_audit_log_sanitizes_injection_and_error_responses_hide_internals(self):
        fake_token = "Bearer test-credential-value"
        request = RequestFactory().post("/api/test/", HTTP_USER_AGENT=f"browser\nforged-entry {fake_token}")
        audit_event(AuditLog.AUTH_LOGIN_FAILURE, request, metadata={"reason": "bad\nvalue", "password": "never-store", "scope": "token-value"})
        entry = AuditLog.objects.get(event_type=AuditLog.AUTH_LOGIN_FAILURE)
        self.assertNotIn("\n", entry.user_agent)
        self.assertNotIn(fake_token, entry.user_agent)
        self.assertEqual(entry.metadata, {"reason": "bad value"})

        unexpected = api_exception_handler(RuntimeError("internal-secret-path"), {"request": request})
        self._error(unexpected, 500, "server_error")
        self.assertNotIn("internal-secret", str(unexpected.data))

        self.client.force_authenticate(self.student)
        with patch("core.code_views.evaluate_cases", side_effect=ExecutorUnavailable("provider.internal secret")):
            response = self.client.post("/api/code/run/", {"question_id": self.question.id, "language": "python", "source_code": "print(1)"}, format="json")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("provider.internal", str(response.data))

    def test_audit_persistence_failure_does_not_break_login(self):
        with patch("core.audit.AuditLog.objects.create", side_effect=RuntimeError("database unavailable")):
            response = self.client.post("/api/auth/login/", {"username": "phase5-student", "password": "StrongPass123!"}, format="json")
        self.assertEqual(response.status_code, 200)
