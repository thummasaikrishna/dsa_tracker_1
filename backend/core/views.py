"""
API views for DSA Tracker.

Organised into four groups, mirroring the PRD's API Modules section:
    /auth        -> RegisterView, MeView
    /questions   -> QuestionViewSet (CRUD, Admin-only writes)
    /assignments -> AssignmentViewSet (assign/unassign/update-status)
    /analytics   -> MyActivityView, StudentActivityView (Admin)
"""

import json
import re
import uuid
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, F, Max, Prefetch, Q, Sum
from django.db.models import Case, CharField, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .filters import AssignmentFilter, QuestionFilter
from .models import Assignment, Notification, Profile, Question, TestCase, normalize_email
from .notify import (
    notify_admin_proof_submitted,
    notify_student_proof_rejected,
    notify_student_proof_validated,
    notify_students_new_question,
    notify_students_question_updated,
    student_activity_snapshot,
    sync_admin_inactivity_notifications,
)
from .permissions import IsAdmin, IsAdminOrReadOnly, IsOwnerOrAdmin
from .scoring import calculate_potential_points
from .serializers import (
    AssignmentCreateSerializer,
    AssignmentSerializer,
    MeSerializer,
    NotificationSerializer,
    ProfileSerializer,
    QuestionSerializer,
    RegisterSerializer,
    AssignmentStatusUpdateSerializer,
    OracleTestCaseRequestSerializer,
    SubmitProofSerializer,
    TestCaseSerializer,
    TrackerTokenObtainPairSerializer,
    TrackerTokenRefreshSerializer,
)


# ---------------------------------------------------------------------------
# Helper: time-window resolution
# ---------------------------------------------------------------------------
def get_period_start(period: str):
    """
    Translate a `period` query param into a concrete datetime cutoff.

    Using timezone-aware `now() - timedelta(days=N)` is deliberately
    simple (O(1), no extra query) and matches the PRD's "Last 7 Days /
    Last 30 Days" requirement precisely. `None` means "all time".
    """
    mapping = {"7days": 7, "30days": 30}
    if period not in mapping:
        raise ValidationError({"period": "Must be one of: 7days, 30days."})
    days = mapping.get(period)
    return timezone.now() - timedelta(days=days)


def validate_analytics_filters(difficulty, status_filter=None):
    if difficulty is not None and difficulty not in dict(Question.DIFFICULTY_CHOICES):
        raise ValidationError({"difficulty": "Contains an unsupported difficulty."})
    if status_filter is not None and status_filter not in dict(Assignment.STATUS_CHOICES):
        raise ValidationError({"status": "Contains an unsupported status."})


def build_breakdown(queryset):
    """
    Single aggregated query that counts assignments grouped by difficulty.

    Instead of running 3 separate `.filter(difficulty='easy').count()`
    queries (3 round-trips to the DB), we use one `.aggregate()` call with
    conditional `Count` expressions — the database does the grouping in a
    single pass. This is the same technique SQL's
    `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` uses under the hood.
    """
    agg = queryset.aggregate(
        easy=Count("id", filter=Q(question__difficulty="easy")),
        medium=Count("id", filter=Q(question__difficulty="medium")),
        hard=Count("id", filter=Q(question__difficulty="hard")),
    )
    agg["total"] = agg["easy"] + agg["medium"] + agg["hard"]
    return agg


def build_status_breakdown(queryset):
    rows = queryset.values("status").annotate(count=Count("id"))
    result = {"assigned": 0, "in_progress": 0, "completed": 0}
    for row in rows:
        result[row["status"]] = row["count"]
    return result


def annotate_workflow_status(queryset):
    """
    Map assignment + proof fields onto the progress tabs:

      assigned   -> assigned, no proof yet
      in_progress -> started or LinkedIn proof pending review
      completed  -> admin-validated / completed
    """
    return queryset.annotate(
        workflow_status=Case(
            When(Q(proof_status="validated") | Q(status="completed"), then=Value("completed")),
            When(Q(proof_status="pending") | Q(status="in_progress"), then=Value("in_progress")),
            default=Value("assigned"),
            output_field=CharField(),
        )
    )


