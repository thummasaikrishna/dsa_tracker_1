from __future__ import annotations

import json
import re

from .schemas import (
    DIFFICULTIES,
    EXAMPLE_RANGE,
    HIDDEN_TEST_RANGE,
    MAX_FIELD_CHARS,
    MAX_HIDDEN_INPUT_CHARS,
    PUBLIC_TEST_RANGE,
)


class ValidationError(Exception):
    pass


def extract_json(text: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        raise ValidationError("empty")
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.IGNORECASE)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise ValidationError("invalid_json")
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValidationError("invalid_json") from exc
    if not isinstance(data, dict):
        raise ValidationError("invalid_json")
    return data


def _as_text(value, allow_null=False) -> str | None:
    if value is None:
        if allow_null:
            return None
        raise ValidationError("missing_field")
    if not isinstance(value, (str, int, float)):
        raise ValidationError("bad_field_type")
    text = str(value)
    if len(text) > MAX_FIELD_CHARS and len(text) > MAX_HIDDEN_INPUT_CHARS:
        raise ValidationError("field_too_large")
    return text


def _validate_example(item) -> dict:
    if not isinstance(item, dict):
        raise ValidationError("bad_example")
    inp = _as_text(item.get("input"))
    out = _as_text(item.get("output"))
    expl = _as_text(item.get("explanation"))
    if not (inp and out and expl and expl.strip()):
        raise ValidationError("bad_example")
    return {"input": inp, "output": out, "explanation": expl.strip()}


def _validate_test(item, *, hidden: bool) -> dict:
    if not isinstance(item, dict):
        raise ValidationError("bad_test_case")
    inp = _as_text(item.get("input"))
    output = _as_text(item.get("output"))
    if inp is None or not inp.strip() or output is None or not output.strip():
        raise ValidationError("bad_test_case")
    limit = MAX_HIDDEN_INPUT_CHARS if hidden else MAX_FIELD_CHARS
    if len(inp) > limit:
        raise ValidationError("field_too_large")

    return {
        "input": inp,
        "output": output,
    }


def validate_payload(data: dict) -> dict:
    difficulty_raw = str(data.get("difficulty") or "").strip()
    difficulty_map = {d.lower(): d for d in DIFFICULTIES}
    difficulty = difficulty_map.get(difficulty_raw.lower())
    if not difficulty:
        raise ValidationError("bad_difficulty")

    prereq_raw = data.get("prerequisites")
    if not isinstance(prereq_raw, list) or not prereq_raw:
        raise ValidationError("bad_prerequisites")
    prerequisites = []
    for item in prereq_raw:
        text = str(item).strip()
        if text:
            prerequisites.append(text[:200])
    if not prerequisites:
        raise ValidationError("bad_prerequisites")

    examples_raw = data.get("examples")
    if not isinstance(examples_raw, list):
        raise ValidationError("bad_examples")
    lo, hi = EXAMPLE_RANGE
    if not (lo <= len(examples_raw) <= hi):
        raise ValidationError("bad_examples")
    examples = [_validate_example(item) for item in examples_raw]

    public_raw = data.get("public_test_cases")
    hidden_raw = data.get("hidden_test_cases")
    if not isinstance(public_raw, list) or not isinstance(hidden_raw, list):
        raise ValidationError("bad_test_case")
    plo, phi = PUBLIC_TEST_RANGE
    hlo, hhi = HIDDEN_TEST_RANGE
    if not (plo <= len(public_raw) <= phi):
        raise ValidationError("bad_public_tests")
    if not (hlo <= len(hidden_raw) <= hhi):
        raise ValidationError("bad_hidden_tests")

    public_tests = [_validate_test(item, hidden=False) for item in public_raw]
    hidden_tests = [_validate_test(item, hidden=True) for item in hidden_raw]
    all_inputs = [case["input"] for case in public_tests + hidden_tests]
    if len(set(all_inputs)) != len(all_inputs):
        raise ValidationError("duplicate_test_input")

    payload = {
        "difficulty": difficulty,
        "prerequisites": prerequisites,
        "examples": examples,
        "public_test_cases": public_tests,
        "hidden_test_cases": hidden_tests,
    }
    return payload
