from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Assignment, Notification, Question
from core.notify import notify_admin_proof_submitted


class NotificationDismissTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("adminn", password="pass12345")
        self.admin.profile.role = "admin"
        self.admin.profile.save()
        self.student = User.objects.create_user("alice", password="pass12345")
        self.other = User.objects.create_user("bob", password="pass12345")
        now = timezone.now()
        self.question = Question.objects.create(
            title="Two Sum",
            difficulty="easy",
            created_by=self.admin,
            deadline=now + timedelta(days=2),
        )
        self.note = Notification.objects.create(
            user=self.student,
            event=Notification.EVENT_NEW_QUESTION,
            title="New Question Added",
            message="Two Sum has been added.",
            question=self.question,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.student)

    def test_list_and_unread(self):
        res = self.client.get("/api/notifications/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["unread_count"], 1)
        self.assertEqual(len(res.data["items"]), 1)

    def test_read_keeps_item_in_dropdown(self):
        res = self.client.post(f"/api/notifications/{self.note.id}/read/")
        self.assertEqual(res.status_code, 200)
        listed = self.client.get("/api/notifications/")
        self.assertEqual(listed.data["unread_count"], 0)
        self.assertEqual(len(listed.data["items"]), 1)

    def test_dismiss_hides_persistently(self):
        res = self.client.patch(f"/api/notifications/{self.note.id}/dismiss/")
        self.assertEqual(res.status_code, 200)
        listed = self.client.get("/api/notifications/")
        self.assertEqual(listed.data["unread_count"], 0)
        self.assertEqual(listed.data["items"], [])
        self.note.refresh_from_db()
        self.assertTrue(self.note.is_dismissed)
        self.assertTrue(self.note.is_read)

    def test_cannot_dismiss_another_users_notification(self):
        other_note = Notification.objects.create(
            user=self.other,
            event=Notification.EVENT_NEW_QUESTION,
            title="New Question Added",
            message="Nope",
            question=self.question,
        )
        res = self.client.patch(f"/api/notifications/{other_note.id}/dismiss/")
        self.assertEqual(res.status_code, 404)
        other_note.refresh_from_db()
        self.assertFalse(other_note.is_dismissed)

    def test_admin_cannot_dismiss_student_notification(self):
        self.client.force_authenticate(self.admin)
        res = self.client.patch(f"/api/notifications/{self.note.id}/dismiss/")
        self.assertEqual(res.status_code, 404)
        self.note.refresh_from_db()
        self.assertFalse(self.note.is_dismissed)

    def test_admin_can_dismiss_own_notification(self):
        admin_note = Notification.objects.create(
            user=self.admin,
            event=Notification.EVENT_CODE_SUBMITTED,
            title="NEW CODE SUBMISSION",
            message="Krishna submitted Binary Search.",
        )
        self.client.force_authenticate(self.admin)
        res = self.client.patch(f"/api/notifications/{admin_note.id}/dismiss/")
        self.assertEqual(res.status_code, 200)
        listed = self.client.get("/api/notifications/")
        ids = [row["id"] for row in listed.data["items"]]
        self.assertNotIn(admin_note.id, ids)
        admin_note.refresh_from_db()
        self.assertTrue(admin_note.is_dismissed)

    def test_admin_proof_notification_can_be_dismissed(self):
        assignment = Assignment.objects.create(
            user=self.student,
            question=self.question,
            proof_status="pending",
            linkedin_post_url="https://www.linkedin.com/posts/example",
        )
        notify_admin_proof_submitted(assignment)
        note = Notification.objects.get(
            user=self.admin,
            event=Notification.EVENT_PROOF_SUBMITTED,
            assignment=assignment,
        )

        self.client.force_authenticate(self.admin)
        self.client.patch(f"/api/notifications/{note.id}/dismiss/")
        listed = self.client.get("/api/notifications/")
        self.assertNotIn(note.id, [row["id"] for row in listed.data["items"]])
