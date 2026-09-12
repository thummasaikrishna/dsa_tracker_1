"""Validation of AI-generated stdin candidates against explicit problem constraints.

The specification is intentionally ephemeral: it is derived from the problem
statement for the generation request and is never saved on a Question or used
by the judge.  This keeps Phase 2 isolated from manual testcase authoring.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

STATUS_READY = "READY"
STATUS_UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ConstraintResult:
    valid: bool
    errors: list[str]
    status: str = STATUS_READY


def normalize_candidate_input(value: str) -> str:
    """Normalize only whitespace, which is insignificant for stdin tokens."""
    return " ".join((value or "").replace("\r\n", "\n").replace("\r", "\n").split())


def _number(value: str) -> int | None:
    value = value.replace(" ", "")
    match = re.fullmatch(r"(-?\d+)(?:\^(\d+))?", value)
    if not match:
        return None
    base = int(match.group(1))
    return base ** int(match.group(2)) if match.group(2) else base


def _ranges(statement: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    pattern = re.compile(
        r"(?P<low>-?\d+(?:\s*\^\s*\d+)?)\s*<=\s*"
        r"(?P<name>[a-zA-Z][\w]*(?:\s*\[[^\]]+\])?)\s*<=\s*"
        r"(?P<high>-?\d+(?:\s*\^\s*\d+)?|[a-zA-Z][\w]*)",
        re.IGNORECASE,
    )
    for match in pattern.finditer(statement):
        raw_name = match.group("name").replace(" ", "")
        name = raw_name.split("[")[0].lower()
        low = _number(match.group("low"))
        high_text = match.group("high")
        high = _number(high_text)
        result[name] = {"min": low, "max": high, "max_ref": None if high is not None else high_text.lower()}
    return result


def _scalar(name: str, ranges: dict[str, dict[str, Any]]) -> dict[str, Any]:
    bounds = ranges.get(name.lower(), {})
    return {"name": name, "type": "integer", "min": bounds.get("min"), "max": bounds.get("max")}


def _array(name: str, length_ref: str, ranges: dict[str, dict[str, Any]]) -> dict[str, Any]:
    bounds = ranges.get(name.lower(), {})
    return {
        "name": name,
        "type": "array",
        "length_ref": length_ref,
        "element_type": "integer",
        "element_min": bounds.get("min"),
        "element_max": bounds.get("max"),
    }


def parse_problem_constraints(title: str, problem_statement: str) -> dict[str, Any]:
    """Build specs for the supported, explicit DSA input formats.

    Text that does not describe a known structure deliberately returns UNKNOWN;
    accepting it would make a prompt instruction masquerade as validation.
    """
    text = problem_statement or ""
    lower = text.lower()
    title_lower = (title or "").lower()
    ranges = _ranges(text)
    rules: list[str] = []
    if "sorted" in lower:
        rules.append("array_sorted")
    if re.search(r"\b(all\s+)?(?:values?|elements?)\s+(?:are\s+)?(?:distinct|unique)\b", lower):
        rules.append("array_distinct")
    if re.search(r"no\s+(?:two\s+)?adjacent\s+(?:cells?|elements?)\s+(?:are\s+)?equal", lower):
        rules.append("matrix_no_adjacent_equal")
    if re.search(r"(?:only|contains?)\s+(?:0\s+and\s+1|binary)", lower):
        rules.append("matrix_binary")

    def scalar_names(*names: str) -> list[dict[str, Any]]:
        return [_scalar(name, ranges) for name in names]

    # These formats reflect the stdin representations requested by the agent
    # prompt, not a new execution format.
    if "binary search" in title_lower:
        return {
            "status": STATUS_READY,
            "fields": [*scalar_names("n"), _array("arr", "n", ranges), *scalar_names("target")],
            "relations": [],
            "rules": rules,
            # Support the judge's canonical two-line contract (`n target`,
            # then the n array values) while retaining previously saved
            # legacy token ordering (`n`, array, `target`).
            "input_format": "binary_search",
        }
    if "two sum" in title_lower:
        return {
            "status": STATUS_READY,
            "fields": [*scalar_names("n"), _array("nums", "n", ranges), *scalar_names("target")],
            "relations": [],
            "rules": rules,
        }
    if "maximum subarray" in title_lower:
        return {
            "status": STATUS_READY,
            "fields": [*scalar_names("n"), _array("nums", "n", ranges)],
            "relations": [],
            "rules": rules,
        }
    if "rotate array" in title_lower:
        relations = [("k", "<=", "n")] if re.search(r"\bk\s*<=\s*n\b", lower) else []
        return {
            "status": STATUS_READY,
            "fields": [*scalar_names("n"), _array("nums", "n", ranges), *scalar_names("k")],
            "relations": relations,
            "rules": rules,
        }
    if "peak" in title_lower and ("2d" in title_lower or "matrix" in lower):
        return {
            "status": STATUS_READY,
            "fields": [
                *scalar_names("n", "m"),
                {
                    "name": "matrix",
                    "type": "matrix",
                    "rows_ref": "n",
                    "cols_ref": "m",
                    "element_type": "integer",
                    "element_min": ranges.get("matrix", {}).get("min"),
                    "element_max": ranges.get("matrix", {}).get("max"),
                },
            ],
            "relations": [],
            "rules": rules,
        }
    return {"status": STATUS_UNKNOWN, "fields": [], "relations": [], "rules": []}


class ConstraintValidator:
    """A modular validator for scalar, array, string, matrix, and relation specs."""

    def validate(self, candidate_input: str, specification: dict[str, Any]) -> ConstraintResult:
        if specification.get("status") != STATUS_READY:
            return ConstraintResult(False, ["constraint_status_unknown"], STATUS_UNKNOWN)
        if not isinstance(candidate_input, str) or not candidate_input.strip():
            return ConstraintResult(False, ["input_required"])

        if specification.get("input_format") == "binary_search":
            return self._validate_binary_search(candidate_input, specification)

        tokens = candidate_input.split()
        lines = [line.split() for line in candidate_input.strip().splitlines()]
        index = 0
        values: dict[str, Any] = {}
        errors: list[str] = []

        def next_integer(name: str, minimum=None, maximum=None) -> int | None:
            nonlocal index
            if index >= len(tokens):
                errors.append(f"{name}_missing")
                return None
            token = tokens[index]
            index += 1
            try:
                value = int(token)
            except ValueError:
                errors.append(f"{name}_must_be_integer")
                return None
            if minimum is not None and value < minimum:
                errors.append(f"{name}_below_min")
            if maximum is not None and value > maximum:
                errors.append(f"{name}_above_max")
            return value

        for field in specification.get("fields", []):
            name = field.get("name", "input")
            field_type = field.get("type")
            if field_type == "integer":
                values[name] = next_integer(name, field.get("min"), field.get("max"))
            elif field_type == "array":
                length = values.get(field.get("length_ref"))
                if not isinstance(length, int) or length < 0:
                    errors.append(f"{name}_invalid_length_reference")
                    continue
                values[name] = [
                    next_integer(name, field.get("element_min"), field.get("element_max"))
                    for _ in range(length)
                ]
                if field.get("non_empty") and not values[name]:
                    errors.append(f"{name}_empty")
            elif field_type == "matrix":
                rows = values.get(field.get("rows_ref"))
                cols = values.get(field.get("cols_ref"))
                if not isinstance(rows, int) or not isinstance(cols, int) or rows < 0 or cols < 0:
                    errors.append(f"{name}_invalid_dimensions")
                    continue
                matrix = []
                for _ in range(rows):
                    matrix.append([
                        next_integer(name, field.get("element_min"), field.get("element_max"))
                        for _ in range(cols)
                    ])
                values[name] = matrix
                if len(matrix) != rows or any(len(row) != cols for row in matrix):
                    errors.append(f"{name}_invalid_dimensions")
                # Matrix stdin uses a header line followed by one row per
                # line. Token counts alone would incorrectly accept a ragged
                # matrix such as `1` / `2 3 4` for a 2x2 input.
                header_width = sum(1 for prior in specification.get("fields", []) if prior is not field and prior.get("type") == "integer")
                matrix_lines = lines[1:] if lines and len(lines[0]) == header_width else []
                if len(matrix_lines) != rows or any(len(row) != cols for row in matrix_lines):
                    errors.append(f"{name}_non_rectangular")
            elif field_type == "string":
                if index >= len(tokens):
                    errors.append(f"{name}_missing")
                    continue
                value = tokens[index]
                index += 1
                values[name] = value
                if field.get("required", True) and not value:
                    errors.append(f"{name}_empty")
                if field.get("min_length") is not None and len(value) < field["min_length"]:
                    errors.append(f"{name}_too_short")
                if field.get("max_length") is not None and len(value) > field["max_length"]:
                    errors.append(f"{name}_too_long")
                allowed = field.get("allowed_pattern")
                if allowed and not re.fullmatch(allowed, value):
                    errors.append(f"{name}_invalid_characters")
            else:
                errors.append(f"{name}_unsupported_type")

        if index != len(tokens):
            errors.append("unexpected_input_tokens")
        for left, operator, right in specification.get("relations", []):
            left_value, right_value = values.get(left), values.get(right)
            if not isinstance(left_value, int) or not isinstance(right_value, int):
                errors.append(f"relation_{left}_{operator}_{right}_unavailable")
            elif operator == "<=" and left_value > right_value:
                errors.append(f"relation_{left}_le_{right}")
            elif operator == "<" and left_value >= right_value:
                errors.append(f"relation_{left}_lt_{right}")

        matrix = next((value for value in values.values() if isinstance(value, list) and value and isinstance(value[0], list)), None)
        array = next((value for value in values.values() if isinstance(value, list) and (not value or not isinstance(value[0], list))), None)
        rules = set(specification.get("rules", []))
        if "array_sorted" in rules and array is not None and any(array[i] > array[i + 1] for i in range(len(array) - 1)):
            errors.append("array_not_sorted")
        if "array_distinct" in rules and array is not None and len(set(array)) != len(array):
            errors.append("array_not_distinct")
        if matrix is not None:
            if "matrix_binary" in rules and any(value not in (0, 1) for row in matrix for value in row):
                errors.append("matrix_not_binary")
            if "matrix_no_adjacent_equal" in rules:
                for row_index, row in enumerate(matrix):
                    for col_index, value in enumerate(row):
                        if (row_index + 1 < len(matrix) and matrix[row_index + 1][col_index] == value) or (
                            col_index + 1 < len(row) and row[col_index + 1] == value
                        ):
                            errors.append("matrix_adjacent_values_equal")
                            break
                    if "matrix_adjacent_values_equal" in errors:
                        break
        return ConstraintResult(not errors, errors)

    def _validate_binary_search(self, candidate_input: str, specification: dict[str, Any]) -> ConstraintResult:
        """Validate both supported Binary Search stdin layouts without rewriting it."""
        lines = [line.split() for line in candidate_input.strip().splitlines() if line.strip()]
        fields = {field["name"]: field for field in specification.get("fields", [])}
        errors: list[str] = []
        try:
            # Canonical judge/reference contract: first line is `n target`,
            # second line contains exactly n array integers.
            if len(lines) == 2 and len(lines[0]) == 2:
                n, target = (int(value) for value in lines[0])
                arr = [int(value) for value in lines[1]]
            else:
                # Backward compatible legacy contract: n, n array values, target.
                tokens = [int(value) for line in lines for value in line]
                n = tokens[0]
                arr = tokens[1 : 1 + n]
                target = tokens[1 + n] if len(tokens) > 1 + n else None
        except (ValueError, IndexError):
            return ConstraintResult(False, ["invalid_integer_input"])

        bounds = fields.get("n", {})
        if bounds.get("min") is not None and n < bounds["min"]:
            errors.append("n_below_min")
        if bounds.get("max") is not None and n > bounds["max"]:
            errors.append("n_above_max")
        if len(arr) != n:
            errors.append("arr_length_mismatch")
        if target is None:
            errors.append("target_missing")
        if "array_sorted" in set(specification.get("rules", [])) and any(
            arr[index] > arr[index + 1] for index in range(len(arr) - 1)
        ):
            errors.append("array_not_sorted")
        if "array_distinct" in set(specification.get("rules", [])) and len(set(arr)) != len(arr):
            errors.append("array_not_distinct")
        return ConstraintResult(not errors, errors)


def validate_generated_candidates(payload: dict, title: str, problem_statement: str) -> dict:
    """Filter invalid AI candidates without ever changing their input values."""
    specification = parse_problem_constraints(title, problem_statement)
    # Not every valid DSA problem has a recognisable input grammar.  Keep its
    # complete AI cases rather than silently deleting all six testcases.
    if specification.get("status") == STATUS_UNKNOWN:
        return payload
    validator = ConstraintValidator()
    seen: set[str] = set()
    for bucket in ("public_test_cases", "hidden_test_cases"):
        accepted = []
        for case in payload.get(bucket, []):
            raw_input = case.get("input", "")
            normalized = normalize_candidate_input(raw_input)
            if normalized in seen:
                logger.warning("AI testcase rejected (duplicate_input)")
                continue
            seen.add(normalized)
            result = validator.validate(raw_input, specification)
            if result.valid:
                accepted.append(case)
                logger.info("AI testcase validation passed (%s)", bucket)
            else:
                logger.warning("AI testcase rejected (%s)", ",".join(result.errors))
        payload[bucket] = accepted
    return payload
