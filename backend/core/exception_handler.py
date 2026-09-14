"""Safe, consistent error responses for DRF API views."""

import logging

from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, MethodNotAllowed, NotAuthenticated, NotFound, ParseError, PermissionDenied, Throttled, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .audit import audit_event
from .models import AuditLog

logger = logging.getLogger(__name__)


def _error(code, message, details=None, legacy_code=None):
    body = {"success": False, "error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    if legacy_code:
        body["code"] = legacy_code
    return body


def api_exception_handler(exc, context):
    """Normalize expected DRF errors and never expose unexpected exceptions."""
    request = context.get("request")
    path = getattr(request, "path", "")
    view = context.get("view")
    response = drf_exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled API exception on %s", getattr(request, "path", "unknown"))
        audit_event(AuditLog.SERVER_ERROR, request, success=False)
        return Response(_error("server_error", "An unexpected server error occurred."), status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if isinstance(exc, ValidationError):
        audit_event(AuditLog.VALIDATION_FAILURE, request, success=False)
        body = _error("validation_error", "Request validation failed.", response.data)
    elif isinstance(exc, ParseError):
        audit_event(AuditLog.VALIDATION_FAILURE, request, success=False, metadata={"reason": "parse_error"})
        body = _error("parse_error", "Malformed request body.")
    elif isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
        detail = response.data.get("detail") if isinstance(response.data, dict) else None
        exc_detail = getattr(exc, "detail", None)
        legacy_code = (
            detail.get("code") if isinstance(detail, dict)
            else exc_detail.get("code") if isinstance(exc_detail, dict)
            else getattr(exc, "default_code", None)
        )
        if legacy_code == "account_removed":
            event = AuditLog.AUTH_REMOVED_ACCOUNT_ACCESS
        elif path.endswith("/auth/refresh/"):
            event = AuditLog.AUTH_REFRESH_FAILURE
        elif path.endswith("/auth/login/"):
            event = AuditLog.AUTH_LOGIN_FAILURE
        else:
            event = AuditLog.AUTH_TOKEN_FAILURE
        audit_event(event, request, success=False, metadata={"reason": legacy_code or "invalid_credentials"})
        body = _error("authentication_failed", "Authentication credentials are invalid or missing.", legacy_code=legacy_code)
    elif isinstance(exc, PermissionDenied):
        audit_event(AuditLog.AUTH_PERMISSION_DENIED, request, success=False)
        body = _error("permission_denied", "You do not have permission to perform this action.")
    elif isinstance(exc, (NotFound, Http404)):
        body = _error("not_found", "The requested resource was not found.")
    elif isinstance(exc, MethodNotAllowed):
        body = _error("method_not_allowed", "This HTTP method is not allowed for this resource.")
    elif isinstance(exc, Throttled):
        scope = getattr(view, "throttle_scope", "")
        if not scope:
            scopes = [getattr(throttle, "scope", "") for throttle in getattr(view, "throttle_classes", [])]
            scope = next((item for item in scopes if item), "")
        event = {
            "code_execution": AuditLog.CODE_EXECUTION_THROTTLED,
            "code_submission": AuditLog.CODE_SUBMISSION_THROTTLED,
            "ai_generation": AuditLog.AI_GENERATION_THROTTLED,
        }.get(scope, AuditLog.RATE_LIMIT_EXCEEDED)
        audit_event(event, request, success=False, metadata={"scope": scope or "unknown"})
        body = _error("throttled", "Too many requests. Please try again later.")
    else:
        body = _error("request_error", "The request could not be completed.")
    response.data = body
    return response