def workflow_status_counts(queryset):
    agg = queryset.aggregate(
        assigned=Count("id", filter=Q(workflow_status="assigned")),
        in_progress=Count("id", filter=Q(workflow_status="in_progress")),
        completed=Count("id", filter=Q(workflow_status="completed")),
    )
    agg["all"] = (agg["assigned"] or 0) + (agg["in_progress"] or 0) + (agg["completed"] or 0)
    return agg


def build_completed_breakdown(queryset):
    """Difficulty counts among completed / validated assignments only."""
    return build_breakdown(queryset.filter(Q(status="completed") | Q(proof_status="validated")))


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class TrackerTokenObtainPairView(TokenObtainPairView):
    serializer_class = TrackerTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_login"


class TrackerTokenRefreshView(TokenRefreshView):
    serializer_class = TrackerTokenRefreshSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_refresh"


def _fetch_supabase_user(access_token):
    """Return an authenticated Supabase user payload, or None for an invalid token."""
    if not settings.SUPABASE_URL.startswith("https://") or not settings.SUPABASE_PUBLISHABLE_KEY:
        return None

    request = Request(
        f"{settings.SUPABASE_URL}/auth/v1/user",
        headers={
            "apikey": settings.SUPABASE_PUBLISHABLE_KEY,
            "Authorization": f"Bearer {access_token}",
        },
    )
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, TimeoutError, ValueError, json.JSONDecodeError):
        return None


def _google_username(email):
    """Create a unique local username without trusting provider display data."""
    prefix = re.sub(r"[^a-zA-Z0-9_.-]", "", email.split("@", 1)[0])[:120] or "google-user"
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class SupabaseGoogleLoginView(APIView):
    """Verify Supabase Google OAuth, link the identity, and issue Django JWTs."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_google"

    def post(self, request):
        access_token = request.data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            return Response({"detail": "Google sign-in could not be completed."}, status=status.HTTP_400_BAD_REQUEST)

        supabase_user = _fetch_supabase_user(access_token)
        if not supabase_user:
            return Response({"detail": "Google sign-in could not be verified."}, status=status.HTTP_401_UNAUTHORIZED)

        metadata = supabase_user.get("app_metadata") or {}
        providers = metadata.get("providers") or []
        if metadata.get("provider") != "google" and "google" not in providers:
            return Response({"detail": "Use a Google account to sign in."}, status=status.HTTP_400_BAD_REQUEST)

        supabase_user_id = supabase_user.get("id")
        email = normalize_email(supabase_user.get("email"))
        if not supabase_user_id or not email or not supabase_user.get("email_confirmed_at"):
            return Response({"detail": "Your Google account must provide a verified email address."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            profile = Profile.objects.select_for_update().select_related("user").filter(
                supabase_user_id=supabase_user_id
            ).first()

            if profile is None:
                # Use the application-wide canonical identity rather than a
                # provider or display value when linking local accounts.
                profile = Profile.objects.select_for_update().select_related("user").filter(
                    normalized_email=email
                ).first()
                if profile is not None:
                    if profile.supabase_user_id and profile.supabase_user_id != supabase_user_id:
                        return Response({"detail": "Unable to safely link this account."}, status=status.HTTP_409_CONFLICT)
                else:
                    user_metadata = supabase_user.get("user_metadata") or {}
                    full_name = (user_metadata.get("full_name") or user_metadata.get("name") or "").strip()
                    first_name, _, last_name = full_name.partition(" ")
                    user = User.objects.create_user(
                        username=_google_username(email),
                        email=email,
                        first_name=first_name[:150],
                        last_name=last_name[:150],
                    )
                    profile = user.profile

                profile.supabase_user_id = supabase_user_id
                profile.save(update_fields=["supabase_user_id"])

            if profile.is_removed or not profile.user.is_active:
                return Response(
                    {"detail": "ACCOUNT_REMOVED", "code": "account_removed"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            refresh = RefreshToken.for_user(profile.user)

        return Response({"access": str(refresh.access_token), "refresh": str(refresh)})


class RegisterView(generics.CreateAPIView):
    """
    Public signup endpoint. Substitutes for the PRD's "New User" Google
    OAuth flow — a Profile is auto-created via the post_save signal with
    role='user' the moment the User row commits.
    """
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_register"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": MeSerializer(user).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )


class LogoutView(APIView):
    """Blacklist the caller's refresh token and always remove no server state by ID."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_logout"

    def post(self, request):
        raw_refresh = request.data.get("refresh")
        if isinstance(raw_refresh, str) and raw_refresh:
            try:
                refresh = RefreshToken(raw_refresh)
                if str(refresh.get("user_id")) == str(request.user.id):
                    refresh.blacklist()
            except TokenError:
                # Idempotent logout: expired or already-blacklisted tokens are
                # not errors and no token material is reflected to the client.
                pass
        return Response({"detail": "Logged out."}, status=status.HTTP_200_OK)


