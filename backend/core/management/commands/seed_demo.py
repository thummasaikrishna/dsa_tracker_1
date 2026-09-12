"""
Seeds the database with the sole admin account, the real student account,
sample questions, and optional assignments for that student.

Removes known leftover demo students (rahul, priya, arjun, old admin).
Does not delete other registered student accounts.

Usage:  python manage.py seed_demo
"""

import random
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Assignment, Profile, Question

ADMIN_USERNAME = "saikrishnathumma"
ADMIN_EMAIL = "thummasaikrishna16@gmail.com"
ADMIN_PASSWORD = "Saikkrrcb123#"

STUDENT_USERNAME = "krishnathumma"
STUDENT_EMAIL = "krishnathumma@dsatracker.dev"
STUDENT_PASSWORD = "Student@123"

# Only these legacy demo accounts are removed on seed.
# Do NOT wipe all other users — that would delete legitimate student registrations.
DEMO_USERNAMES = ("rahul", "priya", "arjun", "admin")

QUESTIONS = [
    {
        "title": "Two Sum",
        "difficulty": "easy",
        "description": "Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.",
        "examples": "Input: nums = [2,7,11,15], target = 9\nOutput: [0,1]\nExplanation: Because nums[0] + nums[1] == 9.",
        "prerequisites": "Arrays, Hash Map",
    },
    {
        "title": "Binary Search",
        "difficulty": "easy",
        "description": "Given a sorted array of integers and a target, return the index if the target is found. Otherwise return -1.",
        "examples": "Input: nums = [-1,0,3,5,9,12], target = 9\nOutput: 4",
        "prerequisites": "Arrays, Divide and Conquer",
    },
    {
        "title": "Valid Parentheses",
        "difficulty": "easy",
        "description": "Given a string containing just the characters '(', ')', '{', '}', '[' and ']', determine if the input string is valid.",
        "examples": "Input: s = \"()[]{}\"\nOutput: true",
        "prerequisites": "Stack, Strings",
    },
    {
        "title": "Merge Intervals",
        "difficulty": "medium",
        "description": "Given an array of intervals where intervals[i] = [starti, endi], merge all overlapping intervals.",
        "examples": "Input: intervals = [[1,3],[2,6],[8,10],[15,18]]\nOutput: [[1,6],[8,10],[15,18]]",
        "prerequisites": "Sorting, Arrays",
    },
    {
        "title": "Longest Substring Without Repeating Characters",
        "difficulty": "medium",
        "description": "Given a string s, find the length of the longest substring without repeating characters.",
        "examples": "Input: s = \"abcabcbb\"\nOutput: 3\nExplanation: The answer is \"abc\".",
        "prerequisites": "Sliding Window, Hash Set",
    },
    {
        "title": "Number of Islands",
        "difficulty": "medium",
        "description": "Given an m x n 2D binary grid which represents a map of '1's (land) and '0's (water), return the number of islands.",
        "examples": "Input: grid = [[\"1\",\"1\",\"0\"],[\"1\",\"1\",\"0\"],[\"0\",\"0\",\"1\"]]\nOutput: 2",
        "prerequisites": "DFS / BFS, Graphs / Grid",
    },
    {
        "title": "Word Ladder",
        "difficulty": "hard",
        "description": "Find the length of shortest transformation sequence from beginWord to endWord, changing one letter at a time.",
        "examples": "Input: beginWord = \"hit\", endWord = \"cog\", wordList = [\"hot\",\"dot\",\"dog\",\"lot\",\"log\",\"cog\"]\nOutput: 5",
        "prerequisites": "BFS, Graphs",
    },
    {
        "title": "Median of Two Sorted Arrays",
        "difficulty": "hard",
        "description": "Given two sorted arrays nums1 and nums2 of size m and n, return the median of the two sorted arrays.",
        "examples": "Input: nums1 = [1,3], nums2 = [2]\nOutput: 2.00000",
        "prerequisites": "Binary Search, Divide and Conquer",
    },
    {
        "title": "N-Queens",
        "difficulty": "hard",
        "description": "Place n queens on an n x n chessboard such that no two queens attack each other. Return all distinct solutions.",
        "examples": "Input: n = 4\nOutput: [[\".Q..\",\"...Q\",\"Q...\",\"..Q.\"],[\"..Q.\",\"Q...\",\"...Q\",\".Q..\"]]",
        "prerequisites": "Backtracking, Recursion",
    },
]


