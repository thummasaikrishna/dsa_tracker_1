from __future__ import annotations

import hashlib
import re

from core.models import AIQuestionGenerationCache


def normalize_text(value: str) -> str:
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip().lower()


def make_input_hash(title: str, problem_statement: str) -> str:
    payload = f"{normalize_text(title)}\n{normalize_text(problem_statement)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_cached(input_hash: str) -> dict | None:
    row = AIQuestionGenerationCache.objects.filter(input_hash=input_hash).first()
    if not row:
        return None
    data = row.generated_response
    return data if isinstance(data, dict) else None


def store_cached(input_hash: str, title: str, problem_statement: str, data: dict) -> None:
    AIQuestionGenerationCache.objects.update_or_create(
        input_hash=input_hash,
        defaults={
            "problem_title": (title or "")[:255],
            "problem_statement": problem_statement or "",
            "generated_response": data,
        },
    )
