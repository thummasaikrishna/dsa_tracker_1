"""Security Phase 2 regressions for RBAC and ownership boundaries."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Assignment, CodeSubmission, Notification, Question
from core.serializers import ProfileSerializer


class AssignmentWorkflowSecurityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user("phase2-admin", password="StrongPass123!")
        self.admin.profile.role = "admin"
        self.admin.profile.save(update_fields=["role"])
        self.student = User.objects.create_user("phase2-student", password="StrongPass123!")
        self.other = User.objects.create_user("phase2-other", password="StrongPass123!")
        self.question = Question.objects.create(
            title="Phase 2 question",
            difficulty="easy",
            deadline=timezone.now() + timedelta(days=2),
            created_by=self.admin,
        )
        self.other_question = Question.objects.create(
            title="Other phase 2 question",
            difficulty="medium",
            deadline=timezone.now() + timedelta(days=2),
            created_by=self.admin,
        )
        self.assignment = Assignment.objects.create(user=self.student, question=self.question)
        self.other_assignment = Assignment.objects.create(user=self.other, question=self.question)

    def test_generic_assignment_put_patch_cannot_bypass_workflow_or_change_question(self):
        self.client.force_authenticate(self.student)
        for method, body in (
            (self.client.patch, {"status": "completed"}),
            (self.client.put, {"status": "completed"}),
            (self.client.patch, {"question": self.other_question.id}),
        ):
            response = method(f"/api/assignments/{self.assignment.id}/", body, format="json")
            self.assertEqual(response.status_code, 405)

        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, "assigned")
        self.assertEqual(self.assignment.question_id, self.question.id)

    def test_create_accepts_only_question_and_server_assigns_owner_and_status(self):
        self.client.force_authenticate(self.student)
        rejected = self.client.post(
            "/api/assignments/",
            {"question": self.other_question.id, "status": "completed"},
            format="json",
        )
        self.assertEqual(rejected.status_code, 400)
        created = self.client.post("/api/assignments/", {"question": self.other_question.id}, format="json")
        self.assertEqual(created.status_code, 201)
        assignment = Assignment.objects.get(pk=created.data["id"])
        self.assertEqual(assignment.user_id, self.student.id)
        self.assertEqual(assignment.status, "assigned")

    def test_server_controlled_assignment_fields_cannot_be_written(self):
        self.client.force_authenticate(self.student)
        protected_bodies = [
            {"proof_status": "validated"},
            {"points_awarded": 999},
            {"potential_points": 999},
            {"validated_by": self.student.id},
            {"submitted_at": timezone.now().isoformat()},
            {"linkedin_post_url": "https://www.linkedin.com/posts/not-through-workflow"},
            {"user": self.other.id},
        ]
        for body in protected_bodies:
            response = self.client.patch(f"/api/assignments/{self.assignment.id}/", body, format="json")
            self.assertEqual(response.status_code, 405)

        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.user_id, self.student.id)
        self.assertEqual(self.assignment.proof_status, "none")
        self.assertEqual(self.assignment.points_awarded, 0)
        self.assertEqual(self.assignment.potential_points, 0)
        self.assertIsNone(self.assignment.validated_by)

    def test_cross_student_assignment_and_proof_access_is_denied(self):
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get(f"/api/assignments/{self.other_assignment.id}/").status_code, 404)
        self.assertEqual(self.client.patch(f"/api/assignments/{self.other_assignment.id}/status_update/", {"status": "in_progress"}, format="json").status_code, 404)
        self.assertEqual(self.client.post(f"/api/assignments/{self.other_assignment.id}/submit_proof/", {"linkedin_post_url": "https://www.linkedin.com/posts/proof"}, format="json").status_code, 404)

    def test_admin_can_still_review_pending_proof(self):
        self.assignment.linkedin_post_url = "https://www.linkedin.com/posts/proof"
        self.assignment.proof_status = "pending"
        self.assignment.potential_points = 7
        self.assignment.save(update_fields=["linkedin_post_url", "proof_status", "potential_points"])
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"/api/assignments/{self.assignment.id}/validate_proof/")
        self.assertEqual(response.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.proof_status, "validated")
        self.assertEqual(self.assignment.points_awarded, 7)


class OwnershipAndRoleSecurityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user("phase2-role-admin", password="StrongPass123!")
        self.admin.profile.role = "admin"
        self.admin.profile.save(update_fields=["role"])
        self.student = User.objects.create_user("phase2-role-student", password="StrongPass123!")
        self.other = User.objects.create_user("phase2-role-other", password="StrongPass123!")
        self.question = Question.objects.create(
            title="Ownership question", difficulty="easy", deadline=timezone.now() + timedelta(days=1), created_by=self.admin
        )
        self.submission = CodeSubmission.objects.create(
            user=self.other, question=self.question, language="python", source_code="print(1)"
        )
        self.notification = Notification.objects.create(
            user=self.other, event=Notification.EVENT_NEW_QUESTION, title="Other user's notification", question=self.question
        )

    def test_profile_role_is_serializer_read_only_and_registration_cannot_elevate_role(self):
        serializer = ProfileSerializer(instance=self.student.profile, data={"role": "admin"}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("role", serializer.validated_data)
        self.assertTrue(serializer.fields["role"].read_only)

        response = self.client.post(
            "/api/auth/register/",
            {"username": "phase2-new", "email": "phase2-new@example.test", "password": "StrongPass123!", "role": "admin"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(User.objects.get(username="phase2-new").profile.role, "user")

    def test_student_cannot_read_other_users_notifications_submissions_or_admin_data(self):
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get(f"/api/notifications/{self.notification.id}/read/").status_code, 405)
        self.assertEqual(self.client.post(f"/api/notifications/{self.notification.id}/read/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/code/submissions/{self.submission.id}/").status_code, 404)
        self.assertEqual(self.client.get("/api/analytics/overview/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/analytics/student/{self.other.id}/").status_code, 403)

    def test_admin_can_read_permitted_student_submission_data(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(f"/api/code/submissions/{self.submission.id}/").status_code, 200)
