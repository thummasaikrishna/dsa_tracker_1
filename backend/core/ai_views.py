from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .agents import AIGenerationUnavailable, generate_question_data
from .audit import audit_event
from .models import AuditLog
from .permissions import IsAdmin
from .throttles import AIGenerationThrottle


class GenerateQuestionDataSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255, allow_blank=True, required=False, default="")
    problem_statement = serializers.CharField(allow_blank=False, max_length=40_000)
    examples = serializers.CharField(allow_blank=True, max_length=20_000, required=False, default="")


class GenerateQuestionDataView(APIView):
    """POST /api/admin/ai/generate-question-data/ — admin-only draft generation."""

    permission_classes = [IsAuthenticated, IsAdmin]
    throttle_classes = [AIGenerationThrottle]

    def post(self, request):
        serializer = GenerateQuestionDataSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            problem_statement = serializer.validated_data["problem_statement"]
            examples = serializer.validated_data.get("examples") or ""
            if examples.strip():
                problem_statement += "\n\nAuthor-provided examples (preserve their input/output contract):\n" + examples
            data, cached = generate_question_data(
                serializer.validated_data.get("title") or "",
                problem_statement,
            )
        except AIGenerationUnavailable:
            return Response(
                {
                    "success": False,
                    "message": "AI generation is temporarily unavailable. Please try again later.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except ValueError:
            return Response(
                {"success": False, "message": "Unable to generate question details. Please try again."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        audit_event(AuditLog.AI_GENERATION, request, success=True, metadata={"cached": cached})
        return Response({"success": True, "data": data, "cached": cached})
