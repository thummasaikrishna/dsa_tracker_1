SYSTEM_PROMPT = """Return one compact JSON object for the supplied DSA problem.

Generate the difficulty, relevant prerequisites, correct examples, and test
cases. Every testcase must have exact stdin and stdout.

Rules:
- Follow explicit problem constraints.
- Do not invent constraints unless clearly marked as inferred.
- Generate candidate test inputs that match the exact stdin format students will use.
- Examples must have a short correct explanation.
- Cover normal and edge cases without large inputs.
- Calculate and include the exact expected stdout for every testcase. These
  values will be used directly by the judge, so never leave an output blank.
- Do not duplicate test inputs, including between public and hidden tests.
- Do not generate random huge inputs that would make a UI or database unusable. Use realistic but meaningful sizes.
- Do not reveal hidden tests to students in any non-JSON commentary.
- Do not return markdown.
- Do not return explanations outside JSON.
- Return valid JSON only.
- Follow the requested schema exactly.

JSON schema:
{
  "difficulty": "Easy | Medium | Hard",
  "prerequisites": ["..."],
  "examples": [
    {"input": "...", "output": "...", "explanation": "..."}
  ],
  "public_test_cases": [
    {"input": "...", "output": "..."}
  ],
  "hidden_test_cases": [
    {"input": "...", "output": "..."}
  ]
}

Generate exactly 2 examples, exactly 2 public test cases, and exactly 4 hidden test cases.
Prerequisites must be an array of relevant concept strings only.
Public tests should include a basic case, another normal case, a small edge case, and a boundary case when applicable.
Hidden tests should include min/max/boundary/edge/special-pattern cases, and cases that catch common wrong algorithms, using constraint-aware but not enormous inputs.
"""


def build_user_prompt(title: str, problem_statement: str) -> str:
    return (
        "Analyze this programming problem and return JSON only.\n\n"
        f"Problem title:\n{title.strip()}\n\n"
        f"Problem statement:\n{problem_statement.strip()}\n"
    )