class Command(BaseCommand):
    help = (
        "Seed data: sole admin + student krishnathumma, sample questions. "
        "Purges other demo student accounts."
    )

    def handle(self, *args, **options):
        # Enforce single admin: demote any other admin profiles first
        Profile.objects.filter(role="admin").update(role="user")

        admin_user, _ = User.objects.get_or_create(
            username=ADMIN_USERNAME,
            defaults={"email": ADMIN_EMAIL},
        )
        admin_user.email = ADMIN_EMAIL
        admin_user.set_password(ADMIN_PASSWORD)
        admin_user.save()

        profile = admin_user.profile
        profile.role = "admin"
        profile.save()
        self.stdout.write(
            self.style.SUCCESS(f"Admin ready: {ADMIN_USERNAME} / {ADMIN_PASSWORD}")
        )

        # Ensure the kept student exists
        student, created = User.objects.get_or_create(
            username=STUDENT_USERNAME,
            defaults={"email": STUDENT_EMAIL},
        )
        if created or not student.has_usable_password():
            student.set_password(STUDENT_PASSWORD)
        if not student.email:
            student.email = STUDENT_EMAIL
        student.save()
        student.profile.role = "user"
        student.profile.save()
        self.stdout.write(
            self.style.SUCCESS(f"Student ready: {STUDENT_USERNAME} / {STUDENT_PASSWORD}")
        )

        # Purge known demo accounts only — preserve any newly registered students
        keep_usernames = {ADMIN_USERNAME, STUDENT_USERNAME}
        doomed = User.objects.filter(username__in=DEMO_USERNAMES).exclude(
            username__in=keep_usernames
        )
        doomed_names = list(doomed.values_list("username", flat=True))
        deleted_count, _ = doomed.delete()
        if doomed_names:
            self.stdout.write(
                self.style.WARNING(
                    f"Purged {len(doomed_names)} demo user(s) "
                    f"({deleted_count} DB rows): {', '.join(doomed_names)}"
                )
            )
        else:
            self.stdout.write("No leftover demo students to purge.")

        questions = []
        for item in QUESTIONS:
            q, created_q = Question.objects.get_or_create(
                title=item["title"],
                defaults={
                    "difficulty": item["difficulty"],
                    "description": item["description"],
                    "examples": item["examples"],
                    "prerequisites": item["prerequisites"],
                    "created_by": admin_user,
                    "deadline": timezone.now() + timedelta(days=3),
                },
            )
            if not created_q:
                q.description = item["description"]
                q.examples = item["examples"]
                q.prerequisites = item["prerequisites"]
                q.difficulty = item["difficulty"]
                if not q.deadline:
                    q.deadline = (q.created_at or timezone.now()) + timedelta(days=3)
                q.save()
            questions.append(q)

        # Light sample activity for the kept student (idempotent get_or_create)
        if not Assignment.objects.filter(user=student).exists() and questions:
            picks = random.sample(questions, k=min(4, len(questions)))
            for q in picks:
                days_ago = random.randint(0, 20)
                status = random.choice(["assigned", "in_progress", "assigned"])
                assignment, _ = Assignment.objects.get_or_create(
                    user=student, question=q, defaults={"status": status}
                )
                assignment.status = status
                assignment.assigned_at = timezone.now() - timedelta(days=days_ago)
                assignment.proof_status = "none"
                assignment.linkedin_post_url = ""
                assignment.submitted_at = None
                assignment.validated_at = None
                assignment.validated_by = None
                assignment.save()
            self.stdout.write(
                self.style.SUCCESS(f"Seeded {len(picks)} assignments for {STUDENT_USERNAME}")
            )

        self.stdout.write(self.style.SUCCESS("Seed complete."))
