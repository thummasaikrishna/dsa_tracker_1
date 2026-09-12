"""API regression tests for authentication, RBAC and removal safeguards."""

from datetime import timedelta
import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.test.utils import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Notification, Question


class AccessControlApiTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("access-admin", password="pass12345")
        self.admin.profile.role = "admin"
        self.admin.profile.save()
        self.student = User.objects.create_user("access-student", email="student@test.local", password="pass12345")
        self.question = Question.objects.create(
            title="Access Question", difficulty="easy", created_by=self.admin,
            deadline=timezone.now() + timedelta(days=2),
        )
        self.client = APIClient()

    def test_student_cannot_create_or_change_questions(self):
        self.client.force_authenticate(self.student)
        response = self.client.post("/api/questions/", {"title": "Nope"}, format="json")
        self.assertEqual(response.status_code, 403)
        response = self.client.patch(f"/api/questions/{self.question.id}/", {"title": "Nope"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_admin_creating_and_updating_question_notifies_students(self):
        self.client.force_authenticate(self.admin)
        created = self.client.post(
            "/api/questions/",
            {"title": "Created by admin", "difficulty": "easy", "deadline": (timezone.now() + timedelta(days=1)).isoformat()},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertTrue(Notification.objects.filter(user=self.student, event="new_question", question_id=created.data["id"]).exists())
        updated = self.client.patch(f"/api/questions/{created.data['id']}/", {"description": "Updated"}, format="json")
        self.assertEqual(updated.status_code, 200)
        self.assertTrue(Notification.objects.filter(user=self.student, event="question_updated", question_id=created.data["id"]).exists())

    def test_student_cannot_use_admin_analytics_or_ai_api(self):
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get("/api/analytics/students/").status_code, 403)
        self.assertEqual(
            self.client.post("/api/admin/ai/generate-question-data/", {"title": "x", "problem_statement": "x"}, format="json").status_code,
            403,
        )

    def test_removed_student_cannot_log_in_or_access_api(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"/api/analytics/students/{self.student.id}/remove/")
        self.assertEqual(response.status_code, 200)
        self.client.force_authenticate(None)
        login = self.client.post("/api/auth/login/", {"username": self.student.username, "password": "pass12345"}, format="json")
        self.assertEqual(login.status_code, 401)
        self.assertEqual(login.data.get("code"), "account_removed")


class SupabaseGoogleLoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.settings = override_settings(
            SUPABASE_URL="https://project.example.supabase.co",
            SUPABASE_PUBLISHABLE_KEY="public-test-key",
        )
        self.settings.enable()

    def tearDown(self):
        self.settings.disable()

    @staticmethod
    def supabase_user(**overrides):
        payload = {
            "id": "11111111-1111-1111-1111-111111111111",
            "email": "student@example.test",
            "email_confirmed_at": "2026-01-01T00:00:00Z",
            "app_metadata": {"provider": "google", "providers": ["google"]},
            "user_metadata": {"full_name": "Google Student"},
        }
        payload.update(overrides)
        return payload

    def mock_supabase_user(self, mocked_urlopen, payload):
        response = mocked_urlopen.return_value.__enter__.return_value
        response.read.return_value = json.dumps(payload).encode("utf-8")

    @patch("core.views.urlopen")
    def test_new_google_user_is_created_as_student(self, mocked_urlopen):
        self.mock_supabase_user(mocked_urlopen, self.supabase_user())
        response = self.client.post(
            "/api/auth/supabase/google/", {"access_token": "verified-google-token"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        user = User.objects.get(email="student@example.test")
        self.assertEqual(user.profile.role, "user")
        self.assertEqual(user.profile.supabase_user_id, "11111111-1111-1111-1111-111111111111")

    @patch("core.views.urlopen")
    def test_existing_email_is_linked_without_duplicate_user(self, mocked_urlopen):
        existing = User.objects.create_user("existing", email="student@example.test", password="pass12345")
        self.mock_supabase_user(mocked_urlopen, self.supabase_user())
        response = self.client.post(
            "/api/auth/supabase/google/", {"access_token": "verified-google-token"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(email="student@example.test").count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.profile.supabase_user_id, "11111111-1111-1111-1111-111111111111")

    @patch("core.views.urlopen")
    def test_existing_admin_keeps_server_controlled_role(self, mocked_urlopen):
        admin = User.objects.create_user("existing-admin", email="student@example.test", password="pass12345")
        admin.profile.role = "admin"
        admin.profile.save(update_fields=["role"])
        self.mock_supabase_user(mocked_urlopen, self.supabase_user())

        response = self.client.post(
            "/api/auth/supabase/google/", {"access_token": "verified-google-token"}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        admin.refresh_from_db()
        self.assertEqual(admin.profile.role, "admin")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        self.assertEqual(self.client.get("/api/analytics/students/").status_code, 200)

    @patch("core.views.urlopen")
    def test_google_user_without_verified_email_is_rejected(self, mocked_urlopen):
        self.mock_supabase_user(mocked_urlopen, self.supabase_user(email="", email_confirmed_at=None))

        response = self.client.post(
            "/api/auth/supabase/google/", {"access_token": "verified-google-token"}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.objects.count(), 0)

    @patch("core.views.urlopen")
    def test_removed_student_cannot_bypass_removal_with_google_login(self, mocked_urlopen):
        removed = User.objects.create_user("removed", email="student@example.test", password="pass12345")
        removed.profile.is_removed = True
        removed.profile.save(update_fields=["is_removed"])
        removed.is_active = False
        removed.save(update_fields=["is_active"])
        self.mock_supabase_user(mocked_urlopen, self.supabase_user())
        response = self.client.post(
            "/api/auth/supabase/google/", {"access_token": "verified-google-token"}, format="json"
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data.get("code"), "account_removed")
        self.assertEqual(User.objects.filter(email="student@example.test").count(), 1)

    @patch("core.views.urlopen")
    def test_removed_linked_identity_cannot_bypass_with_changed_email(self, mocked_urlopen):
        removed = User.objects.create_user("removed", email="old@example.test", password="pass12345")
        removed.profile.supabase_user_id = "11111111-1111-1111-1111-111111111111"
        removed.profile.is_removed = True
        removed.profile.save(update_fields=["supabase_user_id", "is_removed"])
        removed.is_active = False
        removed.save(update_fields=["is_active"])
        self.mock_supabase_user(mocked_urlopen, self.supabase_user(email="new@example.test"))

        response = self.client.post(
            "/api/auth/supabase/google/", {"access_token": "verified-google-token"}, format="json"
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data.get("code"), "account_removed")
        self.assertFalse(User.objects.filter(email="new@example.test").exists())

    @patch("core.views.urlopen")
    def test_non_google_identity_is_rejected(self, mocked_urlopen):
        self.mock_supabase_user(mocked_urlopen, self.supabase_user(app_metadata={"provider": "github"}))
        response = self.client.post(
            "/api/auth/supabase/google/", {"access_token": "verified-token"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.objects.count(), 0)

    @patch("core.views.urlopen", side_effect=OSError)
    def test_unverified_supabase_token_is_rejected(self, _mocked_urlopen):
        response = self.client.post(
            "/api/auth/supabase/google/", {"access_token": "invalid-token"}, format="json"
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(User.objects.count(), 0)
