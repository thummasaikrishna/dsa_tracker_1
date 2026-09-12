"""Security Phase 3 regression tests for validation, CORS, and safe errors."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import Throttled
from rest_framework.test import APIClient

from core.exception_handler import api_exception_handler
from core.executor import ExecutorUnavailable
from core.models import Assignment, Question, TestCase as QuestionTestCase


class ValidationSecurityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user("validation-admin", password="StrongPass123!")
        self.admin.profile.role = "admin"
        self.admin.profile.save(update_fields=["role"])
        self.student = User.objects.create_user("validation-student", password="StrongPass123!")
        self.question = Question.objects.create(
            title="Validation question", difficulty="easy", created_by=self.admin,
            deadline=timezone.now() + timedelta(days=2),
        )
        self.assignment = Assignment.objects.create(user=self.student, question=self.question)

    def assert_error(self, response, status_code, code):
        self.assertEqual(response.status_code, status_code)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], code)

    def test_error_contract_for_parse_auth_permission_not_found_and_method(self):
        malformed = self.client.generic("POST", "/api/auth/register/", b"{", content_type="application/json")
        self.assert_error(malformed, 400, "parse_error")

        invalid_jwt = self.client.get("/api/auth/me/", HTTP_AUTHORIZATION="Bearer invalid")
        self.assert_error(invalid_jwt, 401, "authentication_failed")

        self.client.force_authenticate(self.student)
        forbidden = self.client.get("/api/analytics/overview/")
        self.assert_error(forbidden, 403, "permission_denied")
        missing = self.client.get("/api/questions/999999/")
        self.assert_error(missing, 404, "not_found")
        method = self.client.post("/api/auth/me/", {}, format="json")
        self.assert_error(method, 405, "method_not_allowed")

    def test_wrong_status_and_oracle_types_return_safe_400(self):
        self.client.force_authenticate(self.student)
        for payload in ({}, {"status": []}, {"status": {}}, {"status": None}, {"status": 123}):
            response = self.client.patch(f"/api/assignments/{self.assignment.id}/status_update/", payload, format="json")
            self.assert_error(response, 400, "validation_error")

        self.client.force_authenticate(self.admin)
        for payload in ({"input_data": []}, {"input_data": {}}, {"input_data": None}):
            response = self.client.post(f"/api/questions/{self.question.id}/generate_oracle_testcase/", payload, format="json")
            self.assert_error(response, 400, "validation_error")

    def test_question_testcase_and_search_limits_return_400(self):
        self.client.force_authenticate(self.admin)
        base = {
            "title": "Bounded", "difficulty": "easy", "deadline": (timezone.now() + timedelta(days=2)).isoformat(),
        }
        oversized_question = self.client.post("/api/questions/", {**base, "description": "x" * 50_001}, format="json")
        self.assert_error(oversized_question, 400, "validation_error")
        oversized_case = self.client.post(
            "/api/questions/",
            {**base, "title": "Bounded case", "test_cases": [{"input_data": "x" * 20_001, "expected_output": "ok"}]},
            format="json",
        )
        self.assert_error(oversized_case, 400, "validation_error")
        search = self.client.get("/api/questions/", {"search": "x" * 101})
        self.assert_error(search, 400, "validation_error")

    def test_invalid_query_parameters_return_400(self):
        self.client.force_authenticate(self.student)
        for query in (
            {"difficulty": "invalid"}, {"ordering": "unknown"}, {"page": "zero"}, {"page_size": "201"},
        ):
            self.assert_error(self.client.get("/api/questions/", query), 400, "validation_error")
        self.assert_error(self.client.get("/api/analytics/my-activity/", {"period": "forever"}), 400, "validation_error")
        self.assert_error(self.client.get("/api/analytics/my-activity/", {"difficulty": "invalid"}), 400, "validation_error")

    def test_executor_errors_are_sanitized(self):
        QuestionTestCase.objects.create(question=self.question, input_data="1", expected_output="1")
        self.client.force_authenticate(self.student)
        sensitive = "Execution service HTTP 502: internal-provider.example/path secret-detail"
        with patch("core.code_views.evaluate_cases", side_effect=ExecutorUnavailable(sensitive)):
            response = self.client.post("/api/code/run/", {"question_id": self.question.id, "language": "python", "source_code": "print(1)"}, format="json")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["detail"], "Code execution service is temporarily unavailable.")
        self.assertNotIn("internal-provider", str(response.data))
        self.assertNotIn("secret-detail", str(response.data))

    def test_throttled_and_unexpected_errors_have_safe_envelopes(self):
        request = RequestFactory().get("/api/test/")
        throttled = api_exception_handler(Throttled(), {"request": request})
        self.assertEqual(throttled.status_code, 429)
        self.assertEqual(throttled.data["error"]["code"], "throttled")
        unexpected = api_exception_handler(RuntimeError("filesystem C:\\secret"), {"request": request})
        self.assertEqual(unexpected.status_code, 500)
        self.assertEqual(unexpected.data["error"]["code"], "server_error")
        self.assertNotIn("filesystem", str(unexpected.data))


class CorsValidationTests(TestCase):
    def test_allowed_origin_and_untrusted_origin(self):
        with override_settings(CORS_ALLOWED_ORIGINS=["https://frontend.example.test"], CORS_ALLOW_ALL_ORIGINS=False):
            allowed = self.client.options("/api/auth/login/", HTTP_ORIGIN="https://frontend.example.test", HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST")
            self.assertEqual(allowed["Access-Control-Allow-Origin"], "https://frontend.example.test")
            denied = self.client.options("/api/auth/login/", HTTP_ORIGIN="https://untrusted.example.test", HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST")
            self.assertNotIn("Access-Control-Allow-Origin", denied)

    def test_production_origin_validation_rejects_unsafe_configuration(self):
        from dsatracker.settings import _validate_origins

        for origins, required in (([], True), (["*"], True), (["https://*.example.test"], True), (["https://frontend.example.test/path"], True), (["http://frontend.example.test"], True)):
            with self.assertRaises(ImproperlyConfigured):
                _validate_origins(origins, "CORS_ALLOWED_ORIGINS", production=True, required=required)
        with self.assertRaises(ImproperlyConfigured):
            _validate_origins(["not-an-origin"], "CSRF_TRUSTED_ORIGINS", production=True)
        _validate_origins(["https://frontend.example.test"], "CORS_ALLOWED_ORIGINS", production=True, required=True)
