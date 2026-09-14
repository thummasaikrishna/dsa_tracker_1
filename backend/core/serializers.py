from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.utils import get_md5_hash_password

from .audit import audit_event
from .models import AuditLog
from .models import Assignment, CodeSubmission, Notification, Profile, Question, TestCase, normalize_email


# ---------------------------------------------------------------------------
# Auth / User
# ---------------------------------------------------------------------------
class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    email = serializers.EmailField(required=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "first_name", "last_name"]

    def validate_email(self, value):
        email = normalize_email(value)
        if not email:
            raise serializers.ValidationError("An email address is required.")
        if Profile.objects.filter(normalized_email=email).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return email

    def create(self, validated_data):
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=validated_data["username"],
                    email=validated_data["email"],
                    password=validated_data["password"],
                    first_name=validated_data.get("first_name", ""),
                    last_name=validated_data.get("last_name", ""),
                )
        except IntegrityError:
            # The Profile uniqueness constraint also closes the race between
            # validation and creation without returning database details.
            raise serializers.ValidationError({"email": "An account with this email already exists."})
        return user


class TrackerTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Issue JWTs, but return a dedicated removed-account error after a valid password."""

    def validate(self, attrs):
        attrs["verification_status"] = (
            attrs.get("verification_status") or TestCase.VERIFICATION_VERIFIED
        )
        raw_username = (attrs.get(self.username_field) or "").strip()
        password = attrs.get("password") or ""
        attrs[self.username_field] = raw_username

        user = User.objects.filter(username__iexact=raw_username).first()
        if user is None and "@" in raw_username:
            user = User.objects.filter(email__iexact=raw_username).first()
            if user:
                attrs[self.username_field] = user.username

        if user and user.username != raw_username and "@" not in raw_username:
            # Case-insensitive username match (e.g. Krishnathumma vs krishnathumma)
            attrs[self.username_field] = user.username

        if user and user.check_password(password):
            profile = getattr(user, "profile", None)
            if profile is not None and profile.is_removed:
                raise AuthenticationFailed(
                    detail={"detail": "ACCOUNT_REMOVED", "code": "account_removed"},
                    code="account_removed",
                )
            if not user.is_active:
                raise AuthenticationFailed(
                    detail={"detail": "ACCOUNT_REMOVED", "code": "account_removed"},
                    code="account_removed",
                )
        data = super().validate(attrs)
        audit_event(AuditLog.AUTH_LOGIN_SUCCESS, self.context.get("request"), user=self.user, success=True)
        return data


class TrackerTokenRefreshSerializer(TokenRefreshSerializer):
    """Reject a refresh token after its user's password has changed."""

    def validate(self, attrs):
        refresh = RefreshToken(attrs["refresh"])
        try:
            user = User.objects.get(pk=refresh[api_settings.USER_ID_CLAIM])
        except (User.DoesNotExist, KeyError):
            raise InvalidToken("Token is not valid")

        if (
            not user.is_active
            or refresh.get(api_settings.REVOKE_TOKEN_CLAIM) != get_md5_hash_password(user.password)
        ):
            raise InvalidToken("Token is not valid")
        profile = getattr(user, "profile", None)
        if profile is not None and profile.is_removed:
            raise InvalidToken("Token is not valid")
        return super().validate(attrs)


class ProfileSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    total_assignments = serializers.IntegerField(read_only=True, required=False)
    proof_count = serializers.IntegerField(read_only=True, required=False)
    activity_state = serializers.SerializerMethodField()
    is_removed = serializers.BooleanField(read_only=True)

    class Meta:
        model = Profile
        fields = [
            "id", "user_id", "username", "email", "first_name", "last_name",
            "role", "created_at", "total_assignments", "proof_count",
            "activity_state", "is_removed",
        ]
        read_only_fields = ["role"]

    def get_activity_state(self, obj):
        assigned = getattr(obj, "total_assignments", None)
        proofs = getattr(obj, "proof_count", None)
        if assigned is None or proofs is None:
            from .notify import student_activity_snapshot
            return student_activity_snapshot(obj.user_id)["activity_state"]
        if assigned == 0:
            return "no_activity"
        if proofs == 0:
            return "inactive"
        return "active"


class MeSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    is_removed = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "role", "is_removed"]

    def _profile(self, obj):
        profile = getattr(obj, "profile", None)
        if profile is None:
            profile, _ = Profile.objects.get_or_create(user=obj)
        return profile

    def get_role(self, obj):
        return self._profile(obj).role

    def get_is_removed(self, obj):
        return self._profile(obj).is_removed


