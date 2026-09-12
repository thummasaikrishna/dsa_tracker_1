import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import api from "../api/axios";
import { DifficultyBadge } from "../components/Badges";
import { DifficultyFilter, PeriodSelect, StatusFilter } from "../components/Filters";
import ActivityStats from "../components/ActivityStats";
import AssignmentRow from "../components/AssignmentRow";
import QuestionFormModal from "../components/QuestionFormModal";
import Spinner from "../components/Spinner";
import FlashBanner from "../components/FlashBanner";
import { formatApiError } from "../utils/apiError";
import CodeSubmissionsAdmin from "../components/CodeSubmissionsAdmin";
import {
  Plus, Pencil, Trash2, Users, BookOpen, ClipboardList, CheckCircle2,
  ExternalLink, ShieldCheck, Search, Mail, Bell, XCircle,
} from "lucide-react";

const TABS = [
  { key: "questions", label: "Question Management" },
  { key: "proofs", label: "Proof Validation" },
  { key: "submissions", label: "Submissions" },
  { key: "students", label: "Student Activity" },
  { key: "leaderboard", label: "🏆 Leaderboard" },
];

function buildRemarksGmailUrl(assignment) {
  const email = (assignment.user_email || "").trim();
  if (!email) return null;
  const title = assignment.question_title || "your DSA solution";
  const subject = `Remarks on your solution: ${title}`;
  const body = [
    `Hi ${assignment.username || "there"},`,
    "",
    `I reviewed your LinkedIn proof for "${title}".`,
    "",
    "Remarks:",
    "",
    "",
    "Best regards,",
  ].join("\n");
  const params = new URLSearchParams({
    view: "cm",
    fs: "1",
    to: email,
    su: subject,
    body,
  });
  return `https://mail.google.com/mail/?${params.toString()}`;
}

export default function AdminDashboard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const highlightId = searchParams.get("highlight");
  const tab = TABS.some((t) => t.key === tabParam) ? tabParam : "questions";
  const [pendingCount, setPendingCount] = useState(0);

  function setTab(key) {
    const next = new URLSearchParams(searchParams);
    next.set("tab", key);
    if (key !== "proofs" && key !== "submissions") next.delete("highlight");
    setSearchParams(next, { replace: true });
  }

  const refreshPending = useCallback(() => {
    api
      .get("/analytics/pending-proofs/")
      .then((res) => setPendingCount(res.data.count ?? 0))
      .catch(() => {});
  }, []);

  useEffect(() => {
    refreshPending();
    const id = setInterval(refreshPending, 20_000);
    function onFocus() {
      refreshPending();
    }
    function onVisibility() {
      if (document.visibilityState === "visible") refreshPending();
    }
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      clearInterval(id);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [refreshPending, tab]);

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
      <h1 className="text-2xl font-bold text-slate-900 mb-1">Admin Dashboard</h1>
      <p className="text-sm text-slate-500 mb-6">Manage questions and monitor student progress.</p>

      <OverviewStats pendingCount={pendingCount} onOpenProofs={() => setTab("proofs")} />

      <div className="flex gap-1 border-b border-slate-200 mb-6 overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors whitespace-nowrap inline-flex items-center gap-1.5 ${
              tab === t.key
                ? "border-brand-600 text-brand-700"
                : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            {t.label}
            {t.key === "proofs" && pendingCount > 0 && (
              <span className="ml-0.5 min-w-[1.25rem] h-5 px-1.5 rounded-full bg-rose-500 text-white text-[11px] font-bold flex items-center justify-center">
                {pendingCount}
              </span>
            )}
          </button>
        ))}
      </div>

      {tab === "questions" && <QuestionManagement />}
      {tab === "proofs" && (
        <ProofValidation
          highlightId={highlightId}
          onValidated={refreshPending}
        />
      )}
      {tab === "submissions" && <CodeSubmissionsAdmin highlightId={highlightId} />}
      {tab === "students" && <StudentActivity />}
      {tab === "leaderboard" && <LeaderboardView showAdminActivity />}
    </div>
  );
}

