"""
Sandboxed remote code execution.

Student source is never eval()'d or run via subprocess on the Django host.
Priority:
  1. Judge0 if JUDGE0_BASE_URL is configured
  2. Self-hosted Piston if PISTON_BASE_URL is configured
  3. Wandbox (https://wandbox.org/api) as the default sandbox
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

from django.conf import settings

from .models import CodeSubmission

LANGUAGE_MAP = {
    "python": {
        "judge0_id": 71,
        "piston_language": "python",
        "piston_version": "3.10.0",
        "filename": "main.py",
        "wandbox_compiler": "cpython-3.12.7",
    },
    "java": {
        "judge0_id": 62,
        "piston_language": "java",
        "piston_version": "15.0.2",
        "filename": "Main.java",
        "wandbox_compiler": "openjdk-jdk-21+35",
    },
    "cpp": {
        "judge0_id": 54,
        "piston_language": "c++",
        "piston_version": "10.2.0",
        "filename": "main.cpp",
        "wandbox_compiler": "gcc-13.2.0",
    },
}


class ExecutorUnavailable(Exception):
    pass


def normalize_output(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").rstrip()


def _http_json(method, url, payload=None, headers=None, timeout=30):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "DSA-Tracker/1.0",
    }
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise ExecutorUnavailable(f"Execution service HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ExecutorUnavailable(f"Execution service unreachable: {exc.reason}") from exc


def _judge0_headers():
    headers = {}
    key = getattr(settings, "JUDGE0_API_KEY", "") or ""
    host = getattr(settings, "JUDGE0_API_HOST", "") or ""
    if key:
        headers["X-RapidAPI-Key"] = key
        headers["X-Auth-Token"] = key
    if host:
        headers["X-RapidAPI-Host"] = host
    return headers


def _run_judge0(source_code, language, stdin, cpu_time_limit=2.0):
    base = (getattr(settings, "JUDGE0_BASE_URL", "") or "").rstrip("/")
    lang = LANGUAGE_MAP[language]
    payload = {
        "source_code": source_code,
        "language_id": lang["judge0_id"],
        "stdin": stdin or "",
        "cpu_time_limit": cpu_time_limit,
        "wall_time_limit": cpu_time_limit + 1,
    }
    created = _http_json(
        "POST",
        f"{base}/submissions?base64_encoded=false&wait=false",
        payload,
        headers=_judge0_headers(),
    )
    token = created.get("token")
    if not token:
        raise ExecutorUnavailable("Judge0 did not return a submission token.")

    deadline = time.time() + 20
    result = created
    while time.time() < deadline:
        result = _http_json(
            "GET",
            f"{base}/submissions/{token}?base64_encoded=false",
            headers=_judge0_headers(),
        )
        status_id = (result.get("status") or {}).get("id")
        if status_id not in (1, 2):
            break
        time.sleep(0.35)
    return result


def _map_judge0(result):
    status = result.get("status") or {}
    status_id = status.get("id")
    stdout = result.get("stdout") or ""
    stderr = result.get("stderr") or ""
    compile_output = result.get("compile_output") or ""
    time_s = result.get("time")
    memory = result.get("memory")
    try:
        time_s = float(time_s) if time_s is not None else None
    except (TypeError, ValueError):
        time_s = None
    try:
        memory = float(memory) if memory is not None else None
    except (TypeError, ValueError):
        memory = None

    if status_id == 6:
        kind = "compilation_error"
    elif status_id == 5:
        kind = "time_limit_exceeded"
    elif status_id == 3:
        kind = "ok"
    elif status_id == 4:
        kind = "wrong_answer"
    elif status_id in (7, 8, 9, 10, 11, 12):
        kind = "runtime_error"
    else:
        kind = "runtime_error" if status_id and status_id > 3 else "ok"

    return {
        "kind": kind,
        "stdout": stdout,
        "stderr": stderr,
        "compile_output": compile_output,
        "time": time_s,
        "memory": memory,
        "status_label": status.get("description") or "",
    }


def _run_piston(source_code, language, stdin):
    base = (getattr(settings, "PISTON_BASE_URL", "") or "https://emkc.org/api/v2/piston").rstrip("/")
    lang = LANGUAGE_MAP[language]
    payload = {
        "language": lang["piston_language"],
        "version": lang["piston_version"],
        "files": [{"name": lang["filename"], "content": source_code}],
        "stdin": stdin or "",
        "run_timeout": 3000,
        "compile_timeout": 10000,
    }
    return _http_json("POST", f"{base}/execute", payload, timeout=25)


def _map_piston(result):
    compile_info = result.get("compile") or {}
    run_info = result.get("run") or {}
    compile_output = (compile_info.get("stderr") or "") + (compile_info.get("output") or "")
    if compile_info and compile_info.get("code") not in (0, None):
        return {
            "kind": "compilation_error",
            "stdout": "",
            "stderr": compile_info.get("stderr") or "",
            "compile_output": compile_output.strip(),
            "time": None,
            "memory": None,
            "status_label": "Compilation Error",
        }
    signal = run_info.get("signal")
    code = run_info.get("code")
    stdout = run_info.get("stdout") or ""
    stderr = run_info.get("stderr") or ""
    cpu = run_info.get("cpu_time")
    try:
        time_s = float(cpu) / 1000.0 if cpu is not None else None
    except (TypeError, ValueError):
        time_s = None
    if signal in ("SIGKILL", "SIGXCPU", "SIGALRM") or (isinstance(code, int) and code == 124):
        kind = "time_limit_exceeded"
    elif code not in (0, None):
        kind = "runtime_error"
    else:
        kind = "ok"
    return {
        "kind": kind,
        "stdout": stdout,
        "stderr": stderr,
        "compile_output": compile_output.strip(),
        "time": time_s,
        "memory": None,
        "status_label": kind,
    }


def _java_wandbox_source(source_code: str) -> str:
    """Wandbox compiles a single prog.java file; keep student Main.main working."""
    adapted = re.sub(r"public\s+class\s+Main\b", "class Main", source_code, count=1)
    return (
        adapted
        + "\nclass prog {\n"
        + "    public static void main(String[] args) throws Exception {\n"
        + "        Main.main(args);\n"
        + "    }\n"
        + "}\n"
    )


def _run_wandbox(source_code, language, stdin):
    base = (getattr(settings, "WANDBOX_BASE_URL", "") or "https://wandbox.org/api").rstrip("/")
    lang = LANGUAGE_MAP[language]
    payload = {
        "compiler": lang["wandbox_compiler"],
        "code": source_code,
        "stdin": stdin or "",
        "save": False,
    }
    if language == "cpp":
        payload["compiler-option-raw"] = "-std=c++17\n-O2"
    if language == "java":
        payload["code"] = _java_wandbox_source(source_code)
    return _http_json("POST", f"{base}/compile.json", payload, timeout=25)


def _map_wandbox(result):
    compiler_error = (result.get("compiler_error") or result.get("compiler_message") or "").strip()
    status = str(result.get("status") if result.get("status") is not None else "0")
    stdout = result.get("program_output") or ""
    stderr = result.get("program_error") or ""
    combined = f"{compiler_error}\n{stderr}"
    if "SyntaxError" in combined or (compiler_error and ("error:" in compiler_error.lower() or "cannot find symbol" in compiler_error.lower())):
        return {
            "kind": "compilation_error",
            "stdout": "",
            "stderr": compiler_error or stderr,
            "compile_output": compiler_error or stderr,
            "time": None,
            "memory": None,
            "status_label": "Compilation Error",
        }
    signal_text = f"{stderr} {result.get('program_message') or ''}".lower()
    if ("time" in signal_text and "limit" in signal_text) or "killed" in signal_text:
        kind = "time_limit_exceeded"
    elif status not in ("0",):
        kind = "runtime_error"
    else:
        kind = "ok"
    return {
        "kind": kind,
        "stdout": stdout,
        "stderr": stderr,
        "compile_output": "",
        "time": None,
        "memory": None,
        "status_label": kind,
    }


def execute_once(source_code: str, language: str, stdin: str) -> dict:
    if language not in LANGUAGE_MAP:
        raise ExecutorUnavailable(f"Unsupported language: {language}")
    if getattr(settings, "JUDGE0_BASE_URL", ""):
        return _map_judge0(_run_judge0(source_code, language, stdin))
    if getattr(settings, "PISTON_BASE_URL", "") and "emkc.org" not in getattr(settings, "PISTON_BASE_URL", ""):
        return _map_piston(_run_piston(source_code, language, stdin))
    return _map_wandbox(_run_wandbox(source_code, language, stdin))


def evaluate_cases(source_code, language, cases, reveal_io=True):
    """
    cases: iterable of objects with input_data, expected_output, is_hidden
    """
    cases = list(cases)
    # Playwright tests exercise the real API workflow, but must not consume
    # Wandbox/Judge0 quota.  The seed fixture uses `print('expected')` source
    # so this small local fake remains deterministic and intentionally exists
    # only when the isolated E2E setting is enabled.
    if getattr(settings, "E2E_MOCK_EXECUTOR", False):
        expected_source = source_code.lower()
        results = []
        passed = 0
        for index, case in enumerate(cases, start=1):
            expected = getattr(case, "expected_output", "") or ""
            ok = expected.strip().lower() in expected_source
            passed += int(ok)
            item = {"index": index, "status": "passed" if ok else "wrong_answer", "hidden": bool(case.is_hidden), "time": 0.001, "memory": 1}
            if not case.is_hidden and reveal_io:
                item.update({"input": case.input_data, "expected": expected, "actual": expected if ok else "incorrect"})
            results.append(item)
        return {
            "status": CodeSubmission.STATUS_ACCEPTED if passed == len(cases) else CodeSubmission.STATUS_WRONG_ANSWER,
            "tests_passed": passed, "total_tests": len(cases), "execution_time": 0.001,
            "memory_used": 1, "compile_output": "", "results": results,
        }
    planned = len(cases)
    results = []
    passed = 0
    times = []
    memories = []
    compile_output = ""
    overall = CodeSubmission.STATUS_ACCEPTED if planned else CodeSubmission.STATUS_WRONG_ANSWER

    for index, case in enumerate(cases, start=1):
        raw = execute_once(source_code, language, case.input_data)
        if raw["compile_output"] and not compile_output:
            compile_output = raw["compile_output"]

        actual = normalize_output(raw["stdout"])
        expected = normalize_output(getattr(case, "expected_output", "") or "")
        kind = raw["kind"]
        passed_case = False
        if kind == "ok":
            vtype = (getattr(case, "validation_type", "") or "EXACT_MATCH").upper()
            if vtype == "CUSTOM_VALIDATOR":
                from .validators import get_validator

                validator = get_validator(getattr(case, "validator_type", "") or "")
                passed_case = bool(
                    validator and validator.is_valid(case.input_data, actual, case.expected_output)
                )
            else:
                passed_case = actual == expected
        if passed_case:
            case_status = "passed"
            passed += 1
        elif kind == "compilation_error":
            case_status = "compilation_error"
            overall = CodeSubmission.STATUS_COMPILATION_ERROR
        elif kind == "time_limit_exceeded":
            case_status = "time_limit_exceeded"
            if overall == CodeSubmission.STATUS_ACCEPTED:
                overall = CodeSubmission.STATUS_TIME_LIMIT_EXCEEDED
        elif kind == "runtime_error":
            case_status = "runtime_error"
            if overall in (CodeSubmission.STATUS_ACCEPTED, CodeSubmission.STATUS_WRONG_ANSWER):
                overall = CodeSubmission.STATUS_RUNTIME_ERROR
        else:
            case_status = "wrong_answer"
            if overall == CodeSubmission.STATUS_ACCEPTED:
                overall = CodeSubmission.STATUS_WRONG_ANSWER

        if raw.get("time") is not None:
            times.append(raw["time"])
        if raw.get("memory") is not None:
            memories.append(raw["memory"])

        item = {
            "index": index,
            "status": case_status,
            "hidden": bool(case.is_hidden),
            "time": raw.get("time"),
            "memory": raw.get("memory"),
        }
        # Hidden cases never include stdin, expected output, stdout, or stderr.
        if not case.is_hidden:
            item["stderr"] = raw.get("stderr") or ""
            if reveal_io:
                item["input"] = case.input_data
                item["expected"] = case.expected_output
                item["actual"] = raw.get("stdout") or ""
        results.append(item)

        if kind == "compilation_error":
            break

    if planned and passed == planned:
        overall = CodeSubmission.STATUS_ACCEPTED

    return {
        "status": overall,
        "tests_passed": passed,
        "total_tests": planned,
        "execution_time": max(times) if times else None,
        "memory_used": max(memories) if memories else None,
        "compile_output": compile_output,
        "results": results,
    }
