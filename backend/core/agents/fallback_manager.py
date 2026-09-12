from __future__ import annotations

import logging

from django.conf import settings

from .openrouter_client import OpenRouterError, complete_chat
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .response_validator import ValidationError, extract_json, validate_payload

logger = logging.getLogger(__name__)

# A malformed generated document is safe to regenerate with the next provider
# credential. Candidate test inputs are validated structurally here; expected
# outputs are deliberately outside the AI generation flow in Phase 1.
def _attempts():
    keys = list(getattr(settings, "OPENROUTER_API_KEYS", []) or [])
    for index, key in enumerate(keys, start=1):
        key = (key or "").strip()
        model = (getattr(settings, "OPENROUTER_MODEL", "") or "").strip()
        if not key or not model:
            continue
        yield index, key, model


def _should_fallback(error: Exception) -> bool:
    if isinstance(error, ValidationError):
        return True
    # A key can be disabled, expired, or lack model access (normally 401/403).
    # Those failures are credential-specific, so a later configured key may
    # still work. Each key is attempted only once; this is bounded failover.
    return isinstance(error, OpenRouterError)


def run_with_fallback(title: str, problem_statement: str) -> dict:
    user_prompt = build_user_prompt(title, problem_statement)
    last_error = "unavailable"
    any_attempt = False
    for index, api_key, model in _attempts():
        any_attempt = True
        label = f"attempt_{index}"
        try:
            raw = complete_chat(api_key, model, SYSTEM_PROMPT, user_prompt)
            payload = validate_payload(extract_json(raw))
            logger.info("DSA analysis agent %s succeeded", label)
            return payload
        except (OpenRouterError, ValidationError, ValueError, TypeError) as exc:
            last_error = exc.__class__.__name__
            logger.warning("DSA analysis agent %s failed (%s)", label, last_error)
            if _should_fallback(exc):
                continue
            break
    if not any_attempt:
        logger.warning("DSA analysis agent has no configured API keys or models")
    raise RuntimeError(last_error)