class MeView(APIView):
    """Returns the authenticated user's identity + role — drives frontend route guarding."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(MeSerializer(request.user).data)


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------
class QuestionViewSet(viewsets.ModelViewSet):
    """
    Full CRUD for DSA questions.

    - list/retrieve: any authenticated user (SAFE_METHODS)
    - create/update/delete: Admin only (IsAdminOrReadOnly)
    - Deletes are *soft deletes* (is_active=False) so historical
      assignments referencing a removed question don't dangle or lose
      their audit trail — this mirrors real-world "archive, don't
      destroy" data-integrity practice.
    """
    serializer_class = QuestionSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_class = QuestionFilter
    search_fields = ["title", "description"]
    ordering_fields = ["created_at", "difficulty", "title"]

    def get_queryset(self):
        qs = Question.objects.filter(is_active=True).annotate(assignment_count=Count("assignments"))
        user = self.request.user
        is_admin = bool(
            user.is_authenticated and hasattr(user, "profile") and user.profile.is_admin
        )
        if is_admin:
            qs = qs.prefetch_related("test_cases")
        else:
            # Students never load hidden stdin/expected output from the database.
            qs = qs.prefetch_related(
                Prefetch(
                    "test_cases",
                    queryset=TestCase.objects.filter(is_hidden=False).exclude(
                        verification_status__in=[
                            TestCase.VERIFICATION_REQUIRES_REVIEW,
                            TestCase.VERIFICATION_INVALID,
                        ]
                    ),
                )
            )
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        # Pre-fetch the requesting user's own assignment IDs ONCE per request
        # instead of once per serialized row.
        if self.request.user.is_authenticated:
            mapping = dict(
                Assignment.objects.filter(user=self.request.user).values_list("question_id", "id")
            )
            ctx["my_assignments"] = mapping
            ctx["my_assignment_ids"] = set(mapping.keys())
        return ctx

    def perform_create(self, serializer):
        question = serializer.save(created_by=self.request.user)
        notify_students_new_question(question)

    def perform_update(self, serializer):
        question = serializer.save()
        notify_students_question_updated(question)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsAdmin])
    def validate_reference_solution(self, request, pk=None):
        """Validate admin-supplied reference code through the remote sandbox."""
        from .oracle import validate_reference_solution

        question = self.get_object()
        result = validate_reference_solution(question)
        return Response(
            {
                "ok": result.ok,
                "reference_solution_status": question.reference_solution_status,
                "reference_solution_error": question.reference_solution_error,
            },
            status=status.HTTP_200_OK if result.ok else status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsAdmin])
    def generate_oracle_testcase(self, request, pk=None):
        """Persist sandbox-derived expected output for one already validated candidate input."""
        from .oracle import ReferenceSolutionNotVerified, generate_expected_output
        from .agents.constraint_validator import normalize_candidate_input, validate_generated_candidates

        question = self.get_object()
        serializer = OracleTestCaseRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        input_data = serializer.validated_data["input_data"]
        # Treat this as a candidate input, not trusted test data.  It must
        # pass the same Phase 2 gate used by the AI generation endpoint before
        # the Oracle can ever be called.
        candidate = validate_generated_candidates(
            {"public_test_cases": [{"input": input_data}], "hidden_test_cases": []},
            question.title,
            question.description,
        )
        if not candidate["public_test_cases"]:
            return Response(
                {"input_data": "Candidate input failed problem constraints.", "state": "invalid_candidate"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        normalized_input = normalize_candidate_input(input_data)
        if any(
            normalize_candidate_input(existing) == normalized_input
            for existing in question.test_cases.values_list("input_data", flat=True)
        ):
            return Response({"input_data": "Duplicate testcase input."}, status=status.HTTP_400_BAD_REQUEST)
        if question.reference_solution_status != Question.REFERENCE_SOLUTION_VERIFIED:
            return Response(
                {"detail": "Reference solution not verified.", "state": "reference_solution_not_verified"},
                status=status.HTTP_409_CONFLICT,
            )
        validation_type = serializer.validated_data["validation_type"]
        validator_type = serializer.validated_data["validator_type"]
        test_case = TestCase(
            question=question,
            input_data=input_data,
            is_hidden=serializer.validated_data["is_hidden"],
            order=serializer.validated_data.get("order", question.test_cases.count()),
            validation_type=validation_type,
            validator_type=validator_type if validation_type == TestCase.VALIDATION_CUSTOM else "",
        )
        try:
            # The candidate's request deliberately has no expected_output field.
            # Only the verified reference execution supplies that value.
            test_case.expected_output = generate_expected_output(question, input_data)
        except ReferenceSolutionNotVerified as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        test_case.verification_status = TestCase.VERIFICATION_VERIFIED
        test_case.verification_reason = "Generated by verified reference solution."
        test_case.save()
        return Response(TestCaseSerializer(test_case).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsAdmin])
    def generate_expected_outputs(self, request, pk=None):
        """Process a bounded set of awaiting candidates after reference verification."""
        from .agents.constraint_validator import validate_generated_candidates
        from .oracle import ReferenceSolutionNotVerified, populate_testcase_expected_output

        question = self.get_object()
        if question.reference_solution_status != Question.REFERENCE_SOLUTION_VERIFIED:
            return Response(
                {"detail": "Reference solution not verified.", "state": "reference_solution_not_verified"},
                status=status.HTTP_409_CONFLICT,
            )
        candidates = list(
            question.test_cases.filter(
                verification_status__in=[
                    TestCase.VERIFICATION_GENERATED,
                    TestCase.VERIFICATION_REQUIRES_REVIEW,
                ],
                expected_output="",
            ).order_by("order", "id")[:10]
        )
        verified, invalid, failed = [], [], []
        for test_case in candidates:
            bucket = "hidden_test_cases" if test_case.is_hidden else "public_test_cases"
            checked = validate_generated_candidates(
                {"public_test_cases": [], "hidden_test_cases": []} | {bucket: [{"input": test_case.input_data}]},
                question.title,
                question.description,
            )
            if not checked[bucket]:
                test_case.verification_status = TestCase.VERIFICATION_INVALID
                test_case.verification_reason = "Candidate input failed problem constraints."
                test_case.save(update_fields=["verification_status", "verification_reason"])
                invalid.append(test_case)
                continue
            try:
                verified.append(populate_testcase_expected_output(test_case))
            except ReferenceSolutionNotVerified as exc:
                test_case.verification_status = TestCase.VERIFICATION_REQUIRES_REVIEW
                test_case.verification_reason = str(exc)[:255]
                test_case.save(update_fields=["verification_status", "verification_reason"])
                failed.append(test_case)
        return Response(
            {
                "verified": TestCaseSerializer(verified, many=True).data,
                "invalid": TestCaseSerializer(invalid, many=True).data,
                "failed": TestCaseSerializer(failed, many=True).data,
                "remaining": question.test_cases.filter(
                    verification_status__in=[TestCase.VERIFICATION_GENERATED, TestCase.VERIFICATION_REQUIRES_REVIEW],
                    expected_output="",
                ).count(),
            }
        )


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------
class AssignmentViewSet(viewsets.ModelViewSet):
    """
    Assign / unassign / update status / submit LinkedIn proof.

    - A regular user only ever sees & mutates their OWN assignments.
    - An Admin can see ALL assignments and validate LinkedIn proofs.
    """
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]
    filterset_class = AssignmentFilter
    ordering_fields = ["assigned_at", "updated_at", "submitted_at"]

    def get_queryset(self):
        base = Assignment.objects.select_related("question", "user", "validated_by")
        if hasattr(self.request.user, "profile") and self.request.user.profile.is_admin:
            student_id = self.request.query_params.get("user")
            if student_id:
                return base.filter(user_id=student_id)
            return base
        return base.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return AssignmentCreateSerializer
        return AssignmentSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        assignment = serializer.save()
        sync_admin_inactivity_notifications()
        return Response(AssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """State changes use explicit, ownership-checked workflow actions only."""
        return self.http_method_not_allowed(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """Prevent PATCH from bypassing status/proof/score workflow controls."""
        return self.http_method_not_allowed(request, *args, **kwargs)

    @action(detail=True, methods=["patch"])
    def status_update(self, request, pk=None):
        """PATCH /assignments/{id}/status_update/  { "status": "completed" }"""
        assignment = self.get_object()
        if assignment.proof_status == "validated":
            return Response(
                {"detail": "Validated solutions cannot change status."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = AssignmentStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]
        # Users mark completed only after admin validates LinkedIn proof.
        if new_status == "completed" and assignment.proof_status != "validated":
            return Response(
                {"detail": "Submit a LinkedIn proof and wait for admin validation to complete."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        assignment.status = new_status
        assignment.save(update_fields=["status", "updated_at"])
        return Response(AssignmentSerializer(assignment).data)

    @action(detail=True, methods=["post"])
    def submit_proof(self, request, pk=None):
        """
        POST /assignments/{id}/submit_proof/
        Body: { "linkedin_post_url": "https://www.linkedin.com/..." }

        Student submits LinkedIn post URL as proof of work.
        """
        assignment = self.get_object()
        if assignment.user_id != request.user.id:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        if assignment.proof_status == "validated":
            return Response(
                {"detail": "This solution is already validated."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = SubmitProofSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Store exactly what the student submitted (validated LinkedIn URL only).
        # First submission timestamp is frozen so clock-resets and resubmits
        # cannot change potential points.
        now = timezone.now()
        assignment.linkedin_post_url = serializer.validated_data["linkedin_post_url"]
        assignment.proof_status = "pending"
        if assignment.submitted_at is None:
            assignment.submitted_at = now
            assignment.potential_points = calculate_potential_points(
                assignment.question.created_at,
                assignment.submitted_at,
                assignment.question.deadline,
            )
        Notification.objects.filter(
            event=Notification.EVENT_PROOF_REJECTED,
            assignment=assignment,
        ).delete()
        # Keep workflow consistent: proof pending means not completed yet.
        if assignment.status in ("assigned", "completed"):
            assignment.status = "in_progress"
        assignment.save(
            update_fields=[
                "linkedin_post_url",
                "proof_status",
                "submitted_at",
                "potential_points",
                "status",
                "updated_at",
            ]
        )
        notify_admin_proof_submitted(assignment)
        sync_admin_inactivity_notifications()
        return Response(AssignmentSerializer(assignment).data)

    def destroy(self, request, *args, **kwargs):
        assignment = self.get_object()
        if assignment.user_id != request.user.id:
            return Response(
                {"detail": "You can only unassign your own questions."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if assignment.proof_status == "validated":
            return Response(
                {"detail": "Validated solutions cannot be unassigned."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        assignment_id = assignment.id
        question_id = assignment.question_id
        assignment.delete()
        return Response(
            {"detail": "Question unassigned successfully.", "id": assignment_id, "question": question_id},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def unassign(self, request, pk=None):
        """POST /assignments/{id}/unassign/ — same as destroy, for clients that prefer POST."""
        return self.destroy(request, pk=pk)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsAdmin])
    def validate_proof(self, request, pk=None):
        """
        POST /assignments/{id}/validate_proof/

        Admin validates the student's LinkedIn proof of work.
        Awards stored potential_points exactly once (idempotent).
        """
        with transaction.atomic():
            try:
                assignment = (
                    self.get_queryset()
                    .select_for_update()
                    .select_related("question", "user")
                    .get(pk=pk)
                )
            except Assignment.DoesNotExist:
                return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

            if assignment.proof_status == "validated":
                return Response(AssignmentSerializer(assignment).data)

            if assignment.proof_status != "pending":
                return Response(
                    {"detail": "Only pending submissions can be validated."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not assignment.linkedin_post_url:
                return Response(
                    {"detail": "No LinkedIn proof URL on this assignment."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            assignment.proof_status = "validated"
            assignment.status = "completed"
            assignment.validated_at = timezone.now()
            assignment.validated_by = request.user
            assignment.points_awarded = assignment.potential_points
            assignment.save(
                update_fields=[
                    "proof_status",
                    "status",
                    "validated_at",
                    "validated_by",
                    "points_awarded",
                    "updated_at",
                ]
            )

        notify_student_proof_validated(assignment)
        return Response(AssignmentSerializer(assignment).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsAdmin])
    def reject_proof(self, request, pk=None):
        """
        POST /assignments/{id}/reject_proof/

        Admin rejects a pending LinkedIn proof. Awards 0 points. Idempotent.
        """
        with transaction.atomic():
            try:
                assignment = (
                    self.get_queryset()
                    .select_for_update()
                    .select_related("question", "user")
                    .get(pk=pk)
                )
            except Assignment.DoesNotExist:
                return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

            if assignment.proof_status == "rejected":
                return Response(AssignmentSerializer(assignment).data)
            if assignment.proof_status == "validated":
                return Response(
                    {"detail": "Validated solutions cannot be rejected."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if assignment.proof_status != "pending":
                return Response(
                    {"detail": "Only pending submissions can be rejected."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            assignment.proof_status = "rejected"
            assignment.points_awarded = 0
            assignment.save(update_fields=["proof_status", "points_awarded", "updated_at"])

        notify_student_proof_rejected(assignment)
        return Response(AssignmentSerializer(assignment).data)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
class MyActivityView(APIView):
    """
    GET /analytics/my-activity?period=30days&difficulty=easy

    Returns the authenticated user's own activity: difficulty breakdown,
    status breakdown, and the underlying assignment rows — exactly the
    "MY ACTIVITY" panel described in PRD section 16.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        period = request.query_params.get("period", "30days")
        difficulty = request.query_params.get("difficulty")
        validate_analytics_filters(difficulty)

        qs = Assignment.objects.filter(user=request.user).select_related("question")
        start = get_period_start(period)
        if start:
            qs = qs.filter(assigned_at__gte=start)
        if difficulty:
            qs = qs.filter(question__difficulty=difficulty)
        qs = annotate_workflow_status(qs)

        return Response(
            {
                "period": period,
                "breakdown": build_breakdown(qs),
                "status_breakdown": workflow_status_counts(qs),
                "completed_breakdown": build_completed_breakdown(qs),
                "items": AssignmentSerializer(qs, many=True).data,
            }
        )


