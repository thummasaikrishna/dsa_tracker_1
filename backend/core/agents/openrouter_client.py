from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

from django.conf import settings


class OpenRouterError(Exception):
    pass


def complete_chat(api_key: str, model: str, system_prompt: str, user_prompt: str) -> str:
    """Server-side OpenRouter Chat Completions call; keys are never logged."""
    if not api_key:
        raise OpenRouterError("missing_key")
    if not model:
        raise OpenRouterError("missing_model")
    payload = {
        "model": model,
        "temperature": settings.OPENROUTER_TEMPERATURE,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    request = urllib.request.Request(
        settings.OPENROUTER_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": settings.OPENROUTER_SITE_URL,
            "X-Title": settings.OPENROUTER_APP_NAME,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.OPENROUTER_TIMEOUT) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise OpenRouterError(f"http_{exc.code}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise OpenRouterError("timeout") from exc
    except urllib.error.URLError as exc:
        raise OpenRouterError("network") from exc
    try:
        data = json.loads(raw) if raw else {}
        content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
    except (AttributeError, IndexError, json.JSONDecodeError) as exc:
        raise OpenRouterError("invalid_provider_json") from exc
    if not isinstance(content, str) or not content.strip():
        raise OpenRouterError("empty_response")
    return content
