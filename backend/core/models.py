"""
Core data model for DSA Tracker.

Three entities:
  1. Profile     -> extends Django's built-in User with a `role` field
  2. Question    -> a DSA problem created by an Admin (no external problem link)
  3. Assignment  -> join table Users ↔ Questions with status + LinkedIn proof

Students solve locally, post on LinkedIn, then submit the post URL as
proof of work. Admin validates the LinkedIn post from the admin portal.
"""

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models


def normalize_email(email):
    """Return the canonical email form used for identity matching."""
    return (email or "").strip().lower()


class Profile(models.Model):
    ROLE_CHOICES = (
        ("admin", "Admin"),
        ("user", "User"),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="user")
    is_removed = models.BooleanField(default=False, db_index=True)
    removed_at = models.DateTimeField(null=True, blank=True)
    supabase_user_id = models.CharField(max_length=36, null=True, blank=True, unique=True)
    # User.email is not unique in Django's stock User model.  Keep the
    # canonical value here so the database can enforce application identity.
    normalized_email = models.CharField(max_length=254, null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["role"]),
            models.Index(fields=["is_removed", "role"], name="core_profil_is_remo_role_idx"),
        ]

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    @property
    def is_admin(self):
        return self.role == "admin"

    def clean(self):
        if self.role == "admin":
            clash = Profile.objects.filter(role="admin").exclude(pk=self.pk)
            if clash.exists():
                raise ValidationError("Only one admin account is allowed.")

    def save(self, *args, **kwargs):
        if self.user_id:
            self.normalized_email = normalize_email(self.user.email) or None
        self.full_clean()
        return super().save(*args, **kwargs)


class Question(models.Model):
    DIFFICULTY_CHOICES = (
        ("easy", "Easy"),
        ("medium", "Medium"),
        ("hard", "Hard"),
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    examples = models.TextField(blank=True, help_text="Sample inputs/outputs for the problem")
    prerequisites = models.TextField(blank=True, help_text="Topics/skills needed before attempting")
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, db_index=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="questions_created"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    deadline = models.DateTimeField(db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    REFERENCE_SOLUTION_DRAFT = "DRAFT"
    REFERENCE_SOLUTION_VERIFIED = "VERIFIED"
    REFERENCE_SOLUTION_FAILED = "FAILED"
    REFERENCE_SOLUTION_STATUS_CHOICES = (
        (REFERENCE_SOLUTION_DRAFT, "Draft"),
        (REFERENCE_SOLUTION_VERIFIED, "Verified"),
        (REFERENCE_SOLUTION_FAILED, "Failed"),
    )
    # This is privileged authoring data.  It is never included in student API
    # representations and is executed only by core.oracle through execute_once.
    reference_solution = models.TextField(blank=True)
    reference_solution_language = models.CharField(max_length=16, default="python")
    reference_solution_status = models.CharField(
        max_length=10,
        choices=REFERENCE_SOLUTION_STATUS_CHOICES,
        default=REFERENCE_SOLUTION_DRAFT,
        db_index=True,
    )
    reference_solution_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["difficulty", "is_active"]),
        ]

    def __str__(self):
        return f"{self.title} [{self.difficulty}]"

    def save(self, *args, **kwargs):
        # Changing executable reference code (or its interpreter) always
        # revokes trust.  Only the Oracle validation workflow can set VERIFIED.
        status_reset = False
        if self.pk:
            previous = Question.objects.filter(pk=self.pk).values(
                "reference_solution", "reference_solution_language", "reference_solution_status"
            ).first()
            if previous and (
                previous["reference_solution"] != self.reference_solution
                or previous["reference_solution_language"] != self.reference_solution_language
            ):
                self.reference_solution_status = self.REFERENCE_SOLUTION_DRAFT
                self.reference_solution_error = ""
                status_reset = True
            elif (
                previous
                and previous["reference_solution"] == self.reference_solution
                and self.reference_solution_status == self.REFERENCE_SOLUTION_VERIFIED
                and not getattr(self, "_reference_validation_in_progress", False)
            ):
                # Do not allow an API/admin edit to promote executable code.
                self.reference_solution_status = previous.get("reference_solution_status", self.REFERENCE_SOLUTION_DRAFT)
        elif (
            self.reference_solution_status == self.REFERENCE_SOLUTION_VERIFIED
            and not getattr(self, "_reference_validation_in_progress", False)
        ):
            self.reference_solution_status = self.REFERENCE_SOLUTION_DRAFT
            status_reset = True
        if status_reset and kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {
                "reference_solution_status", "reference_solution_error"
            }
        return super().save(*args, **kwargs)


