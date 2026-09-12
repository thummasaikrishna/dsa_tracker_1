import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Editor from "@monaco-editor/react";
import { Lock, Play, Rocket } from "lucide-react";
import api from "../api/axios";
import { formatApiError } from "../utils/apiError";
import { LANGUAGE_OPTIONS, STARTER_CODE, draftKey } from "../utils/codeTemplates";

function statusClass(status) {
  if (status === "passed" || status === "accepted") return "text-emerald-700 bg-emerald-50 border-emerald-200";
  if (status === "wrong_answer") return "text-rose-700 bg-rose-50 border-rose-200";
  if (status === "compilation_error") return "text-amber-800 bg-amber-50 border-amber-200";
  return "text-slate-700 bg-slate-50 border-slate-200";
}

function formatStatus(status) {
  return (status || "").replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function CodeWorkspace({ questionId, assigned = false }) {
  const [language, setLanguage] = useState("python");
  const drafts = useRef({});
  const [code, setCode] = useState(STARTER_CODE.python);
  const [busy, setBusy] = useState("");
  const [runResult, setRunResult] = useState(null);
  const [submission, setSubmission] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState("");

  const monacoLang = useMemo(
    () => LANGUAGE_OPTIONS.find((l) => l.value === language)?.monaco || "python",
    [language]
  );

  const loadDraft = useCallback(
    (lang) => {
      const key = draftKey(questionId, lang);
      if (drafts.current[lang] != null) return drafts.current[lang];
      const stored = localStorage.getItem(key);
      const value = stored != null ? stored : STARTER_CODE[lang];
      drafts.current[lang] = value;
      return value;
    },
    [questionId]
  );

  useEffect(() => {
    drafts.current = {};
    setCode(loadDraft("python"));
    setLanguage("python");
    setRunResult(null);
    setSubmission(null);
    api
      .get("/code/submissions/me/", { params: { question: questionId, page_size: 20 } })
      .then(({ data }) => setHistory(data.results ?? data))
      .catch(() => {});
  }, [questionId, loadDraft]);

  function persist(lang, value) {
    drafts.current[lang] = value;
    localStorage.setItem(draftKey(questionId, lang), value);
  }

  function handleLanguageChange(next) {
    persist(language, code);
    setLanguage(next);
    setCode(loadDraft(next));
  }

  async function runCode() {
    if (!assigned || busy) return;
    setBusy("run");
    setError("");
    setSubmission(null);
    try {
      const { data } = await api.post("/code/run/", {
        question_id: Number(questionId),
        language,
        source_code: code,
      });
      setRunResult(data);
    } catch (err) {
      setError(formatApiError(err, "Failed to run code."));
    } finally {
      setBusy("");
    }
  }

  async function submitCode() {
    if (!assigned || busy) return;
    setBusy("submit");
    setError("");
    try {
      const { data } = await api.post("/code/submit/", {
        question_id: Number(questionId),
        language,
        source_code: code,
      });
      setSubmission(data);
      setRunResult(null);
      setHistory((list) => [data, ...list.filter((row) => row.id !== data.id)]);
    } catch (err) {
      setError(formatApiError(err, "Failed to submit solution."));
    } finally {
      setBusy("");
    }
  }

  const panel = submission || runResult;
  const results = panel?.public_results || panel?.results || [];
  const publicRows = results.filter((row) => !row.hidden);
  const hiddenRows = results.filter((row) => row.hidden);
  const locked = !assigned;
  const actionsDisabled = locked || Boolean(busy);

  return (
    <div className="flex flex-col card overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b border-slate-200 bg-white">
        <select
          className="input !w-auto !py-1.5 text-sm"
          value={language}
          onChange={(e) => handleLanguageChange(e.target.value)}
          disabled={actionsDisabled}
        >
          {LANGUAGE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <div className="flex-1" />
        <button type="button" className="btn btn-secondary !py-1.5 text-sm" onClick={runCode} disabled={actionsDisabled}>
          <Play className="h-3.5 w-3.5" />
          {busy === "run" ? "Running..." : "Run Code"}
        </button>
        <button type="button" className="btn btn-primary !py-1.5 text-sm" onClick={submitCode} disabled={actionsDisabled}>
          <Rocket className="h-3.5 w-3.5" />
          {busy === "submit" ? "Evaluating..." : "Submit Solution"}
        </button>
      </div>

      {locked && (
        <div className="px-3 py-2 text-sm text-amber-800 bg-amber-50 border-b border-amber-100">
          Please assign this question before attempting to solve it.
        </div>
      )}

      <div className="relative h-[28rem] lg:h-[calc(100vh-18rem)] min-h-[22rem] w-full shrink-0 overflow-hidden bg-[#1e1e1e]">
        <Editor
          height="100%"
          width="100%"
          language={monacoLang}
          value={code}
          onChange={(value) => {
            if (locked) return;
            const next = value ?? "";
            setCode(next);
            persist(language, next);
          }}
          theme="vs-dark"
          loading={
            <div className="h-full w-full bg-[#1e1e1e] text-slate-400 text-sm flex items-center justify-center">
              Loading editor…
            </div>
          }
          options={{
            readOnly: locked,
            domReadOnly: locked,
            minimap: { enabled: false },
            fontSize: 13,
            scrollBeyondLastLine: false,
            automaticLayout: true,
            wordWrap: "on",
            padding: { top: 8 },
          }}
        />
        {locked && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#1e1e1e]/80 pointer-events-none">
            <div className="text-center text-slate-200 px-4">
              <Lock className="h-6 w-6 mx-auto mb-2" />
              <div className="text-sm font-medium">Assign this question to start coding.</div>
            </div>
          </div>
        )}
      </div>

      <div className="border-t border-slate-200 bg-slate-50 max-h-64 overflow-y-auto p-3 space-y-2">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Output / Test Results</div>
        {error && <div className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">{error}</div>}
        {busy && !panel && <div className="text-sm text-slate-500">{busy === "run" ? "Running..." : "Submitting..."}</div>}
        {submission && (
          <div className={`text-sm font-semibold rounded-lg border px-3 py-2 ${statusClass(submission.status)}`}>
            {submission.status === "accepted" ? "🎉 ACCEPTED" : `❌ ${formatStatus(submission.status)}`}
            <div className="font-medium mt-0.5">
              Passed: {submission.tests_passed} / {submission.total_tests} Test Cases
              {submission.status === "accepted" ? ` · Points Earned: +${submission.points_awarded}` : ""}
            </div>
          </div>
        )}
        {runResult && !submission && (
          <div className="text-sm text-slate-700">
            Public tests: {runResult.tests_passed} / {runResult.total_tests} passed
          </div>
        )}
        {panel?.compile_output && (
          <pre className="text-xs bg-slate-900 text-amber-100 rounded-lg p-2 overflow-x-auto">{panel.compile_output}</pre>
        )}
        {publicRows.length > 0 && (
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 pt-1">Public Test Cases</div>
        )}
        {publicRows.map((row) => (
          <div key={`public-${row.index}-${row.status}`} className="rounded-lg border border-slate-200 bg-white p-2 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-slate-800">Test Case {row.index}</span>
              <span className={`px-2 py-0.5 rounded-full border ${statusClass(row.status)}`}>{formatStatus(row.status)}</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-1 font-mono">
              <div>
                <div className="text-slate-400">Input</div>
                <pre className="whitespace-pre-wrap">{row.input ?? ""}</pre>
              </div>
              <div>
                <div className="text-slate-400">Expected Output</div>
                <pre className="whitespace-pre-wrap">{row.expected ?? ""}</pre>
              </div>
              <div>
                <div className="text-slate-400">Actual</div>
                <pre className="whitespace-pre-wrap">{row.actual ?? ""}</pre>
              </div>
            </div>
            {(row.stderr || row.time != null) && (
              <div className="text-slate-500 mt-1">
                {row.time != null ? `Time: ${row.time}s` : ""}
                {row.memory != null ? ` · Memory: ${row.memory} KB` : ""}
                {row.stderr ? ` · ${row.stderr}` : ""}
              </div>
            )}
          </div>
        ))}
        {hiddenRows.length > 0 && (
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 pt-1">Private Test Cases</div>
        )}
        {hiddenRows.map((row, idx) => {
          const passed = row.status === "passed";
          return (
            <div
              key={`hidden-${row.index}-${row.status}`}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs flex items-center justify-between gap-2"
            >
              <span className="font-medium text-slate-800">Test Case {idx + 1}</span>
              <span className={`px-2 py-0.5 rounded-full border ${statusClass(passed ? "passed" : "wrong_answer")}`}>
                {passed ? "PASSED" : "FAILED"}
              </span>
            </div>
          );
        })}

        {history.length > 0 && (
          <div className="pt-2">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">Your submissions</div>
            <div className="space-y-1">
              {history.map((row, idx) => (
                <div key={row.id} className="text-xs text-slate-600 flex justify-between gap-2">
                  <span>
                    #{history.length - idx} · {row.language_label || row.language} · {formatStatus(row.status)}
                  </span>
                  <span>
                    {row.tests_passed}/{row.total_tests} · {row.submitted_at ? new Date(row.submitted_at).toLocaleString() : ""}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
