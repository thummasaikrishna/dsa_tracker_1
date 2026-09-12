"""Online judge: run (public tests) and submit (all tests via remote sandbox)."""

import logging

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .executor import ExecutorUnavailable, evaluate_cases
from .models import Assignment, CodeSubmission, Question, TestCase
from .notify import notify_admin_code_submitted, notify_student_code_result
from .scoring import calculate_potential_points
from .serializers import (
    CodeSubmissionListSerializer,
    CodeSubmissionSerializer,
    RunCodeSerializer,
)

logger = logging.getLogger(__name__)
EXECUTOR_UNAVAILABLE_MESSAGE = "Code execution service is temporarily unavailable."


def _ensure_active_student(user):
    profile = getattr(user, "profile", None)
    if profile is None or profile.is_admin or profile.is_removed:
        return False
    return True


ASSIGNMENT_REQUIRED = {
    "success": False,
    "message": "Please assign this question before attempting to solve it.",
    "detail": "Please assign this question before attempting to solve it.",
}


def _get_active_assignment(user, question):
    """Return the student's existing assignment, or None. Never auto-creates."""
    return Assignment.objects.filter(user=user, question=question).first()


def _mark_in_progress(assignment):
    if assignment.status == "assigned":
        assignment.status = "in_progress"
        assignment.save(update_fields=["status", "updated_at"])
    return assignment


def _student_safe_results(results):
    """Strip hidden test I/O so stored/returned payloads cannot leak secrets."""
    safe = []
    for row in results or []:
        hidden = bool(row.get("hidden"))
        item = {
            "index": row.get("index"),
            "status": row.get("status"),
            "hidden": hidden,
            "time": row.get("time"),
            "memory": row.get("memory"),
        }
        if not hidden:
            if "stderr" in row:
                item["stderr"] = row.get("stderr") or ""
            if "input" in row:
                item["input"] = row.get("input")
            if "expected" in row:
                item["expected"] = row.get("expected")
            if "actual" in row:
                item["actual"] = row.get("actual")
        safe.append(item)
    return safe


def _award_first_accepted(submission, assignment):
    """Points use the first ACCEPTED timestamp; later accepts add nothing."""
    already = (
        CodeSubmission.objects.filter(
            user_id=submission.user_id,
            question_id=submission.question_id,
            status=CodeSubmission.STATUS_ACCEPTED,
        )
        .exclude(pk=submission.pk)
        .exists()
    )
    if already:
        submission.potential_points = 0
        submission.points_awarded = 0
        return

    points = calculate_potential_points(
        submission.question.created_at,
        submission.submitted_at,
        submission.question.deadline,
    )
    submission.potential_points = points
    if assignment.points_awarded:
        submission.points_awarded = 0
        return
    submission.points_awarded = points
    assignment.points_awarded = points
    assignment.status = "completed"
    if assignment.validated_at is None:
        assignment.validated_at = timezone.now()
    assignment.save(update_fields=["points_awarded", "status", "validated_at", "updated_at"])


