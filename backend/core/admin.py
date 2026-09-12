from django.contrib import admin

from .models import AIQuestionGenerationCache, Assignment, CodeSubmission, Notification, Profile, Question, TestCase


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "created_at")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("title", "difficulty", "reference_solution_status", "created_by", "is_active", "created_at", "deadline")
    list_filter = ("difficulty", "is_active", "reference_solution_status")
    search_fields = ("title", "description", "prerequisites")
    actions = ("validate_reference_solutions",)

    @admin.action(description="Validate selected reference solutions in sandbox")
    def validate_reference_solutions(self, request, queryset):
        from .oracle import validate_reference_solution

        verified = sum(validate_reference_solution(question).ok for question in queryset)
        self.message_user(request, f"Validated {verified} of {queryset.count()} reference solution(s).")


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "user", "question", "status", "proof_status",
        "potential_points", "points_awarded", "assigned_at",
    )
    list_filter = ("status", "proof_status")
    search_fields = ("user__username", "question__title", "linkedin_post_url")


@admin.register(TestCase)
class TestCaseAdmin(admin.ModelAdmin):
    list_display = ("question", "order", "is_hidden", "validation_type")
    list_filter = ("is_hidden", "validation_type")


@admin.register(CodeSubmission)
class CodeSubmissionAdmin(admin.ModelAdmin):
    list_display = ("user", "question", "language", "status", "tests_passed", "points_awarded", "submitted_at")
    list_filter = ("status", "language")
    search_fields = ("user__username", "question__title")
    readonly_fields = ("source_code", "public_results")


@admin.register(AIQuestionGenerationCache)
class AIQuestionGenerationCacheAdmin(admin.ModelAdmin):
    list_display = ("input_hash", "problem_title", "updated_at")
    search_fields = ("problem_title", "input_hash")
    readonly_fields = ("input_hash", "problem_title", "problem_statement", "generated_response", "created_at", "updated_at")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "event", "title", "is_read", "is_dismissed", "created_at")
    list_filter = ("event", "is_read", "is_dismissed")
    search_fields = ("user__username", "title")
