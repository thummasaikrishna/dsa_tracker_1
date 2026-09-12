"""Create deterministic, non-production data for Playwright only."""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import Profile, Question, TestCase


class Command(BaseCommand):
    help = "Seed the isolated e2e.sqlite3 database used by Playwright."

    def handle(self, *args, **options):
        if not settings.E2E_TEST_MODE:
            raise CommandError("seed_e2e requires E2E_TEST_MODE=1; it never runs on the normal database.")

        # This database is selected exclusively by the explicit environment flag.
        User.objects.all().delete()
        admin = User.objects.create_user(
            username="e2e-admin", email="admin@example.test", password="E2EPassword123!", first_name="E2E Admin"
        )
        admin.profile.role = "admin"
        admin.profile.save(update_fields=["role"])
        student = User.objects.create_user(
            username="e2e-student", email="student@example.test", password="E2EPassword123!", first_name="E2E Student"
        )
        question = Question.objects.create(
            title="E2E Echo", description="Print the expected response.", examples="Input: hello\nOutput: expected",
            prerequisites="Basics", difficulty="easy", created_by=admin, deadline=timezone.now() + timedelta(days=3),
        )
        TestCase.objects.create(question=question, input_data="hello", expected_output="expected", order=0)
        TestCase.objects.create(question=question, input_data="secret-e2e-input", expected_output="expected", is_hidden=True, order=1)
        self.stdout.write(self.style.SUCCESS("Seeded isolated E2E users and question."))