class TestCase(models.Model):
    """stdin/expected-output pair for online judging. Hidden cases never leave the API for students."""

    VALIDATION_EXACT = "EXACT_MATCH"
    VALIDATION_CUSTOM = "CUSTOM_VALIDATOR"
    VALIDATION_CHOICES = (
        (VALIDATION_EXACT, "Exact match"),
        (VALIDATION_CUSTOM, "Custom validator"),
    )
    VERIFICATION_GENERATED = "GENERATED"
    VERIFICATION_VERIFIED = "VERIFIED"
    VERIFICATION_REQUIRES_REVIEW = "REQUIRES_REVIEW"
    VERIFICATION_INVALID = "INVALID"
    VERIFICATION_CHOICES = (
        (VERIFICATION_GENERATED, "Generated"),
        (VERIFICATION_VERIFIED, "Verified"),
        (VERIFICATION_REQUIRES_REVIEW, "Requires review"),
        (VERIFICATION_INVALID, "Invalid"),
    )

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="test_cases")
    input_data = models.TextField(blank=True)
    expected_output = models.TextField(blank=True)
    validation_type = models.CharField(
        max_length=32,
        choices=VALIDATION_CHOICES,
        default=VALIDATION_EXACT,
        db_index=True,
    )
    validator_type = models.CharField(max_length=64, blank=True)
    is_hidden = models.BooleanField(default=False, db_index=True)
    verification_status = models.CharField(
        max_length=20, choices=VERIFICATION_CHOICES, default=VERIFICATION_GENERATED, db_index=True
    )
    verification_reason = models.CharField(max_length=255, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]
        indexes = [
            models.Index(
                fields=["question", "is_hidden", "order"],
                name="core_testca_questio_hidden_idx",
            )
        ]

    def __str__(self):
        kind = "hidden" if self.is_hidden else "public"
        return f"{self.question_id} #{self.order} ({kind})"


class Assignment(models.Model):
    STATUS_CHOICES = (
        ("assigned", "Assigned"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
    )
    PROOF_STATUS_CHOICES = (
        ("none", "Not Submitted"),
        ("pending", "Pending Review"),
        ("validated", "Validated"),
        ("rejected", "Rejected"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="assignments")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="assignments")
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="assigned")
    # LinkedIn share URLs often exceed the default 200-char URLField limit.
    linkedin_post_url = models.URLField(blank=True, max_length=500)
    proof_status = models.CharField(
        max_length=15, choices=PROOF_STATUS_CHOICES, default="none", db_index=True
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    potential_points = models.PositiveSmallIntegerField(default=0)
    points_awarded = models.PositiveSmallIntegerField(default=0)
    validated_at = models.DateTimeField(null=True, blank=True)
    validated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="validated_assignments",
    )
    assigned_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "question"], name="unique_user_question_assignment")
        ]
        ordering = ["-assigned_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["assigned_at"]),
            models.Index(fields=["proof_status"]),
        ]

    def __str__(self):
        return f"{self.user.username} -> {self.question.title} ({self.status}/{self.proof_status})"


class CodeSubmission(models.Model):
    LANGUAGE_CHOICES = (
        ("python", "Python"),
        ("java", "Java"),
        ("cpp", "C++"),
    )
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_ACCEPTED = "accepted"
    STATUS_WRONG_ANSWER = "wrong_answer"
    STATUS_COMPILATION_ERROR = "compilation_error"
    STATUS_RUNTIME_ERROR = "runtime_error"
    STATUS_TIME_LIMIT_EXCEEDED = "time_limit_exceeded"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_WRONG_ANSWER, "Wrong Answer"),
        (STATUS_COMPILATION_ERROR, "Compilation Error"),
        (STATUS_RUNTIME_ERROR, "Runtime Error"),
        (STATUS_TIME_LIMIT_EXCEEDED, "Time Limit Exceeded"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="code_submissions")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="code_submissions")
    language = models.CharField(max_length=16, choices=LANGUAGE_CHOICES, db_index=True)
    source_code = models.TextField()
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    tests_passed = models.PositiveIntegerField(default=0)
    total_tests = models.PositiveIntegerField(default=0)
    execution_time = models.FloatField(null=True, blank=True, help_text="Seconds")
    memory_used = models.FloatField(null=True, blank=True, help_text="KB if reported")
    compile_output = models.TextField(blank=True)
    public_results = models.JSONField(default=list, blank=True)
    potential_points = models.PositiveSmallIntegerField(default=0)
    points_awarded = models.PositiveSmallIntegerField(default=0)
    submitted_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(
                fields=["user", "question", "-submitted_at"],
                name="core_codesu_user_q_sub_idx",
            ),
            models.Index(fields=["status", "-submitted_at"], name="core_codesu_status_sub_idx"),
            models.Index(fields=["language"], name="core_codesu_language_idx"),
        ]

    def __str__(self):
        return f"{self.user.username} {self.question_id} {self.language} {self.status}"


