from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.agents.openrouter_client import OpenRouterError
from core.agents.response_validator import ValidationError, extract_json, validate_payload
from core.executor import evaluate_cases
from core.models import AIQuestionGenerationCache, Question
from core.models import TestCase as QuestionTestCase
from core.validators.peak_2d import Peak2DValidator

AI_URL = "/api/admin/ai/generate-question-data/"

VALID_AI = {
    "difficulty": "Medium",
    "prerequisites": ["Arrays", "2D Arrays / Matrices", "Binary Search"],
    "examples": [
        {"input": "3 3\n1 2 3\n4 5 6\n7 8 9", "output": "0 2", "explanation": "3 is a peak in the first row."},
        {"input": "1 1\n7", "output": "0 0", "explanation": "A single cell is always a peak."},
    ],
    "public_test_cases": [
        {"input": "1 1\n1", "output": "0 0"},
        {"input": "2 2\n1 2\n3 4", "output": "1 1"},
    ],
    "hidden_test_cases": [
        {"input": "3 3\n10 8 10\n14 13 12\n15 9 11", "output": "2 0"},
        {"input": "2 1\n1\n2", "output": "1 0"},
        {"input": "1 2\n5 4", "output": "0 0"},
        {"input": "3 1\n1\n2\n3", "output": "2 0"},
    ],
}


def _json_dump(payload):
    import json
    return json.dumps(payload)