class StudentActivityView(APIView):
    """
    GET /analytics/student/{user_id}?period=30days&difficulty=hard&status=completed

    Admin-only. Mirrors PRD section 17 (Admin Student Tracking): pick a
    student, a time period, optionally a difficulty and status, then view
    their stats + underlying question list.
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request, user_id):
        period = request.query_params.get("period", "30days")
        difficulty = request.query_params.get("difficulty")
        status_filter = request.query_params.get("status")
        validate_analytics_filters(difficulty, status_filter)

        qs = Assignment.objects.filter(user_id=user_id).select_related("question", "user")
        start = get_period_start(period)
        if start:
            qs = qs.filter(assigned_at__gte=start)
        if difficulty:
            qs = qs.filter(question__difficulty=difficulty)
        qs = annotate_workflow_status(qs)
        status_counts = workflow_status_counts(qs)
        if status_filter:
            qs = qs.filter(workflow_status=status_filter)

        student = User.objects.filter(id=user_id).select_related("profile").first()
        if not student or not hasattr(student, "profile") or student.profile.role != "user":
            return Response({"detail": "Student not found."}, status=status.HTTP_404_NOT_FOUND)

        snap = student_activity_snapshot(user_id)
        return Response(
            {
                "student": ProfileSerializer(student.profile).data,
                "period": period,
                "breakdown": build_breakdown(qs),
                "status_breakdown": status_counts,
                "completed_breakdown": build_completed_breakdown(qs),
                "items": AssignmentSerializer(qs, many=True).data,
                "activity": snap,
            }
        )


class StudentListView(generics.ListAPIView):
    """GET /analytics/students — Admin-only roster for the Student Activity search picker."""
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = ProfileSerializer

    def get_queryset(self):
        qs = (
            Profile.objects.filter(role="user", is_removed=False)
            .select_related("user")
            .annotate(
                total_assignments=Count("user__assignments"),
                proof_count=Count(
                    "user__assignments",
                    filter=~Q(user__assignments__proof_status="none"),
                ),
            )
        )
        search = (self.request.query_params.get("search") or "").strip()
        if len(search) > 100:
            raise ValidationError({"search": "Must not exceed 100 characters."})
        if search:
            qs = qs.filter(
                Q(user__username__icontains=search)
                | Q(user__email__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
            )
        return qs.order_by("user__username")


class OverviewStatsView(APIView):
    """
    GET /analytics/overview/

    Admin-only dashboard totals: users, questions, assignments, completed.
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        return Response(
            {
                "total_users": Profile.objects.filter(role="user", is_removed=False).count(),
                "total_questions": Question.objects.filter(is_active=True).count(),
                "total_assignments": Assignment.objects.count(),
                "total_completed": Assignment.objects.filter(status="completed").count(),
                "pending_proofs": Assignment.objects.filter(proof_status="pending").count(),
            }
        )


