class BaseValidator:
    """Deterministic custom checker for problems with more than one valid output."""

    name = ""

    def is_valid(self, stdin: str, stdout: str, expected_output: str | None) -> bool:
        raise NotImplementedError