@override_settings(
    OPENROUTER_API_KEYS=["key-a", "key-b", "key-c", "key-d", "key-e"],
    OPENROUTER_MODEL="openai/gpt-oss-20b",
)
class AIQuestionAgentTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user("adminai", password="pass12345")
        self.admin.profile.role = "admin"
        self.admin.profile.save()
        self.student = User.objects.create_user("aliceai", password="pass12345")
        self.client = APIClient()
        self.now = timezone.now()
    def test_successful_generation_primary_key(self):
        self.client.force_authenticate(self.admin)
        with patch("core.agents.fallback_manager.complete_chat", return_value=_json_dump(VALID_AI)) as mock_chat:
            res = self.client.post(
                AI_URL,
                {"title": "Peak 2D", "problem_statement": "Find any peak in a matrix."},
                format="json",
            )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["success"])
        self.assertFalse(res.data["cached"])
        self.assertEqual(res.data["data"]["difficulty"], "Medium")
        self.assertEqual(len(res.data["data"]["public_test_cases"]), 2)
        self.assertEqual(len(res.data["data"]["hidden_test_cases"]), 4)
        for bucket in ("public_test_cases", "hidden_test_cases"):
            self.assertTrue(all(set(case) == {"input", "output"} for case in res.data["data"][bucket]))
        self.assertEqual(mock_chat.call_count, 1)
        self.assertEqual(mock_chat.call_args[0][0], "key-a")
        self.assertEqual(mock_chat.call_args[0][1], "openai/gpt-oss-20b")

    def test_key1_failure_key2_succeeds(self):
        self.client.force_authenticate(self.admin)

        def side_effect(api_key, model, system_prompt, user_prompt):
            if api_key == "key-a":
                raise OpenRouterError("http_429")
            return _json_dump(VALID_AI)

        with patch("core.agents.fallback_manager.complete_chat", side_effect=side_effect) as mock_chat:
            res = self.client.post(
                AI_URL,
                {"title": "Peak 2D", "problem_statement": "Find a peak. Constraints: 1 <= n <= 100."},
                format="json",
            )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["success"])
        self.assertEqual(mock_chat.call_count, 2)
        self.assertEqual(mock_chat.call_args_list[1][0][0], "key-b")

    def test_key1_timeout_uses_key2(self):
        self.client.force_authenticate(self.admin)
        with patch(
            "core.agents.fallback_manager.complete_chat",
            side_effect=[OpenRouterError("timeout"), _json_dump(VALID_AI)],
        ) as mock_chat:
            res = self.client.post(AI_URL, {"title": "Peak", "problem_statement": "Find peak."}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(mock_chat.call_args_list[1][0][0], "key-b")

    def test_key1_forbidden_uses_key2(self):
        self.client.force_authenticate(self.admin)
        with patch(
            "core.agents.fallback_manager.complete_chat",
            side_effect=[OpenRouterError("http_403"), _json_dump(VALID_AI)],
        ) as mock_chat:
            res = self.client.post(AI_URL, {"title": "Peak", "problem_statement": "Find peak."}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(mock_chat.call_args_list[1][0][0], "key-b")

    def test_key1_network_error_uses_key2(self):
        self.client.force_authenticate(self.admin)
        with patch(
            "core.agents.fallback_manager.complete_chat",
            side_effect=[OpenRouterError("network"), _json_dump(VALID_AI)],
        ) as mock_chat:
            res = self.client.post(AI_URL, {"title": "Peak", "problem_statement": "Find peak."}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(mock_chat.call_args_list[1][0][0], "key-b")

    def test_invalid_json_uses_fallback(self):
        self.client.force_authenticate(self.admin)

        def side_effect(api_key, model, system_prompt, user_prompt):
            if api_key == "key-a":
                return "not json at all"
            return _json_dump(VALID_AI)

        with patch("core.agents.fallback_manager.complete_chat", side_effect=side_effect):
            res = self.client.post(
                AI_URL,
                {"title": "Peak", "problem_statement": "Find peak element."},
                format="json",
            )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["success"])

    def test_invalid_schema_uses_fallback(self):
        self.client.force_authenticate(self.admin)
        bad = {**VALID_AI, "difficulty": "Insane"}

        def side_effect(api_key, model, system_prompt, user_prompt):
            if api_key == "key-a":
                return _json_dump(bad)
            return _json_dump(VALID_AI)

        with patch("core.agents.fallback_manager.complete_chat", side_effect=side_effect):
            res = self.client.post(
                AI_URL,
                {"title": "Peak", "problem_statement": "A matrix peak problem."},
                format="json",
            )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["data"]["difficulty"], "Medium")

    def test_all_fallback_attempts_fail(self):
        self.client.force_authenticate(self.admin)
        with patch("core.agents.fallback_manager.complete_chat", side_effect=OpenRouterError("http_429")):
            res = self.client.post(
                AI_URL,
                {"title": "Peak", "problem_statement": "Find peak."},
                format="json",
            )
        self.assertEqual(res.status_code, 503)
        self.assertFalse(res.data["success"])
        self.assertIn("temporarily unavailable", res.data["message"].lower())
        self.assertNotIn("key-a", str(res.data))
        self.assertEqual(AIQuestionGenerationCache.objects.count(), 0)

    def test_same_problem_returns_cache(self):
        self.client.force_authenticate(self.admin)
        body = {"title": "Peak 2D", "problem_statement": "Find any peak in a 2D matrix."}
        with patch("core.agents.fallback_manager.complete_chat", return_value=_json_dump(VALID_AI)) as mock_chat:
            first = self.client.post(AI_URL, body, format="json")
            second = self.client.post(AI_URL, body, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.data["cached"])
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.data["cached"])
        self.assertEqual(mock_chat.call_count, 1)

    def test_different_problem_generates_again(self):
        self.client.force_authenticate(self.admin)
        with patch("core.agents.fallback_manager.complete_chat", return_value=_json_dump(VALID_AI)) as mock_chat:
            self.client.post(AI_URL, {"title": "A", "problem_statement": "Problem one."}, format="json")
            self.client.post(AI_URL, {"title": "B", "problem_statement": "Problem two."}, format="json")
        self.assertEqual(mock_chat.call_count, 2)

    def test_non_admin_cannot_call(self):
        self.client.force_authenticate(self.student)
        res = self.client.post(
            AI_URL,
            {"title": "Peak", "problem_statement": "Find peak."},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_unauthenticated_cannot_call(self):
        res = self.client.post(AI_URL, {"title": "Peak", "problem_statement": "Find peak."}, format="json")
        self.assertEqual(res.status_code, 401)

    def test_hidden_cases_never_in_student_api(self):
        question = Question.objects.create(
            title="Peak",
            difficulty="medium",
            created_by=self.admin,
            deadline=self.now + timedelta(days=2),
        )
        QuestionTestCase.objects.create(
            question=question,
            input_data="public\n",
            expected_output="1",
            is_hidden=False,
            order=0,
        )
        QuestionTestCase.objects.create(
            question=question,
            input_data="SECRET_HIDDEN",
            expected_output="9",
            is_hidden=True,
            order=1,
            validation_type="CUSTOM_VALIDATOR",
            validator_type="PEAK_2D",
        )
        self.client.force_authenticate(self.student)
        res = self.client.get(f"/api/questions/{question.id}/")
        self.assertEqual(res.status_code, 200)
        blob = str(res.data)
        self.assertNotIn("SECRET_HIDDEN", blob)
        self.assertNotIn("PEAK_2D", blob)
        self.assertEqual(len(res.data["test_cases"]), 1)
        self.assertNotIn("hidden_test_count", res.data)

    def test_existing_add_question_still_works(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/questions/",
            {
                "title": "Two Sum",
                "description": "Find two numbers.",
                "examples": "Input 1\nOutput 0 1",
                "prerequisites": "Arrays",
                "difficulty": "easy",
                "deadline": (self.now + timedelta(days=5)).isoformat(),
                "test_cases": [
                    {"input_data": "1\n", "expected_output": "1", "is_hidden": False, "order": 0, "verification_status": "VERIFIED"},
                    {"input_data": "2\n", "expected_output": "2", "is_hidden": True, "order": 1, "verification_status": "VERIFIED"},
                ],
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        q = Question.objects.get(title="Two Sum")
        self.assertEqual(q.test_cases.count(), 2)

    def test_generated_payload_can_be_edited_before_save(self):
        self.client.force_authenticate(self.admin)
        with patch("core.agents.fallback_manager.complete_chat", return_value=_json_dump(VALID_AI)):
            generated = self.client.post(
                AI_URL,
                {"title": "Peak 2D", "problem_statement": "Input is n m followed by an n by m matrix."},
                format="json",
            ).data["data"]
        generated["prerequisites"].append("Edited by admin")
        generated["difficulty"] = "Hard"
        res = self.client.post(
            "/api/questions/",
            {
                "title": "Peak edited",
                "description": "Find any peak.",
                "examples": "admin edited examples",
                "prerequisites": "\n".join(generated["prerequisites"]),
                "difficulty": generated["difficulty"].lower(),
                "deadline": (self.now + timedelta(days=5)).isoformat(),
                "test_cases": [
                    {
                        "input_data": generated["public_test_cases"][0]["input"],
                        "expected_output": "0 0",
                        "is_hidden": False,
                        "order": 0,
                        "verification_status": "VERIFIED",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        q = Question.objects.get(title="Peak edited")
        self.assertEqual(q.difficulty, "hard")
        self.assertIn("Edited by admin", q.prerequisites)
        self.assertEqual(q.examples, "admin edited examples")

    def test_custom_validator_still_works_with_judge(self):
        question = Question.objects.create(
            title="Peak",
            difficulty="medium",
            created_by=self.admin,
            deadline=self.now + timedelta(days=2),
        )
        case = QuestionTestCase.objects.create(
            question=question,
            input_data="3 3\n1 4 3\n2 5 6\n7 8 9",
            expected_output="",
            is_hidden=False,
            validation_type="CUSTOM_VALIDATOR",
            validator_type="PEAK_2D",
            order=0,
        )
        with patch(
            "core.executor.execute_once",
            return_value={
                "kind": "ok",
                "stdout": "2 2",
                "stderr": "",
                "compile_output": "",
                "time": 0.01,
                "memory": None,
            },
        ):
            outcome = evaluate_cases("print(1)", "python", [case], reveal_io=True)
        self.assertEqual(outcome["status"], "accepted")
        self.assertEqual(outcome["tests_passed"], 1)

    def test_exact_match_judge_unchanged(self):
        question = Question.objects.create(
            title="Echo",
            difficulty="easy",
            created_by=self.admin,
            deadline=self.now + timedelta(days=2),
        )
        case = QuestionTestCase.objects.create(
            question=question,
            input_data="1\n",
            expected_output="1",
            is_hidden=False,
            order=0,
        )
        with patch(
            "core.executor.execute_once",
            return_value={
                "kind": "ok",
                "stdout": "1\n",
                "stderr": "",
                "compile_output": "",
                "time": 0.01,
                "memory": None,
            },
        ):
            outcome = evaluate_cases("print(1)", "python", [case], reveal_io=True)
        self.assertEqual(outcome["status"], "accepted")

    def test_validator_rejects_non_peak(self):
        validator = Peak2DValidator()
        stdin = "3 3\n1 2 3\n4 5 6\n7 8 9"
        self.assertTrue(validator.is_valid(stdin, "2 2", None))
        self.assertFalse(validator.is_valid(stdin, "0 0", None))

    def test_extract_json_from_fences(self):
        payload = extract_json("```json\n" + _json_dump(VALID_AI) + "\n```")
        validated = validate_payload(payload)
        self.assertEqual(validated["difficulty"], "Medium")

    def test_schema_rejects_bad_difficulty(self):
        with self.assertRaises(ValidationError):
            validate_payload({**VALID_AI, "difficulty": "Legendary"})

    def test_ai_expected_outputs_are_required_and_returned(self):
        payload = {
            **VALID_AI,
            "public_test_cases": [
                {**case, "output": "WRONG", "validation_type": "EXACT_MATCH"}
                for case in VALID_AI["public_test_cases"]
            ],
            "hidden_test_cases": [
                {**case, "output": "WRONG"}
                for case in VALID_AI["hidden_test_cases"]
            ],
        }
        self.client.force_authenticate(self.admin)
        with patch("core.agents.fallback_manager.complete_chat", return_value=_json_dump(payload)):
            response = self.client.post(
                AI_URL,
                {"title": "Input-only tests", "problem_statement": "Generate valid candidate inputs."},
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        for bucket in ("public_test_cases", "hidden_test_cases"):
            self.assertTrue(all(set(case) == {"input", "output"} for case in response.data["data"][bucket]))
            self.assertIn("WRONG", str(response.data["data"][bucket]))
        cached = AIQuestionGenerationCache.objects.get()
        self.assertIn("WRONG", str(cached.generated_response))

    def test_schema_rejects_missing_test_input(self):
        invalid = {**VALID_AI, "public_test_cases": [{}, *VALID_AI["public_test_cases"][1:]]}
        with self.assertRaises(ValidationError):
            validate_payload(invalid)

    def test_schema_rejects_empty_test_input(self):
        invalid = {**VALID_AI, "public_test_cases": [{"input": "   "}, *VALID_AI["public_test_cases"][1:]]}
        with self.assertRaises(ValidationError):
            validate_payload(invalid)

    def test_schema_rejects_duplicate_test_inputs(self):
        invalid = {
            **VALID_AI,
            "hidden_test_cases": [
                {"input": VALID_AI["public_test_cases"][0]["input"]},
                *VALID_AI["hidden_test_cases"][1:],
            ],
        }
        with self.assertRaises(ValidationError):
            validate_payload(invalid)