class PendingProofsView(APIView):
    """
    GET /analytics/pending-proofs/

    Admin-only: pending LinkedIn proof submissions for in-app notifications.
    Ordered newest-first so admins see the latest submissions first.
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        qs = (
            Assignment.objects.filter(proof_status="pending", user__profile__is_removed=False)
            .select_related("question", "user")
            .order_by("-submitted_at", "-updated_at")
        )
        return Response(
            {
                "count": qs.count(),
                "items": AssignmentSerializer(qs, many=True).data,
            }
        )


class NotificationListView(APIView):
    """GET /notifications/ — current user's in-app notifications (newest first)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if getattr(request.user, "profile", None) and request.user.profile.is_admin:
            sync_admin_inactivity_notifications()
        qs = (
            Notification.objects.filter(user=request.user, is_dismissed=False)
            .select_related("question", "assignment", "about_user", "code_submission")
            .order_by("-created_at")[:50]
        )
        unread = Notification.objects.filter(
            user=request.user, is_read=False, is_dismissed=False
        ).count()
        return Response(
            {
                "unread_count": unread,
                "items": NotificationSerializer(qs, many=True).data,
            }
        )


class NotificationReadView(APIView):
    """POST/PATCH /notifications/{id}/read/ — mark one of the current user's notifications as read."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        return self._mark_read(request, pk)

    def patch(self, request, pk):
        return self._mark_read(request, pk)

    def _mark_read(self, request, pk):
        notif = Notification.objects.filter(user=request.user, pk=pk).first()
        if not notif:
            return Response({"detail": "Notification not found."}, status=status.HTTP_404_NOT_FOUND)
        if not notif.is_read:
            notif.is_read = True
            notif.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notif).data)


class NotificationDismissView(APIView):
    """POST/PATCH /notifications/{id}/dismiss/ — hide from dropdown; persisted per user."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        return self._dismiss(request, pk)

    def patch(self, request, pk):
        return self._dismiss(request, pk)

    def _dismiss(self, request, pk):
        notif = Notification.objects.filter(user=request.user, pk=pk).first()
        if not notif:
            return Response({"detail": "Notification not found."}, status=status.HTTP_404_NOT_FOUND)
        notif.is_dismissed = True
        if not notif.is_read:
            notif.is_read = True
        notif.save(update_fields=["is_dismissed", "is_read"])
        return Response(NotificationSerializer(notif).data)