// ---------------------------------------------------------------------------
function OverviewStats({ pendingCount, onOpenProofs }) {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    api.get("/analytics/overview/").then((res) => setStats(res.data)).catch(() => {});
  }, []);

  if (!stats) return null;

  const cards = [
    { label: "Total Users", value: stats.total_users, icon: Users, color: "text-brand-700 bg-brand-50" },
    { label: "Total Questions", value: stats.total_questions, icon: BookOpen, color: "text-amber-700 bg-amber-50" },
    { label: "Total Assignments", value: stats.total_assignments, icon: ClipboardList, color: "text-blue-700 bg-blue-50" },
    { label: "Total Completed", value: stats.total_completed, icon: CheckCircle2, color: "text-emerald-700 bg-emerald-50" },
  ];

  return (
    <div className="mb-6 space-y-3">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {cards.map((c) => (
          <div key={c.label} className="card p-4 flex items-center gap-3">
            <div className={`h-10 w-10 rounded-xl flex items-center justify-center ${c.color}`}>
              <c.icon className="h-5 w-5" />
            </div>
            <div>
              <div className="text-2xl font-bold text-slate-900 leading-none">{c.value}</div>
              <div className="text-xs text-slate-500 mt-1">{c.label}</div>
            </div>
          </div>
        ))}
      </div>
      {(pendingCount > 0 || (stats.pending_proofs ?? 0) > 0) && (
        <button
          type="button"
          onClick={onOpenProofs}
          className="w-full card p-3 flex items-center gap-3 text-left hover:bg-rose-50/60 border-rose-100 transition-colors"
        >
          <div className="h-10 w-10 rounded-xl flex items-center justify-center text-rose-700 bg-rose-50">
            <Bell className="h-5 w-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold text-slate-900">
              {pendingCount || stats.pending_proofs} LinkedIn proof
              {(pendingCount || stats.pending_proofs) === 1 ? "" : "s"} awaiting validation
            </div>
            <div className="text-xs text-slate-500">Click to open Proof Validation</div>
          </div>
          <span className="text-xs font-medium text-rose-600 shrink-0">Review →</span>
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
function QuestionManagement() {
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [difficulty, setDifficulty] = useState("");
  const [modalQuestion, setModalQuestion] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [flash, setFlash] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  const fetchQuestions = useCallback(async () => {
    setLoading(true);
    const params = { page_size: 100 };
    if (difficulty) params.difficulty = difficulty;
    const { data } = await api.get("/questions/", { params });
    setQuestions(data.results ?? data);
    setLoading(false);
  }, [difficulty]);

  useEffect(() => {
    fetchQuestions();
  }, [fetchQuestions]);

  function openCreate() {
    setModalQuestion({});
    setShowModal(true);
  }
  async function openEdit(q) {
    try {
      const { data } = await api.get(`/questions/${q.id}/`);
      setModalQuestion(data);
    } catch {
      setModalQuestion(q);
    }
    setShowModal(true);
  }

  async function handleSubmit(form) {
    const payload = {
      title: form.title,
      description: form.description,
      examples: form.examples,
      prerequisites: form.prerequisites,
      difficulty: form.difficulty,
      deadline: form.deadline,
      reference_solution: form.reference_solution || "",
      reference_solution_language: form.reference_solution_language || "python",
      test_cases: (form.test_cases || []).map((tc, index) => ({
        input_data: tc.input_data || "",
        expected_output: tc.expected_output || "",
        is_hidden: Boolean(tc.is_hidden),
        order: index,
        validation_type: tc.validation_type || "EXACT_MATCH",
        validator_type: tc.validator_type || "",
        verification_status: tc.verification_status || "VERIFIED",
        verification_reason: tc.verification_reason || "",
      })),
    };
    if (form.id) {
      await api.put(`/questions/${form.id}/`, payload);
      setFlash({ type: "success", text: "Question updated successfully." });
    } else {
      await api.post("/questions/", payload);
      setFlash({ type: "success", text: "Question added successfully." });
    }
    fetchQuestions();
  }

  async function handleDelete(question) {
    if (!confirm(`Delete "${question.title}"? This will remove it from active listings.`)) return;
    setDeletingId(question.id);
    try {
      await api.delete(`/questions/${question.id}/`);
      setFlash({ type: "success", text: "Question deleted successfully." });
      fetchQuestions();
    } catch (err) {
      setFlash({ type: "error", text: formatApiError(err, "Failed to delete question.") });
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div>
      <FlashBanner
        message={flash?.text}
        type={flash?.type}
        onClose={() => setFlash(null)}
      />
      <div className="flex items-center justify-between mb-5">
        <DifficultyFilter value={difficulty} onChange={setDifficulty} />
        <button onClick={openCreate} className="btn btn-primary">
          <Plus className="h-4 w-4" /> Add Question
        </button>
      </div>

      {loading ? (
        <Spinner />
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-left">
              <tr>
                <th className="px-4 py-3 font-medium">Question</th>
                <th className="px-4 py-3 font-medium">Pre-requisites</th>
                <th className="px-4 py-3 font-medium">Difficulty</th>
                <th className="px-4 py-3 font-medium">Deadline</th>
                <th className="px-4 py-3 font-medium">Assignments</th>
                <th className="px-4 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {questions.map((q) => (
                <tr key={q.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-900">{q.title}</div>
                    {q.description && (
                      <div className="text-xs text-slate-400 line-clamp-1 mt-0.5">{q.description}</div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-500 text-xs max-w-[180px] truncate">
                    {q.prerequisites || "—"}
                  </td>
                  <td className="px-4 py-3">
                    <DifficultyBadge difficulty={q.difficulty} />
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-600 whitespace-nowrap">
                    {q.deadline_expired ? (
                      <span className="text-rose-600 font-medium">Expired</span>
                    ) : q.deadline ? (
                      new Date(q.deadline).toLocaleString()
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-500">{q.assignment_count ?? 0}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1">
                      <button
                        onClick={() => openEdit(q)}
                        className="p-1.5 rounded-lg text-slate-500 hover:bg-slate-100"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => handleDelete(q)}
                        disabled={deletingId === q.id}
                        className="p-1.5 rounded-lg text-slate-500 hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {questions.length === 0 && (
                <tr>
                  <td colSpan={6} className="text-center py-10 text-slate-400">
                    No questions yet — click "Add Question" to create one.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {showModal && (
        <QuestionFormModal initial={modalQuestion} onClose={() => setShowModal(false)} onSubmit={handleSubmit} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
function ProofValidation({ highlightId, onValidated }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [validatingId, setValidatingId] = useState(null);
  const [rejectingId, setRejectingId] = useState(null);
  const [filter, setFilter] = useState("pending");
  const [flash, setFlash] = useState(null);
  const rowRefs = useRef({});
  const navigate = useNavigate();

  const fetchProofs = useCallback(async () => {
    setLoading(true);
    const params = { page_size: 100, ordering: "-submitted_at" };
    if (filter) params.proof_status = filter;
    const { data } = await api.get("/assignments/", { params });
    setItems(data.results ?? data);
    setLoading(false);
  }, [filter]);

  useEffect(() => {
    fetchProofs();
  }, [fetchProofs]);

  // When opening from the bell with a highlight, ensure pending filter so the row is visible.
  useEffect(() => {
    if (highlightId && filter !== "pending" && filter !== "") {
      setFilter("pending");
    }
  }, [highlightId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!highlightId || loading) return;
    const el = rowRefs.current[String(highlightId)];
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [highlightId, loading, items]);

  async function handleReject(assignment) {
    if (!confirm(`Reject ${assignment.username}'s LinkedIn proof for "${assignment.question_title}"? They will receive 0 points.`)) {
      return;
    }
    setRejectingId(assignment.id);
    try {
      await api.post(`/assignments/${assignment.id}/reject_proof/`);
      setFlash({ type: "success", text: "Submission rejected. 0 points awarded." });
      fetchProofs();
      onValidated?.();
      navigate("/admin?tab=proofs", { replace: true });
    } catch (err) {
      setFlash({ type: "error", text: formatApiError(err, "Failed to reject submission.") });
    } finally {
      setRejectingId(null);
    }
  }

  async function handleValidate(assignment) {
    if (!confirm(`Validate ${assignment.username}'s LinkedIn proof for "${assignment.question_title}"?`)) {
      return;
    }
    setValidatingId(assignment.id);
    try {
      await api.post(`/assignments/${assignment.id}/validate_proof/`);
      setFlash({ type: "success", text: "Solution validated successfully." });
      fetchProofs();
      onValidated?.();
      navigate("/admin?tab=proofs", { replace: true });
    } catch (err) {
      setFlash({ type: "error", text: formatApiError(err, "Failed to validate solution.") });
    } finally {
      setValidatingId(null);
    }
  }

  return (
    <div>
      <FlashBanner message={flash?.text} type={flash?.type} onClose={() => setFlash(null)} />
      <div className="flex items-center gap-2 mb-5 flex-wrap">
        {[
          { value: "pending", label: "Pending review" },
          { value: "validated", label: "Validated" },
          { value: "rejected", label: "Rejected" },
          { value: "", label: "All with proof" },
        ].map((f) => (
          <button
            key={f.value || "all"}
            onClick={() => setFilter(f.value)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
              filter === f.value
                ? "bg-brand-600 text-white border-brand-600"
                : "bg-white text-slate-600 border-slate-300 hover:bg-slate-50"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <Spinner />
      ) : items.length === 0 ? (
        <div className="text-center py-14 text-slate-400 text-sm">
          No submissions in this filter.
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-left">
              <tr>
                <th className="px-4 py-3 font-medium">Student</th>
                <th className="px-4 py-3 font-medium">Question</th>
                <th className="px-4 py-3 font-medium">LinkedIn proof</th>
                <th className="px-4 py-3 font-medium">Submitted</th>
                <th className="px-4 py-3 font-medium">Points</th>
                <th className="px-4 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items
                .filter((a) => a.proof_status !== "none")
                .map((a) => {
                  const isHighlight = String(a.id) === String(highlightId);
                  const gmailUrl = buildRemarksGmailUrl(a);
                  return (
                    <tr
                      key={a.id}
                      ref={(el) => {
                        if (el) rowRefs.current[String(a.id)] = el;
                      }}
                      className={`hover:bg-slate-50 ${
                        isHighlight ? "bg-amber-50 ring-2 ring-inset ring-amber-300" : ""
                      }`}
                    >
                      <td className="px-4 py-3">
                        <div className="font-medium text-slate-900">{a.username}</div>
                        {a.user_email && (
                          <div className="text-[11px] text-slate-400 truncate max-w-[140px]">
                            {a.user_email}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="text-slate-800">{a.question_title}</div>
                        <DifficultyBadge difficulty={a.difficulty} />
                      </td>
                      <td className="px-4 py-3 max-w-[220px]">
                        {a.linkedin_post_url ? (
                          <a
                            href={a.linkedin_post_url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-brand-600 hover:underline text-xs break-all inline-flex items-start gap-1"
                            title={a.linkedin_post_url}
                          >
                            <span className="line-clamp-2">{a.linkedin_post_url}</span>
                            <ExternalLink className="h-3 w-3 shrink-0 mt-0.5" />
                          </a>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-500 text-xs">
                        {a.submitted_at ? new Date(a.submitted_at).toLocaleString() : "—"}
                        {a.submitted_after_deadline && (
                          <div className="text-rose-600 font-medium mt-1">After deadline</div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-700 whitespace-nowrap">
                        {a.proof_status === "validated"
                          ? `Awarded ${a.points_awarded ?? 0}`
                          : `Potential ${a.potential_points ?? 0}`}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="inline-flex flex-col sm:flex-row items-end sm:items-center gap-1.5 justify-end">
                          {gmailUrl ? (
                            <a
                              href={gmailUrl}
                              target="_blank"
                              rel="noreferrer"
                              className="btn btn-secondary !py-1.5 !px-3 text-xs"
                              title={`Email remarks to ${a.user_email}`}
                            >
                              <Mail className="h-3.5 w-3.5" />
                              Send remarks
                            </a>
                          ) : (
                            <span
                              className="text-[11px] text-slate-400 px-1"
                              title="Student has no email on file"
                            >
                              No email
                            </span>
                          )}
                          {a.proof_status === "pending" ? (
                            <>
                              <button
                                onClick={() => handleValidate(a)}
                                disabled={validatingId === a.id || rejectingId === a.id}
                                className="btn btn-primary !py-1.5 !px-3 text-xs"
                              >
                                <ShieldCheck className="h-3.5 w-3.5" />
                                {validatingId === a.id ? "Validating..." : "Validate"}
                              </button>
                              <button
                                onClick={() => handleReject(a)}
                                disabled={validatingId === a.id || rejectingId === a.id}
                                className="btn btn-danger !py-1.5 !px-3 text-xs"
                              >
                                <XCircle className="h-3.5 w-3.5" />
                                {rejectingId === a.id ? "Rejecting..." : "Reject"}
                              </button>
                            </>
                          ) : a.proof_status === "rejected" ? (
                            <span className="text-xs font-medium text-rose-700 px-1">Rejected · 0 pts</span>
                          ) : (
                            <span className="text-xs font-medium text-emerald-700 px-1">Validated</span>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
function studentMatchText(s) {
  return [s.username, s.email, s.first_name, s.last_name]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function StudentPicker({ students, selectedId, onSelect }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);

  const selected = students.find((s) => String(s.id) === String(selectedId));

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return students.slice(0, 20);
    return students
      .filter((s) => studentMatchText(s).includes(q))
      .slice(0, 20);
  }, [students, query]);

  useEffect(() => {
    function onDocClick(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  function pick(student) {
    onSelect(String(student.id));
    setQuery("");
    setOpen(false);
  }

  const displayName = selected
    ? [selected.first_name, selected.last_name].filter(Boolean).join(" ") || selected.username
    : "";

  return (
    <div className="relative min-w-[220px] sm:min-w-[280px] flex-1 max-w-md" ref={wrapRef}>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 pointer-events-none" />
        <input
          type="search"
          className="input !pl-9 text-sm"
          placeholder={
            selected
              ? `Selected: ${selected.username}${selected.email ? ` · ${selected.email}` : ""}`
              : "Search students by name, username, or email…"
          }
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          aria-label="Search students"
        />
      </div>
      {selected && !open && (
        <div className="mt-1 text-xs text-slate-500 truncate">
          Viewing: <span className="font-medium text-slate-700">{displayName}</span>
          {selected.email ? ` (${selected.email})` : ""}
        </div>
      )}
      {open && (
        <div className="absolute z-20 mt-1 w-full card shadow-lg max-h-64 overflow-y-auto">
          {matches.length === 0 ? (
            <div className="px-3 py-4 text-sm text-slate-400 text-center">No students match.</div>
          ) : (
            matches.map((s) => {
              const name = [s.first_name, s.last_name].filter(Boolean).join(" ");
              const isActive = String(s.id) === String(selectedId);
              return (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => pick(s)}
                  className={`w-full text-left px-3 py-2.5 border-b border-slate-50 last:border-0 hover:bg-brand-50 transition-colors ${
                    isActive ? "bg-brand-50" : ""
                  }`}
                >
                  <div className="text-sm font-medium text-slate-900">{s.username}</div>
                  <div className="text-xs text-slate-500 truncate">
                    {[name, s.email].filter(Boolean).join(" · ") || "No email"}
                  </div>
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

function StudentActivity() {
  const [students, setStudents] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [period, setPeriod] = useState("all");
  const [difficulty, setDifficulty] = useState("");
  const [status, setStatus] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [flash, setFlash] = useState(null);
  const [removing, setRemoving] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);

  function loadStudents(preferId) {
    return api.get("/analytics/students/?page_size=200").then((res) => {
      const list = res.data.results ?? res.data;
      setStudents(list);
      if (list.length === 0) {
        setSelectedId("");
        setData(null);
        return list;
      }
      const keep = preferId && list.some((s) => String(s.id) === String(preferId));
      setSelectedId(keep ? String(preferId) : String(list[0].id));
      return list;
    });
  }

  useEffect(() => {
    loadStudents();
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    const student = students.find((s) => String(s.id) === selectedId);
    if (!student) return;
    let cancelled = false;
    setLoading(true);
    const params = { period };
    if (difficulty) params.difficulty = difficulty;
    if (status) params.status = status;
    api
      .get(`/analytics/student/${student.user_id}/`, { params })
      .then((res) => {
        if (!cancelled) {
          setData(res.data);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setData(null);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, period, difficulty, status, students]);

  async function handleRemoveStudent() {
    const student = students.find((s) => String(s.id) === selectedId);
    if (!student) return;
    setRemoving(true);
    try {
      await api.post(`/analytics/students/${student.user_id}/remove/`);
      setConfirmRemove(false);
      setFlash({ type: "success", text: "Student removed successfully." });
      const remaining = students.filter((s) => s.id !== student.id);
      setStudents(remaining);
      setSelectedId(remaining[0] ? String(remaining[0].id) : "");
      if (!remaining[0]) setData(null);
    } catch (err) {
      setFlash({ type: "error", text: formatApiError(err, "Failed to remove student.") });
    } finally {
      setRemoving(false);
    }
  }

  const selectedStudent = students.find((s) => String(s.id) === selectedId);
  const statusCounts = data?.status_breakdown;

  return (
    <div>
      <FlashBanner message={flash?.text} type={flash?.type} onClose={() => setFlash(null)} />
      <div className="flex flex-col sm:flex-row sm:items-start gap-3 mb-5 flex-wrap">
        <StudentPicker
          students={students}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
        {selectedStudent && (
          <button
            type="button"
            onClick={() => setConfirmRemove(true)}
            className="btn btn-danger !py-2 text-sm"
          >
            Remove Student
          </button>
        )}
        <div className="flex flex-wrap gap-3 items-center">
          <PeriodSelect value={period} onChange={setPeriod} />
          <DifficultyFilter value={difficulty} onChange={setDifficulty} />
          <StatusFilter value={status} onChange={setStatus} counts={statusCounts} />
        </div>
      </div>

      {students.length === 0 ? (
        <div className="text-center py-14 text-slate-400 text-sm inline-flex items-center gap-2">
          <Users className="h-4 w-4" /> No students have signed up yet.
        </div>
      ) : loading || !data ? (
        <Spinner />
      ) : (
        <>
          <ActivityStats
            breakdown={data.breakdown}
            statusBreakdown={data.status_breakdown}
            completedBreakdown={data.completed_breakdown}
          />
          <div className="card mt-5 p-2 divide-y divide-slate-100">
            {data.items.length === 0 ? (
              <div className="text-center py-10 text-slate-400 text-sm">No activity matching these filters.</div>
            ) : (
              data.items.map((a) => (
                <AssignmentRow key={a.id} assignment={a} readOnly />
              ))
            )}
          </div>
        </>
      )}

      {confirmRemove && selectedStudent && (
        <div className="fixed inset-0 bg-slate-900/40 flex items-center justify-center z-30 px-4">
          <div className="card w-full max-w-md p-6">
            <h2 className="text-lg font-semibold text-slate-900 mb-2">Remove student</h2>
            <p className="text-sm text-slate-600">
              Are you sure you want to remove this student from the DSA Tracker?
            </p>
            <p className="text-sm font-medium text-slate-800 mt-2">
              {selectedStudent.username}
              {selectedStudent.email ? ` · ${selectedStudent.email}` : ""}
            </p>
            <div className="flex justify-end gap-2 mt-5">
              <button type="button" className="btn btn-secondary" onClick={() => setConfirmRemove(false)} disabled={removing}>
                Cancel
              </button>
              <button type="button" className="btn btn-danger" onClick={handleRemoveStudent} disabled={removing}>
                {removing ? "Removing..." : "Remove Student"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
