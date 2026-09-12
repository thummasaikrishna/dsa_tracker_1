from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.scoring import calculate_potential_points


class ScoringTests(TestCase):
    def setUp(self):
        self.published = timezone.now()
        self.deadline = self.published + timedelta(hours=72)

    def test_within_first_24_hours(self):
        submitted = self.published + timedelta(hours=10)
        self.assertEqual(calculate_potential_points(self.published, submitted, self.deadline), 10)

    def test_between_24_and_48_hours(self):
        submitted = self.published + timedelta(hours=34)
        self.assertEqual(calculate_potential_points(self.published, submitted, self.deadline), 7)

    def test_between_48_and_deadline(self):
        submitted = self.published + timedelta(hours=58)
        self.assertEqual(calculate_potential_points(self.published, submitted, self.deadline), 5)

    def test_after_deadline_is_zero(self):
        submitted = self.deadline + timedelta(hours=1)
        self.assertEqual(calculate_potential_points(self.published, submitted, self.deadline), 0)

    def test_missing_timestamps_are_zero(self):
        self.assertEqual(calculate_potential_points(None, timezone.now(), self.deadline), 0)
