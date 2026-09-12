from __future__ import annotations

from .cache import get_cached, make_input_hash, store_cached
from .constraint_validator import validate_generated_candidates
from .fallback_manager import run_with_fallback
from .response_validator import ValidationError, validate_payload


class AIGenerationUnavailable(Exception):
    default_message = "AI generation is temporarily unavailable. Please try again later."


def generate_question_data(title: str, problem_statement: str) -> tuple[dict, bool]:
    title = (title or "").strip()
    problem_statement = (problem_statement or "").strip()
    if not problem_statement:
        raise ValueError("problem_statement is required")

    input_hash = make_input_hash(title, problem_statement)
    cached = get_cached(input_hash)
    if cached:
        try:
            validated = validate_payload(cached)
            return validate_generated_candidates(validated, title, problem_statement), True
        except ValidationError:
            pass

    try:
        data = run_with_fallback(title, problem_statement)
    except RuntimeError as exc:
        raise AIGenerationUnavailable() from exc

    data = validate_generated_candidates(data, title, problem_statement)
    # Candidate inputs are structurally and constraint validated, but are not
    # executed, verified, or converted into judge expected outputs here.
    store_cached(input_hash, title, problem_statement, data)
    return data, False
