"""
2D peak checker (LeetCode-style Peak Element II).

A cell is a peak if it is strictly greater than existing neighbors
(up, down, left, right). Student output may be:
  - two integers: row col (0-indexed preferred; 1-indexed accepted if in range)
  - one integer: the peak value (must appear at some peak cell)
"""

from __future__ import annotations

import re

from .base import BaseValidator


def _parse_ints(text: str) -> list[int]:
    return [int(tok) for tok in re.findall(r"-?\d+", text or "")]


def parse_matrix(stdin: str) -> list[list[int]]:
    lines = [ln.strip() for ln in (stdin or "").splitlines() if ln.strip()]
    if not lines:
        return []
    header = _parse_ints(lines[0])
    rows: list[list[int]] = []
    if len(header) >= 2 and header[0] > 0 and header[1] > 0:
        n, m = header[0], header[1]
        for line in lines[1 : 1 + n]:
            vals = _parse_ints(line)
            if len(vals) >= m:
                rows.append(vals[:m])
        if len(rows) == n:
            return rows
    for line in lines:
        vals = _parse_ints(line)
        if vals:
            rows.append(vals)
    if rows and all(len(r) == len(rows[0]) for r in rows):
        return rows
    return []


def is_peak(matrix: list[list[int]], r: int, c: int) -> bool:
    if not matrix or r < 0 or c < 0 or r >= len(matrix) or c >= len(matrix[0]):
        return False
    val = matrix[r][c]
    n, m = len(matrix), len(matrix[0])
    neighbors = []
    if r > 0:
        neighbors.append(matrix[r - 1][c])
    if r + 1 < n:
        neighbors.append(matrix[r + 1][c])
    if c > 0:
        neighbors.append(matrix[r][c - 1])
    if c + 1 < m:
        neighbors.append(matrix[r][c + 1])
    return all(val > nb for nb in neighbors)


class Peak2DValidator(BaseValidator):
    name = "PEAK_2D"

    def is_valid(self, stdin: str, stdout: str, expected_output: str | None) -> bool:
        matrix = parse_matrix(stdin)
        if not matrix:
            return False
        nums = _parse_ints(stdout)
        n, m = len(matrix), len(matrix[0])
        if len(nums) >= 2:
            r, c = nums[0], nums[1]
            if is_peak(matrix, r, c):
                return True
            if is_peak(matrix, r - 1, c - 1):
                return True
            return False
        if len(nums) == 1:
            target = nums[0]
            for i in range(n):
                for j in range(m):
                    if matrix[i][j] == target and is_peak(matrix, i, j):
                        return True
            return False
        return False
