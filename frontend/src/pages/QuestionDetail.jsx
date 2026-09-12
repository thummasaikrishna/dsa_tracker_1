import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import api from "../api/axios";
import { DifficultyBadge } from "../components/Badges";
import Spinner from "../components/Spinner";
import { formatApiError } from "../utils/apiError";
import { ArrowLeft, Check, ChevronDown, ChevronUp, Plus, Trash2 } from "lucide-react";
import DeadlineCountdown from "../components/DeadlineCountdown";
import CodeWorkspace from "../components/CodeWorkspace";

export default function QuestionDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [question, setQuestion] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [assigning, setAssigning] = useState(false);
  const [toast, setToast] = useState("");
  const [examplesOpen, setExamplesOpen] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    api
      .get(`/questions/${id}/`)
      .then(({ data }) => {
        if (!cancelled) setQuestion(data);
      })
      .catch(() => {
        if (!cancelled) setError("Question not found.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function handleAssign() {
    if (!question || question.is_assigned_to_me) return;
    setAssigning(true);
    try {
      const { data } = await api.post("/assignments/", { question: question.id });
      setQuestion((q) => ({
        ...q,
        is_assigned_to_me: true,
        my_assignment_id: data.id,
      }));
      setToast("Question assigned. You can now start solving.");
      setTimeout(() => setToast(""), 2500);
    } catch (err) {
      setToast(formatApiError(err, "Failed to assign question."));
      setTimeout(() => setToast(""), 3500);
    } finally {
      setAssigning(false);
    }
  }

  async function handleUnassign() {
    const assignmentId = question?.my_assignment_id;
    if (!assignmentId) return;
    if (!window.confirm(`Unassign "${question.title}"?`)) return;
    setAssigning(true);
    try {
      await api.delete(`/assignments/${assignmentId}/`);
      setQuestion((q) => ({ ...q, is_assigned_to_me: false, my_assignment_id: null }));
      setToast("Please assign this question before attempting to solve it.");
      setTimeout(() => setToast(""), 2500);
    } catch (err) {
      setToast(formatApiError(err, "Failed to unassign question."));
      setTimeout(() => setToast(""), 3500);
    } finally {
      setAssigning(false);
    }
  }

  if (loading) return <Spinner full />;

  if (error || !question) {
    return (
      <div className="max-w-3xl mx-auto px-4 sm:px-6 py-10 text-center">
        <p className="text-slate-500 mb-4">{error || "Question not found."}</p>
        <button onClick={() => navigate("/dashboard")} className="btn btn-secondary">
          Back to dashboard
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-[1400px] mx-auto px-4 sm:px-6 py-4">
      <Link
        to="/dashboard"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 mb-4 transition-colors"
      >
        <ArrowLeft className="h-4 w-4" /> Back to Available Questions
      </Link>

      {toast && (
        <div className={`mb-4 text-sm px-3 py-2 rounded-lg inline-block ${
          toast.toLowerCase().includes("fail") ? "bg-red-50 text-red-700" : "bg-emerald-50 text-emerald-800"
        }`}>
          {toast}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        <div className="space-y-5 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto pr-1">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <h1 className="text-2xl font-bold text-slate-900 leading-tight flex-1 min-w-0">
              {question.title}
            </h1>
            <div className="flex items-center gap-2 shrink-0">
              <DifficultyBadge difficulty={question.difficulty} />
              {question.is_assigned_to_me ? (
                <div className="flex items-center gap-2">
                  <span className="text-sm text-emerald-600 font-medium inline-flex items-center gap-1.5 px-3 py-1.5">
                    <Check className="h-4 w-4" /> Question Assigned
                  </span>
                  {question.my_assignment_id ? (
                    <button
                      type="button"
                      onClick={handleUnassign}
                      disabled={assigning}
                      className="btn btn-secondary !px-3 !py-1.5 text-sm text-rose-700"
                    >
                      <Trash2 className="h-4 w-4" /> Unassign
                    </button>
                  ) : null}
                </div>
              ) : (
                <button
                  onClick={handleAssign}
                  disabled={assigning}
                  className="btn btn-primary !px-3 !py-1.5 text-sm"
                >
                  <Plus className="h-4 w-4" /> Assign Question
                </button>
              )}
            </div>
          </div>

          <DeadlineCountdown
            createdAt={question.created_at}
            deadline={question.deadline}
            remainingSeconds={question.remaining_seconds}
            deadlineExpired={question.deadline_expired}
          />

          {question.is_assigned_to_me && (
            <div className="text-sm text-emerald-800 bg-emerald-50 border border-emerald-100 rounded-lg px-3 py-2">
              You can now start solving.
            </div>
          )}

          <section>
            <h2 className="text-base font-semibold text-slate-900 mb-2">Problem Statement:</h2>
            <p className="text-sm text-slate-600 leading-relaxed whitespace-pre-wrap">
              {question.description || "No description provided."}
            </p>
          </section>

          {question.prerequisites && (
            <section>
              <h2 className="text-base font-semibold text-slate-900 mb-2">Pre-requisites:</h2>
              <p className="text-sm text-brand-700 leading-relaxed">{question.prerequisites}</p>
            </section>
          )}

          {question.examples && (
            <section className="card overflow-hidden">
              <button
                type="button"
                onClick={() => setExamplesOpen((o) => !o)}
                className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-50 transition-colors"
              >
                <span className="text-base font-semibold text-slate-900">Examples</span>
                {examplesOpen ? (
                  <ChevronUp className="h-4 w-4 text-slate-400" />
                ) : (
                  <ChevronDown className="h-4 w-4 text-slate-400" />
                )}
              </button>
              {examplesOpen && (
                <div className="border-t border-slate-100 px-4 py-3 bg-slate-50">
                  <pre className="whitespace-pre-wrap font-mono text-xs sm:text-sm text-slate-700 leading-relaxed">
                    {question.examples}
                  </pre>
                </div>
              )}
            </section>
          )}

          {(question.test_cases || []).length > 0 && (
            <section className="space-y-2">
              <h2 className="text-base font-semibold text-slate-900">Public Test Cases</h2>
              {question.test_cases.map((tc, index) => (
                <div key={tc.id || index} className="card px-4 py-3 text-sm space-y-2">
                  <div className="font-medium text-slate-800">Test Case {index + 1}</div>
                  <div>
                    <div className="text-xs text-slate-500 mb-0.5">Input</div>
                    <pre className="whitespace-pre-wrap font-mono text-xs bg-slate-50 rounded-md p-2">{tc.input_data || ""}</pre>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500 mb-0.5">Expected Output</div>
                    <pre className="whitespace-pre-wrap font-mono text-xs bg-slate-50 rounded-md p-2">{tc.expected_output || "Expected output not yet verified"}</pre>
                  </div>
                </div>
              ))}
            </section>
          )}
        </div>

        <div className="lg:sticky lg:top-16">
          <CodeWorkspace questionId={question.id} assigned={Boolean(question.is_assigned_to_me)} />
        </div>
      </div>
    </div>
  );
}
