"""Time-based potential points from publication time, first submission, and deadline."""

from datetime import timedelta


def calculate_potential_points(published_at, submitted_at, deadline):
    """
    Score the first proof submission against the question's publish time.

    - Within the first 24 hours: 10
    - After 24 hours and within 48 hours: 7
    - After 48 hours but still before the deadline: 5
    - After the deadline (or missing timestamps): 0
    """
    if not published_at or not submitted_at or not deadline:
        return 0
    if submitted_at > deadline:
        return 0
    elapsed = submitted_at - published_at
    if elapsed < timedelta(hours=24):
        return 10
    if elapsed < timedelta(hours=48):
        return 7
    return 5