class CodeRunView(APIView):
    """POST /api/code/run/ — public tests only, no persistence, no admin notification."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _ensure_active_student(request.user):
            return Response({"detail": "Only active students can run code."}, status=status.HTTP_403_FORBIDDEN)
        serializer = RunCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = Question.objects.filter(
            pk=serializer.validated_data["question_id"], is_active=True
        ).first()
        if not question:
            return Response({"detail": "Question not found."}, status=status.HTTP_404_NOT_FOUND)
        if not _get_active_assignment(request.user, question):
            return Response(ASSIGNMENT_REQUIRED, status=status.HTTP_403_FORBIDDEN)
        cases = list(
            question.test_cases.filter(is_hidden=False).exclude(
                verification_status__in=[
                    TestCase.VERIFICATION_REQUIRES_REVIEW,
                    TestCase.VERIFICATION_INVALID,
                ]
            )
        )
        if not cases:
            return Response(
                {"detail": "This question has no public test cases yet."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            outcome = evaluate_cases(
                serializer.validated_data["source_code"],
                serializer.validated_data["language"],
                cases,
                reveal_io=True,
            )
        except ExecutorUnavailable as exc:
            logger.warning("Code execution unavailable during run: %s", exc.__class__.__name__)
            return Response({"detail": EXECUTOR_UNAVAILABLE_MESSAGE}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        outcome["results"] = _student_safe_results(outcome.get("results"))
        return Response(outcome)


class CodeSubmitView(APIView):
    """POST /api/code/submit/ — persist source, judge all tests, notify, award once."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _ensure_active_student(request.user):
            return Response({"detail": "Only active students can submit code."}, status=status.HTTP_403_FORBIDDEN)
        serializer = RunCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = (
            Question.objects.filter(pk=serializer.validated_data["question_id"], is_active=True)
            .prefetch_related("test_cases")
            .first()
        )
        if not question:
            return Response({"detail": "Question not found."}, status=status.HTTP_404_NOT_FOUND)
        assignment = _get_active_assignment(request.user, question)
        if not assignment:
            return Response(ASSIGNMENT_REQUIRED, status=status.HTTP_403_FORBIDDEN)
        _mark_in_progress(assignment)
        cases = list(
            question.test_cases.exclude(
                verification_status__in=[
                    TestCase.VERIFICATION_REQUIRES_REVIEW,
                    TestCase.VERIFICATION_INVALID,
                ]
            )
        )
        if not cases:
            return Response(
                {"detail": "This question has no test cases yet."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        submission = CodeSubmission.objects.create(
            user=request.user,
            question=question,
            language=serializer.validated_data["language"],
            source_code=serializer.validated_data["source_code"],
            status=CodeSubmission.STATUS_RUNNING,
            total_tests=len(cases),
        )
        try:
            outcome = evaluate_cases(
                submission.source_code,
                submission.language,
                cases,
                reveal_io=True,
            )
        except ExecutorUnavailable as exc:
            logger.warning("Code execution unavailable during submit: %s", exc.__class__.__name__)
            submission.status = CodeSubmission.STATUS_RUNTIME_ERROR
            submission.compile_output = EXECUTOR_UNAVAILABLE_MESSAGE
            submission.save(update_fields=["status", "compile_output", "updated_at"])
            return Response({"detail": EXECUTOR_UNAVAILABLE_MESSAGE, "submission": CodeSubmissionSerializer(submission).data}, status=503)

        with transaction.atomic():
            locked = CodeSubmission.objects.select_for_update().select_related("question", "user").get(pk=submission.pk)
            assignment = Assignment.objects.select_for_update().get(pk=assignment.pk)
            locked.status = outcome["status"]
            locked.tests_passed = outcome["tests_passed"]
            locked.total_tests = outcome["total_tests"]
            locked.execution_time = outcome["execution_time"]
            locked.memory_used = outcome["memory_used"]
            locked.compile_output = outcome["compile_output"]
            locked.public_results = _student_safe_results(outcome.get("results"))
            if locked.status == CodeSubmission.STATUS_ACCEPTED:
                _award_first_accepted(locked, assignment)
            locked.save()

        notify_admin_code_submitted(locked)
        notify_student_code_result(locked)
        return Response(CodeSubmissionSerializer(locked).data, status=status.HTTP_201_CREATED)


class CodeSubmissionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/code/submissions/ — admin sees all; students see only their own.
    GET /api/code/submissions/{id}/ — source_code included; students cannot read others.
    """

    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "language", "question"]
    search_fields = ["user__username", "user__first_name", "user__last_name", "user__email", "question__title"]
    ordering_fields = ["submitted_at", "status"]

    def get_queryset(self):
        qs = CodeSubmission.objects.select_related("user", "question", "user__profile")
        profile = getattr(self.request.user, "profile", None)
        if profile and profile.is_admin:
            return qs.exclude(user__profile__is_removed=True)
        return qs.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == "retrieve":
            return CodeSubmissionSerializer
        return CodeSubmissionListSerializer

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        qs = self.get_queryset().filter(user=request.user)
        question_id = request.query_params.get("question")
        if question_id:
            qs = qs.filter(question_id=question_id)
        page = self.paginate_queryset(qs)
        serializer = CodeSubmissionListSerializer(page or qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)
