import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import api from "../api/axios";
import QuestionCard from "../components/QuestionCard";
import AssignmentRow from "../components/AssignmentRow";
import ActivityStats from "../components/ActivityStats";
import { DifficultyFilter, PeriodSelect } from "../components/Filters";
import Spinner from "../components/Spinner";
import FlashBanner from "../components/FlashBanner";
import { formatApiError } from "../utils/apiError";
import LeaderboardView from "../components/LeaderboardView";
import { Search } from "lucide-react";

const TABS = [
  { key: "browse", label: "Available Questions" },
  { key: "mine", label: "My Assigned Questions" },
  { key: "activity", label: "My Activity" },
  { key: "leaderboard", label: "🏆 Leaderboard" },
];

export default function UserDashboard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const highlightId = searchParams.get("highlight");
  const tab = TABS.some((t) => t.key === tabParam) ? tabParam : "browse";

  function setTab(key) {
    const next = new URLSearchParams(searchParams);
    next.set("tab", key);
    if (key !== "mine") next.delete("highlight");
    setSearchParams(next, { replace: true });
  }

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
      <h1 className="text-2xl font-bold text-slate-900 mb-1">Student Dashboard</h1>
      <p className="text-sm text-slate-500 mb-6">Browse questions, manage assignments, and track your progress.</p>

      <div className="flex gap-1 border-b border-slate-200 mb-6">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.key
                ? "border-brand-600 text-brand-700"
                : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "browse" && <BrowseQuestions />}
      {tab === "mine" && <MyAssignments highlightId={highlightId} />}
      {tab === "activity" && <MyActivity />}
      {tab === "leaderboard" && <LeaderboardView />}
    </div>
  );
}

// ---------------------------------------------------------------------------
function BrowseQuestions() {
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [difficulty, setDifficulty] = useState("");
  const [search, setSearch] = useState("");

  const fetchQuestions = useCallback(async () => {
    setLoading(true);
    const params = { page_size: 100 };
    if (difficulty) params.difficulty = difficulty;
    if (search) params.search = search;
    const { data } = await api.get("/questions/", { params });
    setQuestions(data.results ?? data);
    setLoading(false);
  }, [difficulty, search]);

  // Debounce the search box so we don't fire an API call per keystroke.
  useEffect(() => {
    const id = setTimeout(fetchQuestions, 300);
    return () => clearTimeout(id);
  }, [fetchQuestions]);

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-5">
        <div className="relative flex-1 max-w-xs">
          <Search className="h-4 w-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            className="input !pl-9"
            placeholder="Search questions..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <DifficultyFilter value={difficulty} onChange={setDifficulty} />
      </div>

      {loading ? (
        <Spinner />
      ) : questions.length === 0 ? (
        <EmptyState text="No questions match your filters." />
      ) : (
        <div className="card divide-y divide-slate-100 overflow-hidden">
          {questions.map((q) => (
            <QuestionCard key={q.id} question={q} />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
function MyAssignments({ highlightId }) {
  const [assignments, setAssignments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("");
  const [flash, setFlash] = useState(null);
  const [unassigningId, setUnassigningId] = useState(null);

  const fetchAssignments = useCallback(async () => {
    setLoading(true);
    const params = { page_size: 100 };
    if (status) params.status = status;
    const { data } = await api.get("/assignments/", { params });
    setAssignments(data.results ?? data);
    setLoading(false);
  }, [status]);

  useEffect(() => {
    fetchAssignments();
  }, [fetchAssignments]);

  async function handleStatusChange(assignment, newStatus) {
    const prev = assignments;
    setAssignments((list) => list.map((a) => (a.id === assignment.id ? { ...a, status: newStatus } : a)));
    try {
      await api.patch(`/assignments/${assignment.id}/status_update/`, { status: newStatus });
    } catch (err) {
      setAssignments(prev);
      setFlash({ type: "error", text: formatApiError(err, "Could not update status.") });
    }
  }

  async function handleUnassign(assignment) {
    if (!confirm(`Unassign "${assignment.question_title}"?`)) return;
    const prev = assignments;
    setUnassigningId(assignment.id);
    setAssignments((list) => list.filter((a) => a.id !== assignment.id));
    try {
      await api.delete(`/assignments/${assignment.id}/`);
      setFlash({ type: "success", text: "Question unassigned successfully." });
    } catch (err) {
      setAssignments(prev);
      setFlash({ type: "error", text: formatApiError(err, "Failed to unassign question.") });
    } finally {
      setUnassigningId(null);
    }
  }

  async function handleSubmitProof(assignment, linkedinUrl) {
    const { data } = await api.post(`/assignments/${assignment.id}/submit_proof/`, {
      linkedin_post_url: linkedinUrl,
    });
    // Replace only this row with the API response so admin/student see the exact stored URL.
    setAssignments((list) => list.map((a) => (a.id === assignment.id ? data : a)));
    return data;
  }

  return (
    <div>
      <div className="flex items-center gap-3 mb-5">
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="input !w-auto text-sm">
          <option value="">All statuses</option>
          <option value="assigned">Assigned</option>
          <option value="in_progress">In Progress</option>
          <option value="completed">Completed</option>
        </select>
      </div>

      <p className="text-sm text-slate-500 mb-4">
        Solve the problem in your local editor, post your solution on LinkedIn, then paste the post URL below as proof of work.
      </p>

      <FlashBanner message={flash?.text} type={flash?.type} onClose={() => setFlash(null)} />

      {loading ? (
        <Spinner />
      ) : assignments.length === 0 ? (
        <EmptyState text="You haven't assigned any questions yet." />
      ) : (
        <div className="card divide-y divide-slate-100 p-2">
          {assignments.map((a) => (
            <AssignmentRow
              key={a.id}
              assignment={a}
              highlighted={String(a.id) === String(highlightId)}
              unassigning={unassigningId === a.id}
              onStatusChange={handleStatusChange}
              onUnassign={handleUnassign}
              onSubmitProof={handleSubmitProof}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
function MyActivity() {
  const [data, setData] = useState(null);
  const [period, setPeriod] = useState("30days");
  const [difficulty, setDifficulty] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const params = { period };
    if (difficulty) params.difficulty = difficulty;
    api.get("/analytics/my-activity/", { params }).then((res) => {
      setData(res.data);
      setLoading(false);
    });
  }, [period, difficulty]);

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-5">
        <PeriodSelect value={period} onChange={setPeriod} />
        <DifficultyFilter value={difficulty} onChange={setDifficulty} />
      </div>

      {loading || !data ? (
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
              <EmptyState text="No activity in this period." />
            ) : (
              data.items.map((a) => (
                <AssignmentRow key={a.id} assignment={a} readOnly />
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
}

function EmptyState({ text }) {
  return <div className="text-center py-14 text-slate-400 text-sm">{text}</div>;
}
