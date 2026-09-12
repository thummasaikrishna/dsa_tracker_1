import { useCallback, useEffect, useState } from "react";
import Editor from "@monaco-editor/react";
import { Search, X } from "lucide-react";
import api from "../api/axios";
import { DifficultyBadge } from "./Badges";
import Spinner from "./Spinner";
import { LANGUAGE_OPTIONS } from "../utils/codeTemplates";

function formatStatus(status) {
  return (status || "").replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function CodeSubmissionsAdmin({ highlightId }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("");
  const [language, setLanguage] = useState("");
  const [search, setSearch] = useState("");
  const [detail, setDetail] = useState(null);

  const fetchList = useCallback(async () => {
    setLoading(true);
    const params = { page_size: 50, ordering: "-submitted_at" };
    if (status) params.status = status;
    if (language) params.language = language;
    if (search) params.search = search;
    const { data } = await api.get("/code/submissions/", { params });
    setItems(data.results ?? data);
    setLoading(false);
  }, [status, language, search]);

  useEffect(() => {
    const id = setTimeout(fetchList, 250);
    return () => clearTimeout(id);
  }, [fetchList]);

  useEffect(() => {
    if (!highlightId) return;
    api
      .get(`/code/submissions/${highlightId}/`)
      .then(({ data }) => setDetail(data))
      .catch(() => {});
  }, [highlightId]);

  async function openDetail(row) {
    const { data } = await api.get(`/code/submissions/${row.id}/`);
    setDetail(data);
  }

  const monacoLang = LANGUAGE_OPTIONS.find((l) => l.value === detail?.language)?.monaco || "python";
  const remarksHref = detail?.user_email
    ? `mailto:${encodeURIComponent(detail.user_email)}?subject=${encodeURIComponent(`DSA Tracker - Remarks: ${detail.question_title || "submission"}`)}`
    : null;

  return (
    <div>
      <div className="flex flex-wrap gap-2 mb-4">
        {[
          { value: "", label: "All Submissions" },
          { value: "accepted", label: "Accepted" },
          { value: "wrong_answer", label: "Wrong Answer" },
          { value: "compilation_error", label: "Compilation Error" },
          { value: "runtime_error", label: "Runtime Error" },
        ].map((f) => (
          <button
            key={f.value || "all"}
            onClick={() => setStatus(f.value)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border ${
              status === f.value ? "bg-brand-600 text-white border-brand-600" : "bg-white text-slate-600 border-slate-300"
            }`}
          >
            {f.label}
          </button>
        ))}
        {["", "python", "java", "cpp"].map((lang) => (
          <button
            key={lang || "lang-all"}
            onClick={() => setLanguage(lang)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border ${
              language === lang ? "bg-slate-800 text-white border-slate-800" : "bg-white text-slate-600 border-slate-300"
            }`}
          >
            {lang ? lang.toUpperCase() : "All langs"}
          </button>
        ))}
        <div className="relative flex-1 min-w-[180px]">
          <Search className="h-4 w-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            className="input !pl-9"
            placeholder="Search student or question..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {loading ? (
        <Spinner />
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-left">
              <tr>
                <th className="px-4 py-3 font-medium">Student</th>
                <th className="px-4 py-3 font-medium">Question</th>
                <th className="px-4 py-3 font-medium">Language</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Tests</th>
                <th className="px-4 py-3 font-medium">Submitted</th>
                <th className="px-4 py-3 font-medium text-right"> </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((row) => (
                <tr
                  key={row.id}
                  className={String(row.id) === String(highlightId) ? "bg-amber-50" : "hover:bg-slate-50"}
                >
                  <td className="px-4 py-3 font-medium text-slate-900">{row.display_name || row.username}</td>
                  <td className="px-4 py-3">
                    <div>{row.question_title}</div>
                    <DifficultyBadge difficulty={row.difficulty} />
                  </td>
                  <td className="px-4 py-3">{row.language_label || row.language}</td>
                  <td className="px-4 py-3">{formatStatus(row.status)}</td>
                  <td className="px-4 py-3">
                    {row.tests_passed}/{row.total_tests}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    {row.submitted_at ? new Date(row.submitted_at).toLocaleString() : "—"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button type="button" className="btn btn-secondary !py-1 !px-3 text-xs" onClick={() => openDetail(row)}>
                      View Submission
                    </button>
                  </td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr>
                  <td colSpan={7} className="text-center py-10 text-slate-400">
                    No code submissions yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {detail && (
        <div className="fixed inset-0 bg-slate-900/40 z-30 flex items-center justify-center px-4">
          <div className="card w-full max-w-4xl max-h-[92vh] overflow-hidden flex flex-col">
            <div className="flex items-start justify-between gap-3 px-5 py-4 border-b border-slate-100">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">Student submitted code</h2>
                <p className="text-sm text-slate-500">
                  {detail.display_name} {detail.user_email ? `· ${detail.user_email}` : ""}
                </p>
              </div>
              <button type="button" className="p-1.5 rounded-lg hover:bg-slate-100" onClick={() => setDetail(null)}>
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="px-5 py-3 border-b border-slate-100 bg-slate-50">
              {remarksHref ? (
                <a className="btn btn-secondary !py-1.5 text-sm" href={remarksHref}>Remarks</a>
              ) : (
                <span className="text-sm text-amber-700">Student email is not available.</span>
              )}
            </div>
            <div className="px-5 py-3 grid sm:grid-cols-2 gap-2 text-sm border-b border-slate-100">
              <div>
                <span className="text-slate-500">Question:</span> {detail.question_title}{" "}
                <DifficultyBadge difficulty={detail.difficulty} />
              </div>
              <div>
                <span className="text-slate-500">Language:</span> {detail.language_label}
              </div>
              <div>
                <span className="text-slate-500">Status:</span> {formatStatus(detail.status)}
              </div>
              <div>
                <span className="text-slate-500">Tests:</span> {detail.tests_passed} / {detail.total_tests}
              </div>
              <div>
                <span className="text-slate-500">Time:</span> {detail.execution_time ?? "—"}s
              </div>
              <div>
                <span className="text-slate-500">Memory:</span> {detail.memory_used ?? "—"} KB
              </div>
              <div>
                <span className="text-slate-500">Submitted:</span>{" "}
                {detail.submitted_at ? new Date(detail.submitted_at).toLocaleString() : "—"}
              </div>
              <div>
                <span className="text-slate-500">Points Earned:</span> +{detail.points_awarded ?? 0} ⭐
              </div>
            </div>
            <div className="h-[24rem] w-full overflow-hidden bg-[#1e1e1e]">
              <Editor
                height="100%"
                width="100%"
                language={monacoLang}
                value={detail.source_code || ""}
                theme="vs-dark"
                options={{
                  readOnly: true,
                  minimap: { enabled: false },
                  fontSize: 13,
                  automaticLayout: true,
                  domReadOnly: true,
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