# ---------------------------------------------------------------------------
# Question
# ---------------------------------------------------------------------------
class TestCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestCase
        fields = [
            "id", "input_data", "expected_output", "is_hidden", "order",
            "validation_type", "validator_type", "verification_status", "verification_reason",
        ]
        extra_kwargs = {
            "id": {"required": False},
            # Bound admin authoring payloads without constraining normal DSA cases.
            "input_data": {"max_length": 20_000},
            "expected_output": {"required": False, "allow_blank": True, "max_length": 20_000},
            "validation_type": {"required": False},
            "validator_type": {"required": False, "allow_blank": True},
            "verification_status": {"required": False},
            "verification_reason": {"required": False, "allow_blank": True},
        }

    def validate(self, attrs):
        vtype = (attrs.get("validation_type") or TestCase.VALIDATION_EXACT).upper()
        attrs["validation_type"] = vtype
        verification_status = attrs.get("verification_status") or TestCase.VERIFICATION_GENERATED
        if vtype == TestCase.VALIDATION_CUSTOM:
            validator_type = (attrs.get("validator_type") or "").strip().upper()
            if not validator_type:
                raise serializers.ValidationError(
                    {"validator_type": "Required when validation_type is CUSTOM_VALIDATOR."}
                )
            from core.validators import get_validator

            if get_validator(validator_type) is None:
                raise serializers.ValidationError({"validator_type": "Unknown validator."})
            attrs["validator_type"] = validator_type
            attrs["expected_output"] = attrs.get("expected_output") or ""
        else:
            expected = attrs.get("expected_output")
            if (
                expected is not None
                and not str(expected).strip()
                and verification_status != TestCase.VERIFICATION_REQUIRES_REVIEW
            ):
                raise serializers.ValidationError(
                    {"expected_output": "Expected output is required for exact-match tests."}
                )
            attrs["validator_type"] = ""
        return attrs


class QuestionSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)
    assignment_count = serializers.IntegerField(read_only=True, required=False)
    is_assigned_to_me = serializers.SerializerMethodField()
    my_assignment_id = serializers.SerializerMethodField()
    deadline_expired = serializers.SerializerMethodField()
    remaining_seconds = serializers.SerializerMethodField()
    test_cases = TestCaseSerializer(many=True, required=False)
    public_test_count = serializers.SerializerMethodField()
    hidden_test_count = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = [
            "id", "title", "description", "examples", "prerequisites", "difficulty",
            "created_by", "created_by_username", "created_at", "deadline",
            "deadline_expired", "remaining_seconds", "updated_at",
            "is_active", "assignment_count", "is_assigned_to_me", "my_assignment_id",
            "test_cases", "public_test_count", "hidden_test_count",
            "reference_solution", "reference_solution_language", "reference_solution_status",
            "reference_solution_error",
        ]
        read_only_fields = [
            "created_by", "created_at", "updated_at", "reference_solution_status",
            "reference_solution_error",
        ]
        extra_kwargs = {
            "description": {"max_length": 50_000},
            "examples": {"max_length": 20_000},
            "prerequisites": {"max_length": 10_000},
            "reference_solution": {"max_length": 100_000},
        }

    def _now(self):
        return timezone.now()

    def _is_admin(self):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and hasattr(user, "profile") and user.profile.is_admin)

    def get_is_assigned_to_me(self, obj):
        return self.get_my_assignment_id(obj) is not None

    def get_my_assignment_id(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        mapping = self.context.get("my_assignments")
        if mapping is not None:
            return mapping.get(obj.id)
        assignment = Assignment.objects.filter(user=request.user, question=obj).only("id").first()
        return assignment.id if assignment else None

    def get_deadline_expired(self, obj):
        if not obj.deadline:
            return False
        return self._now() > obj.deadline

    def get_remaining_seconds(self, obj):
        if not obj.deadline:
            return 0
        delta = obj.deadline - self._now()
        return max(0, int(delta.total_seconds()))

    def get_public_test_count(self, obj):
        tests = getattr(obj, "test_cases", None)
        if tests is None:
            return 0
        return sum(1 for t in obj.test_cases.all() if not t.is_hidden)

    def get_hidden_test_count(self, obj):
        if not self._is_admin():
            return None
        return sum(1 for t in obj.test_cases.all() if t.is_hidden)

    def validate_deadline(self, value):
        if value is None:
            raise serializers.ValidationError("Deadline is required.")
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        if not self.instance and value <= timezone.now():
            raise serializers.ValidationError("Deadline must be in the future.")
        return value

    def validate_test_cases(self, cases):
        if sum(bool(case.get("is_hidden")) for case in cases) > 5:
            raise serializers.ValidationError("A question can have at most five hidden test cases.")
        if any(case.get("verification_status") == TestCase.VERIFICATION_INVALID for case in cases):
            raise serializers.ValidationError(
                "Invalid testcases cannot be saved. Remove or correct them first."
            )
        return cases

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self._is_admin():
            student_cases = []
            for row in data.get("test_cases") or []:
                if row.get("is_hidden"):
                    continue
                cleaned = {k: v for k, v in row.items() if k not in {"is_hidden", "validator_type", "verification_status", "verification_reason"}}
                student_cases.append(cleaned)
            data["test_cases"] = student_cases
            data.pop("hidden_test_count", None)
            data.pop("reference_solution", None)
            data.pop("reference_solution_language", None)
            data.pop("reference_solution_status", None)
            data.pop("reference_solution_error", None)
        return data

    def _sync_test_cases(self, question, cases):
        if cases is None:
            return
        question.test_cases.all().delete()
        TestCase.objects.bulk_create(
            [
                TestCase(
                    question=question,
                    input_data=item.get("input_data") or "",
                    expected_output=item.get("expected_output") or "",
                    validation_type=item.get("validation_type") or TestCase.VALIDATION_EXACT,
                    validator_type=item.get("validator_type") or "",
                    verification_status=item.get("verification_status") or TestCase.VERIFICATION_VERIFIED,
                    verification_reason=item.get("verification_reason") or "",
                    is_hidden=bool(item.get("is_hidden")),
                    order=item.get("order") if item.get("order") is not None else index,
                )
                for index, item in enumerate(cases)
            ]
        )

    def create(self, validated_data):
        cases = validated_data.pop("test_cases", None)
        question = super().create(validated_data)
        self._sync_test_cases(question, cases)
        return question

    def update(self, instance, validated_data):
        cases = validated_data.pop("test_cases", None)
        question = super().update(instance, validated_data)
        self._sync_test_cases(question, cases)
        return question


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------
class AssignmentSerializer(serializers.ModelSerializer):
    question_title = serializers.CharField(source="question.title", read_only=True)
    question_description = serializers.CharField(source="question.description", read_only=True)
    question_examples = serializers.CharField(source="question.examples", read_only=True)
    question_prerequisites = serializers.CharField(source="question.prerequisites", read_only=True)
    difficulty = serializers.CharField(source="question.difficulty", read_only=True)
    question_created_at = serializers.DateTimeField(source="question.created_at", read_only=True)
    question_deadline = serializers.DateTimeField(source="question.deadline", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    is_validated = serializers.SerializerMethodField()
    submitted_after_deadline = serializers.SerializerMethodField()
    deadline_expired = serializers.SerializerMethodField()
    remaining_seconds = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = [
            "id", "user", "username", "user_email", "question", "question_title",
            "question_description", "question_examples", "question_prerequisites",
            "difficulty", "question_created_at", "question_deadline",
            "status", "linkedin_post_url", "proof_status",
            "submitted_at", "validated_at", "is_validated",
            "potential_points", "points_awarded", "submitted_after_deadline",
            "deadline_expired", "remaining_seconds",
            "assigned_at", "updated_at",
        ]
        read_only_fields = [
            # Assignment state moves only through explicit workflow actions.
            # This serializer is response-only; it must never reopen a generic
            # PATCH/PUT path for ownership, score, proof, or status changes.
            "id", "user", "question", "status", "assigned_at", "updated_at", "proof_status",
            "submitted_at", "validated_at", "linkedin_post_url",
            "potential_points", "points_awarded",
        ]

    def get_is_validated(self, obj):
        return obj.proof_status == "validated"

    def get_submitted_after_deadline(self, obj):
        deadline = getattr(obj.question, "deadline", None)
        if not obj.submitted_at or not deadline:
            return False
        return obj.submitted_at > deadline

    def get_deadline_expired(self, obj):
        deadline = getattr(obj.question, "deadline", None)
        if not deadline:
            return False
        return timezone.now() > deadline

    def get_remaining_seconds(self, obj):
        deadline = getattr(obj.question, "deadline", None)
        if not deadline:
            return 0
        return max(0, int((deadline - timezone.now()).total_seconds()))


class AssignmentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Assignment
        fields = ["id", "question"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        disallowed = set(self.initial_data) - {"question"}
        if disallowed:
            raise serializers.ValidationError(
                {field: "This field is not allowed when creating an assignment." for field in disallowed}
            )
        request = self.context["request"]
        question = attrs["question"]
        if Assignment.objects.filter(user=request.user, question=question).exists():
            raise serializers.ValidationError("You have already assigned this question.")
        if not question.is_active:
            raise serializers.ValidationError("This question is no longer available.")
        return attrs

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class SubmitProofSerializer(serializers.Serializer):
    linkedin_post_url = serializers.URLField(max_length=500)

    def validate_linkedin_post_url(self, value):
        """
        Accept only LinkedIn domains (linkedin.com / lnkd.in).
        Reject Striver, LeetCode, etc. so admin always sees a real LinkedIn proof URL.
        """
        from urllib.parse import urlparse

        value = (value or "").strip()
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        if not host or parsed.scheme not in ("http", "https"):
            raise serializers.ValidationError(
                "Please paste a full LinkedIn URL starting with https://."
            )

        allowed = ("linkedin.com", "lnkd.in")
        if not any(host == domain or host.endswith("." + domain) for domain in allowed):
            raise serializers.ValidationError(
                "Only LinkedIn post links are accepted (linkedin.com or lnkd.in). "
                "Other links (e.g. Striver / takeuforward) cannot be submitted as proof."
            )
        return value


class AssignmentStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Assignment.STATUS_CHOICES)


class OracleTestCaseRequestSerializer(serializers.Serializer):
    input_data = serializers.CharField(allow_blank=False, trim_whitespace=True, max_length=20_000)
    is_hidden = serializers.BooleanField(required=False, default=False)
    order = serializers.IntegerField(required=False, min_value=0, max_value=32_767)
    validation_type = serializers.ChoiceField(
        choices=TestCase.VALIDATION_CHOICES, required=False, default=TestCase.VALIDATION_EXACT
    )
    validator_type = serializers.CharField(required=False, allow_blank=True, max_length=64, default="")


class NotificationSerializer(serializers.ModelSerializer):
    question_title = serializers.SerializerMethodField()
    difficulty = serializers.SerializerMethodField()
    assignment_id = serializers.IntegerField(read_only=True, allow_null=True)
    question_id = serializers.IntegerField(read_only=True, allow_null=True)
    about_user_id = serializers.IntegerField(read_only=True, allow_null=True)
    about_username = serializers.SerializerMethodField()
    code_submission_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Notification
        fields = [
            "id", "event", "title", "message", "question_id", "question_title",
            "difficulty", "assignment_id", "about_user_id", "about_username",
            "code_submission_id", "is_read", "is_dismissed", "created_at",
        ]
        read_only_fields = fields

    def get_question_title(self, obj):
        return obj.question.title if obj.question_id else None

    def get_difficulty(self, obj):
        return obj.question.difficulty if obj.question_id else None

    def get_about_username(self, obj):
        if not obj.about_user_id:
            return None
        return obj.about_user.get_full_name() or obj.about_user.username


class RunCodeSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    language = serializers.ChoiceField(choices=CodeSubmission.LANGUAGE_CHOICES)
    source_code = serializers.CharField(allow_blank=False, max_length=200_000)


class CodeSubmissionSerializer(serializers.ModelSerializer):
    question_title = serializers.CharField(source="question.title", read_only=True)
    difficulty = serializers.CharField(source="question.difficulty", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    display_name = serializers.SerializerMethodField()
    user_email = serializers.EmailField(source="user.email", read_only=True)
    language_label = serializers.SerializerMethodField()

    class Meta:
        model = CodeSubmission
        fields = [
            "id", "user", "username", "display_name", "user_email",
            "question", "question_title", "difficulty",
            "language", "language_label", "source_code",
            "status", "tests_passed", "total_tests",
            "execution_time", "memory_used", "compile_output",
            "public_results", "potential_points", "points_awarded",
            "submitted_at", "updated_at",
        ]
        read_only_fields = fields

    def get_display_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

    def get_language_label(self, obj):
        return dict(CodeSubmission.LANGUAGE_CHOICES).get(obj.language, obj.language)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        is_admin = bool(user and user.is_authenticated and hasattr(user, "profile") and user.profile.is_admin)
        if is_admin:
            return data
        results = data.get("public_results") or []
        safe = []
        for row in results:
            if not isinstance(row, dict):
                continue
            if row.get("hidden"):
                safe.append(
                    {
                        "index": row.get("index"),
                        "status": row.get("status"),
                        "hidden": True,
                        "time": row.get("time"),
                        "memory": row.get("memory"),
                    }
                )
            else:
                safe.append(row)
        if "public_results" in data:
            data["public_results"] = safe
        return data


class CodeSubmissionListSerializer(CodeSubmissionSerializer):
    """List rows omit huge source_code unless admin retrieve."""

    class Meta(CodeSubmissionSerializer.Meta):
        fields = [
            "id", "user", "username", "display_name", "user_email",
            "question", "question_title", "difficulty",
            "language", "language_label", "status",
            "tests_passed", "total_tests", "execution_time", "memory_used",
            "potential_points", "points_awarded", "submitted_at",
        ]


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
class DifficultyBreakdownSerializer(serializers.Serializer):
    easy = serializers.IntegerField()
    medium = serializers.IntegerField()
    hard = serializers.IntegerField()
    total = serializers.IntegerField()


class ActivitySummarySerializer(serializers.Serializer):
    period = serializers.CharField()
    breakdown = DifficultyBreakdownSerializer()
    status_breakdown = serializers.DictField(child=serializers.IntegerField())
    items = AssignmentSerializer(many=True)