class Notification(models.Model):
    """
    In-app notifications for students (new questions, validated proofs).
    Persisted so refresh does not recreate or duplicate events.
    """

    EVENT_NEW_QUESTION = "new_question"
    EVENT_PROOF_VALIDATED = "proof_validated"
    EVENT_PROOF_REJECTED = "proof_rejected"
    EVENT_PROOF_SUBMITTED = "proof_submitted"
    EVENT_QUESTION_UPDATED = "question_updated"
    EVENT_STUDENT_INACTIVE = "student_inactive"
    EVENT_CODE_SUBMITTED = "code_submitted"
    EVENT_CODE_RESULT = "code_result"
    EVENT_CHOICES = (
        (EVENT_NEW_QUESTION, "New Question"),
        (EVENT_PROOF_VALIDATED, "Proof Validated"),
        (EVENT_PROOF_REJECTED, "Proof Rejected"),
        (EVENT_PROOF_SUBMITTED, "Proof Submitted"),
        (EVENT_QUESTION_UPDATED, "Question Updated"),
        (EVENT_STUDENT_INACTIVE, "Student Inactivity"),
        (EVENT_CODE_SUBMITTED, "Code Submitted"),
        (EVENT_CODE_RESULT, "Code Result"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    event = models.CharField(max_length=32, choices=EVENT_CHOICES, db_index=True)
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications"
    )
    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications"
    )
    code_submission = models.ForeignKey(
        "CodeSubmission",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    about_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications_about",
    )
    is_read = models.BooleanField(default=False, db_index=True)
    is_dismissed = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "is_read", "-created_at"],
                name="core_notifi_user_id_3a4e8a_idx",
            ),
            models.Index(
                fields=["user", "is_dismissed", "-created_at"],
                name="core_notif_user_dismiss_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "event", "question"],
                condition=models.Q(event="new_question", question__isnull=False),
                name="uniq_user_new_question_notification",
            ),
            models.UniqueConstraint(
                fields=["user", "event", "assignment"],
                condition=models.Q(("event", "proof_validated"), ("assignment__isnull", False)),
                name="uniq_user_validated_assignment_notification",
            ),
            models.UniqueConstraint(
                fields=["user", "event", "assignment"],
                condition=models.Q(event="proof_rejected", assignment__isnull=False),
                name="uniq_user_rejected_assignment_notification",
            ),
            models.UniqueConstraint(
                fields=["user", "event", "assignment"],
                condition=models.Q(event="proof_submitted", assignment__isnull=False),
                name="uniq_admin_submitted_proof_notification",
            ),
            models.UniqueConstraint(
                fields=["user", "event", "question"],
                condition=models.Q(event="question_updated", question__isnull=False),
                name="uniq_user_question_updated_notification",
            ),
            models.UniqueConstraint(
                fields=["user", "event", "about_user"],
                condition=models.Q(("event", "student_inactive"), ("about_user__isnull", False)),
                name="uniq_admin_student_inactive_notification",
            ),
            models.UniqueConstraint(
                fields=["user", "event", "code_submission"],
                condition=models.Q(event="code_submitted", code_submission__isnull=False),
                name="uniq_admin_code_submitted_notification",
            ),
            models.UniqueConstraint(
                fields=["user", "event", "code_submission"],
                condition=models.Q(event="code_result", code_submission__isnull=False),
                name="uniq_student_code_result_notification",
            ),
        ]

    def __str__(self):
        return f"{self.user.username}: {self.event} ({self.title})"


class AIQuestionGenerationCache(models.Model):
    """Validated DSA Problem Analysis Agent output keyed by a deterministic input hash."""

    input_hash = models.CharField(max_length=64, unique=True, db_index=True)
    problem_title = models.CharField(max_length=255)
    problem_statement = models.TextField()
    generated_response = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"ai-cache {self.input_hash[:12]}"