class NotificationReadAllView(APIView):
    """POST /notifications/read-all/"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(
            user=request.user, is_read=False, is_dismissed=False
        ).update(is_read=True)
        return Response({"detail": "ok"})


class LeaderboardView(APIView):
    """
    GET /analytics/leaderboard/

    Active (non-removed) students ranked by validated points_awarded.
    Tie-break: more validated problems, then earlier latest validation time.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = (
            Profile.objects.filter(role="user", is_removed=False)
            .select_related("user")
            .annotate(
                total_points=Coalesce(
                    Sum("user__assignments__points_awarded"),
                    0,
                ),
                solved_count=Count(
                    "user__assignments",
                    filter=Q(user__assignments__proof_status="validated")
                    | Q(user__assignments__status="completed"),
                    distinct=True,
                ),
                last_validated_at=Max(
                    "user__assignments__validated_at",
                    filter=Q(user__assignments__proof_status="validated")
                    | Q(user__assignments__status="completed"),
                ),
                last_code_at=Max(
                    "user__code_submissions__submitted_at",
                    filter=Q(user__code_submissions__status="accepted"),
                ),
                last_activity_at=Max("user__assignments__updated_at"),
            )
            .order_by(
                "-total_points",
                "-solved_count",
                F("last_validated_at").asc(nulls_last=True),
                F("last_code_at").asc(nulls_last=True),
                "user__username",
            )
        )

        me_id = request.user.id
        is_admin = hasattr(request.user, "profile") and request.user.profile.is_admin
        rows = []
        my_row = None
        for rank, profile in enumerate(qs, start=1):
            display = profile.user.get_full_name() or profile.user.username
            last = profile.last_validated_at
            if profile.last_code_at and (last is None or profile.last_code_at > last):
                last = profile.last_code_at
            item = {
                "rank": rank,
                "user_id": profile.user_id,
                "username": profile.user.username,
                "display_name": display,
                "total_points": int(profile.total_points or 0),
                "solved_count": int(profile.solved_count or 0),
                "last_validated_at": last,
                "last_activity_at": profile.last_activity_at,
                "is_me": profile.user_id == me_id,
            }
            rows.append(item)
            if item["is_me"]:
                my_row = item

        return Response(
            {
                "items": rows,
                "me": my_row,
                "is_admin": is_admin,
            }
        )


