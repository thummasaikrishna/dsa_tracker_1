"""Trusted-output Oracle backed exclusively by the configured sandbox executor."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .executor import ExecutorUnavailable, execute_once, normalize_output
from .models import Question, TestCase


class ReferenceSolutionNotVerified(Exception):
    """Raised when an operation would use untrusted reference code."""


@dataclass(frozen=True)
class OracleResult:
    ok: bool
    output: str = ""
    reason: str = ""


_SAFE_FAILURES = {
    "compilation_error": "Reference solution did not compile.",
    "runtime_error": "Reference solution failed while running.",
    "time_limit_exceeded": "Reference solution exceeded the execution time limit.",
}


def _manual_examples(question: Question) -> list[tuple[str, str]]:
    """Extract only unambiguous, admin-authored Input/Output example pairs.

    Examples remain display content; this merely lets a trusted reference
    solution be checked against the same stated stdin/stdout contract.
    """
    text = question.examples or ""
    pattern = re.compile(
        r"(?:^|\n)\s*Input:\s*\n?(?P<input>[\s\S]*?)\n\s*Output:\s*\n?(?P<output>[\s\S]*?)(?=\n\s*(?:Explanation:|Example\s+\d+\s*:|Input:)|\Z)",
        re.IGNORECASE,
    )
    return [
        (match.group("input").strip(), normalize_output(match.group("output")))
        for match in pattern.finditer(text)
        if match.group("input").strip() and match.group("output").strip()
    ]


def _safe_failure(raw: dict) -> str:
    return _SAFE_FAILURES.get(raw.get("kind"), "Reference solution validation failed.")


def _matches_case(case: TestCase, actual: str) -> bool:
    if case.validation_type == TestCase.VALIDATION_CUSTOM:
        from .validators import get_validator

        validator = get_validator(case.validator_type)
        return bool(validator and validator.is_valid(case.input_data, actual, case.expected_output))
    return actual == normalize_output(case.expected_output)


def _record_validation(question: Question, status: str, error: str = "") -> None:
    question.reference_solution_status = status
    question.reference_solution_error = error
    question._reference_validation_in_progress = True
    try:
        question.save(update_fields=["reference_solution_status", "reference_solution_error"])
    finally:
        del question._reference_validation_in_progress


def validate_reference_solution(question: Question) -> OracleResult:
    """Validate using only the sandbox and already-verified human test cases.

    No AI expected output and no student submission is consulted here.
    """
    if not (question.reference_solution or "").strip():
        reason = "Reference solution is required."
        _record_validation(question, Question.REFERENCE_SOLUTION_FAILED, reason)
        return OracleResult(False, reason=reason)

    cases = list(
        question.test_cases.filter(verification_status=TestCase.VERIFICATION_VERIFIED).order_by("order", "id")
    )
    examples = _manual_examples(question) if not cases else []
    if not cases and not examples:
        reason = "Add a verified testcase or a labeled Input/Output example before validating the reference solution."
        _record_validation(question, Question.REFERENCE_SOLUTION_FAILED, reason)
        return OracleResult(False, reason=reason)

    inputs = [case.input_data for case in cases] or [item[0] for item in examples]
    for index, stdin in enumerate(inputs):
        try:
            raw = execute_once(question.reference_solution, question.reference_solution_language, stdin)
        except ExecutorUnavailable:
            reason = "Sandbox executor is unavailable."
            _record_validation(question, Question.REFERENCE_SOLUTION_FAILED, reason)
            return OracleResult(False, reason=reason)
        if raw.get("kind") != "ok":
            reason = _safe_failure(raw)
            _record_validation(question, Question.REFERENCE_SOLUTION_FAILED, reason)
            return OracleResult(False, reason=reason)
        actual = normalize_output(raw.get("stdout") or "")
        expected = normalize_output(cases[index].expected_output) if cases else examples[index][1]
        matches = _matches_case(cases[index], actual) if cases else actual == expected
        if not matches:
            reason = "Reference solution does not match a verified test case."
            _record_validation(question, Question.REFERENCE_SOLUTION_FAILED, reason)
            return OracleResult(False, reason=reason)

    _record_validation(question, Question.REFERENCE_SOLUTION_VERIFIED)
    return OracleResult(True)


def generate_expected_output(question: Question, input_data: str) -> str:
    """Run a verified reference solution and return judge-normalized stdout."""
    if question.reference_solution_status != Question.REFERENCE_SOLUTION_VERIFIED:
        raise ReferenceSolutionNotVerified("Reference solution not verified.")
    try:
        raw = execute_once(question.reference_solution, question.reference_solution_language, input_data)
    except ExecutorUnavailable as exc:
        raise ReferenceSolutionNotVerified("Sandbox executor is unavailable.") from exc
    if raw.get("kind") != "ok":
        raise ReferenceSolutionNotVerified(_safe_failure(raw))
    return normalize_output(raw.get("stdout") or "")


def populate_testcase_expected_output(test_case: TestCase) -> TestCase:
    """Populate a candidate's expected output; never read candidate AI output."""
    test_case.expected_output = generate_expected_output(test_case.question, test_case.input_data)
    test_case.verification_status = TestCase.VERIFICATION_VERIFIED
    test_case.verification_reason = "Generated by verified reference solution."
    test_case.save(update_fields=["expected_output", "verification_status", "verification_reason"])
    return test_case
