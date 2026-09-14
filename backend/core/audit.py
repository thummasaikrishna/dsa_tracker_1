"""Fail-open, privacy-conscious persistence for selected security events."""

import logging
import re

from .models import AuditLog

logger = logging.getLogger(__name__)

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")
_SAFE_METADATA_KEYS = {"scope", "status_code", "reason", "outcome", "cached"}
_SENSITIVE_METADATA = re.compile(r"password|token|secret|authorization|api[_-]?key|credential", re.I)
_CREDENTIAL_VALUE = re.compile(r"(?i)(?:bearer\s+|eyJ)[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9_-]{12,}")


def _clean_text(value, limit):
    """Bound untrusted text and prevent control-character log injection."""
    return _CONTROL_CHARS.sub(" ", str(value or "")).strip()[:limit]


def _safe_user_agent(value):
    return _CREDENTIAL_VALUE.sub("[redacted]", _clean_text(value, 255))


def _request_user(request):
    user = getattr(request, "user", None)
    return user if getattr(user, "is_authenticated", False) else None


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    candidate = forwarded.split(",", 1)[0] if forwarded else request.META.get("REMOTE_ADDR", "")
    return _clean_text(candidate, 45) or None


def _safe_metadata(metadata):
    """Allow only predeclared, scalar metadata; never retain client payloads."""
    if not isinstance(metadata, dict):
        return {}
    safe = {}
    for key, value in metadata.items():
        if key not in _SAFE_METADATA_KEYS or _SENSITIVE_METADATA.search(key):
            continue
        if isinstance(value, bool):
            safe[key] = value
        elif isinstance(value, int):
            safe[key] = value
        elif isinstance(value, str):
            clean = _clean_text(value, 120)
            if not _SENSITIVE_METADATA.search(clean):
                safe[key] = clean
    return safe


def audit_event(event_type, request=None, *, user=None, success=False, metadata=None):
    """Persist a security event without allowing audit failures to affect requests."""
    if event_type not in dict(AuditLog.EVENT_CHOICES):
        logger.warning("Rejected unknown security audit event")
        return
    try:
        request = request or None
        AuditLog.objects.create(
            user=user or (_request_user(request) if request else None),
            event_type=event_type,
            success=success,
            ip_address=_client_ip(request) if request else None,
            user_agent=_safe_user_agent(request.META.get("HTTP_USER_AGENT", "")) if request else "",
            request_path=_clean_text(getattr(request, "path", ""), 255) if request else "",
            http_method=_clean_text(getattr(request, "method", ""), 10).upper() if request else "",
            metadata=_safe_metadata(metadata),
        )
    except Exception:
        # Audit persistence must never turn a valid application response into a failure.
        logger.warning("Security audit persistence failed for event %s", event_type)
