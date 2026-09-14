"""Regression tests for Security Phase 1 authentication controls."""

from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken


class SecurityAuthTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            "security-user", email="security@example.test", password="StrongPass123!"
        )

    def login(self, username="security-user", password="StrongPass123!"):
        return self.client.post("/api/auth/login/", {"username": username, "password": password}, format="json")

    def test_register_success_and_normalizes_email(self):
        response = self.client.post(
            "/api/auth/register/",
            {"username": "new-user", "email": "  New.User@Example.Test ", "password": "StrongPass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("access", response.data)
        self.assertEqual(User.objects.get(username="new-user").profile.normalized_email, "new.user@example.test")

    def test_register_rejects_invalid_password_duplicate_username_and_normalized_email(self):
        bad_password = self.client.post(
            "/api/auth/register/",
            {"username": "bad-password", "email": "bad@example.test", "password": "12345678"},
            format="json",
        )
        self.assertEqual(bad_password.status_code, 400)
        duplicate_username = self.client.post(
            "/api/auth/register/",
            {"username": "security-user", "email": "another@example.test", "password": "StrongPass123!"},
            format="json",
        )
        self.assertEqual(duplicate_username.status_code, 400)
        duplicate_email = self.client.post(
            "/api/auth/register/",
            {"username": "another-user", "email": " SECURITY@EXAMPLE.TEST ", "password": "StrongPass123!"},
            format="json",
        )
        self.assertEqual(duplicate_email.status_code, 400)
        self.assertIn("email", duplicate_email.data["error"]["details"])

    def test_login_username_and_email_are_case_insensitive_and_bad_password_fails(self):
        self.assertEqual(self.login("SECURITY-USER").status_code, 200)
        self.assertEqual(self.login("SECURITY@EXAMPLE.TEST").status_code, 200)
        self.assertEqual(self.login(password="wrong-password").status_code, 401)

    def test_inactive_and_removed_users_cannot_log_in(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertEqual(self.login().status_code, 401)
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])
        self.user.profile.is_removed = True
        self.user.profile.save(update_fields=["is_removed"])
        self.assertEqual(self.login().status_code, 401)

    def test_access_token_valid_invalid_and_expired(self):
        tokens = self.login().data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        expired = AccessToken.for_user(self.user)
        expired.set_exp(lifetime=timedelta(seconds=-1))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {expired}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_refresh_rotates_and_rejects_old_and_expired_tokens(self):
        original = self.login().data["refresh"]
        refreshed = self.client.post("/api/auth/refresh/", {"refresh": original}, format="json")
        self.assertEqual(refreshed.status_code, 200)
        self.assertIn("refresh", refreshed.data)
        self.assertNotEqual(original, refreshed.data["refresh"])
        self.assertEqual(
            self.client.post("/api/auth/refresh/", {"refresh": original}, format="json").status_code,
            401,
        )
        expired = RefreshToken.for_user(self.user)
        expired.set_exp(lifetime=timedelta(seconds=-1))
        self.assertEqual(
            self.client.post("/api/auth/refresh/", {"refresh": str(expired)}, format="json").status_code,
            401,
        )

    def test_logout_blacklists_refresh_and_is_idempotent(self):
        tokens = self.login().data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        self.assertEqual(self.client.post("/api/auth/logout/", {"refresh": tokens["refresh"]}, format="json").status_code, 200)
        self.assertEqual(
            self.client.post("/api/auth/refresh/", {"refresh": tokens["refresh"]}, format="json").status_code,
            401,
        )
        self.assertEqual(self.client.post("/api/auth/logout/", {"refresh": tokens["refresh"]}, format="json").status_code, 200)

    def test_password_change_revokes_existing_access_and_refresh_tokens(self):
        tokens = self.login().data
        self.user.set_password("NewStrongPass123!")
        self.user.save(update_fields=["password"])
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        self.client.credentials()
        self.assertEqual(
            self.client.post("/api/auth/refresh/", {"refresh": tokens["refresh"]}, format="json").status_code,
            401,
        )
        self.assertEqual(self.login(password="NewStrongPass123!").status_code, 200)

    def test_rbac_and_cross_user_data_remain_protected(self):
        admin = User.objects.create_user("security-admin", password="StrongPass123!")
        admin.profile.role = "admin"
        admin.profile.save(update_fields=["role"])
        other = User.objects.create_user("security-other", password="StrongPass123!")
        self.assertEqual(self.client.get("/api/analytics/students/").status_code, 401)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/analytics/students/").status_code, 403)
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.get("/api/analytics/students/").status_code, 200)
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(f"/api/analytics/student/{self.user.id}/").status_code, 403)


class AuthenticationThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        User.objects.create_user("throttle-user", email="throttle@example.test", password="StrongPass123!")

    def _rates(self, **rates):
        return {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], **rates}

    def test_login_register_refresh_and_google_are_throttled(self):
        rates = self._rates(auth_login="1/min", auth_register="1/min", auth_refresh="1/min", auth_google="1/min")
        with override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": rates}), patch.object(ScopedRateThrottle, "THROTTLE_RATES", rates):
            self.assertEqual(self.client.post("/api/auth/login/", {"username": "throttle-user", "password": "bad"}, format="json").status_code, 401)
            throttled = self.client.post("/api/auth/login/", {"username": "throttle-user", "password": "bad"}, format="json")
            self.assertEqual(throttled.status_code, 429)
            self.assertEqual(throttled.data["error"]["code"], "throttled")

            self.assertEqual(self.client.post("/api/auth/register/", {"username": "throttle-register", "email": "register@example.test", "password": "StrongPass123!"}, format="json").status_code, 201)
            self.assertEqual(self.client.post("/api/auth/register/", {"username": "throttle-register-two", "email": "register2@example.test", "password": "StrongPass123!"}, format="json").status_code, 429)

            refresh = str(RefreshToken.for_user(User.objects.get(username="throttle-user")))
            self.assertEqual(self.client.post("/api/auth/refresh/", {"refresh": refresh}, format="json").status_code, 200)
            self.assertEqual(self.client.post("/api/auth/refresh/", {"refresh": refresh}, format="json").status_code, 429)

            self.assertEqual(self.client.post("/api/auth/supabase/google/", {"access_token": "invalid"}, format="json").status_code, 401)
            self.assertEqual(self.client.post("/api/auth/supabase/google/", {"access_token": "invalid"}, format="json").status_code, 429)


class CorsSecurityTests(TestCase):
    def test_explicit_allowed_origin_is_allowed_and_untrusted_origin_is_not(self):
        with override_settings(CORS_ALLOWED_ORIGINS=["https://frontend.example.test"], CORS_ALLOW_ALL_ORIGINS=False):
            allowed = self.client.options("/api/auth/login/", HTTP_ORIGIN="https://frontend.example.test", HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST")
            self.assertEqual(allowed["Access-Control-Allow-Origin"], "https://frontend.example.test")
            denied = self.client.options("/api/auth/login/", HTTP_ORIGIN="https://untrusted.example.test", HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST")
            self.assertNotIn("Access-Control-Allow-Origin", denied)

    def test_cors_configuration_rejects_wildcards(self):
        from django.core.exceptions import ImproperlyConfigured
        from dsatracker.settings import _is_valid_cors_origin, _validate_cors_origins, _validate_production_settings

        self.assertFalse(_is_valid_cors_origin("*"))
        self.assertFalse(_is_valid_cors_origin("https://*.example.test"))
        self.assertTrue(_is_valid_cors_origin("https://frontend.example.test"))
        with self.assertRaises(ImproperlyConfigured):
            _validate_cors_origins([], production=True)
        with self.assertRaises(ImproperlyConfigured):
            _validate_cors_origins(["http://frontend.example.test"], production=True)
        with self.assertRaises(ImproperlyConfigured):
            _validate_production_settings(True, "not-used")
        with self.assertRaises(ImproperlyConfigured):
            _validate_production_settings(False, "")