class ContactAdminView(APIView):
    """Public: admin email for Contact Admin (no secrets)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        admin = (
            Profile.objects.filter(role="admin", is_removed=False)
            .select_related("user")
            .first()
        )
        if not admin:
            return Response({"email": "", "name": "Admin"})
        user = admin.user
        return Response(
            {
                "email": user.email or "",
                "name": user.get_full_name() or user.username,
            }
        )


class RemoveStudentView(APIView):
    """
    POST /analytics/students/{user_id}/remove/

    Soft-remove a student. Keeps User/Profile/assignments for audit.
    Admin-only. Students cannot call this.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, user_id):
        profile = (
            Profile.objects.filter(user_id=user_id, role="user")
            .select_related("user")
            .first()
        )
        if not profile:
            return Response({"detail": "Student not found."}, status=status.HTTP_404_NOT_FOUND)
        if profile.is_removed:
            return Response({"detail": "Student is already removed."}, status=status.HTTP_400_BAD_REQUEST)

        profile.is_removed = True
        profile.removed_at = timezone.now()
        profile.save(update_fields=["is_removed", "removed_at"])
        profile.user.is_active = False
        profile.user.save(update_fields=["is_active"])
        Notification.objects.filter(
            event=Notification.EVENT_STUDENT_INACTIVE, about_user_id=user_id
        ).delete()
        return Response({"detail": "Student removed successfully.", "user_id": user_id})
