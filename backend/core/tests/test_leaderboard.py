from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Assignment, Profile, Question


class LeaderboardApiTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("adminlb", password="pass12345")
        self.admin.profile.role = "admin"
        self.admin.profile.save()

        self.rahul = User.objects.create_user("rahul", first_name="Rahul", password="pass12345")
        self.krishna = User.objects.create_user("krishna", first_name="Krishna", password="pass12345")
        self.removed = User.objects.create_user("gone", password="pass12345")
        self.removed.profile.is_removed = True
        self.removed.profile.save()

        now = timezone.now()
        self.q1 = Question.objects.create(
            title="Two Sum",
            difficulty="easy",
            created_by=self.admin,
            deadline=now + timedelta(days=3),
        )
        self.q2 = Question.objects.create(
            title="Binary Search",
            difficulty="easy",
            created_by=self.admin,
            deadline=now + timedelta(days=3),
        )

        a1 = Assignment.objects.create(
            user=self.rahul,
            question=self.q1,
            status="completed",
            proof_status="validated",
            potential_points=10,
            points_awarded=10,
            submitted_at=now,
            validated_at=now,
        )
        a2 = Assignment.objects.create(
            user=self.krishna,
            question=self.q1,
            status="completed",
            proof_status="validated",
            potential_points=10,
            points_awarded=10,
            submitted_at=now,
            validated_at=now + timedelta(minutes=5),
        )
        Assignment.objects.create(
            user=self.rahul,
            question=self.q2,
            status="completed",
            proof_status="validated",
            potential_points=7,
            points_awarded=7,
            submitted_at=now,
            validated_at=now + timedelta(minutes=1),
        )
        Assignment.objects.create(
            user=self.removed,
            question=self.q1,
            status="completed",
            proof_status="validated",
            potential_points=10,
            points_awarded=10,
            submitted_at=now,
            validated_at=now,
        )
        self.a1 = a1
        self.a2 = a2

        self.client = APIClient()
        self.client.force_authenticate(self.rahul)

    def test_rank_order_and_excludes_removed(self):
        res = self.client.get("/api/analytics/leaderboard/")
        self.assertEqual(res.status_code, 200)
        items = res.data["items"]
        usernames = [row["username"] for row in items]
        self.assertNotIn("gone", usernames)
        self.assertEqual(usernames[0], "rahul")
        self.assertEqual(items[0]["total_points"], 17)
        self.assertEqual(items[0]["solved_count"], 2)
        self.assertEqual(usernames[1], "krishna")
        self.assertTrue(res.data["me"]["is_me"])

    def test_validate_is_idempotent(self):
        q = Question.objects.create(
            title="Valid Parens",
            difficulty="easy",
            created_by=self.admin,
            deadline=timezone.now() + timedelta(days=3),
        )
        assignment = Assignment.objects.create(
            user=self.krishna,
            question=q,
            status="in_progress",
            proof_status="pending",
            linkedin_post_url="https://www.linkedin.com/posts/x",
            submitted_at=timezone.now(),
            potential_points=10,
            points_awarded=0,
        )
        admin_client = APIClient()
        admin_client.force_authenticate(self.admin)
        first = admin_client.post(f"/api/assignments/{assignment.id}/validate_proof/")
        second = admin_client.post(f"/api/assignments/{assignment.id}/validate_proof/")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        assignment.refresh_from_db()
        self.assertEqual(assignment.points_awarded, 10)
        self.assertEqual(assignment.proof_status, "validated")
