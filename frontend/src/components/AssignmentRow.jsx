import { useEffect, useState } from "react";
import { DifficultyBadge, StatusBadge, ValidatedBadge, ProofStatusBadge } from "./Badges";
import { Trash2, ExternalLink, Send } from "lucide-react";
import { formatApiError } from "../utils/apiError";
import DeadlineCountdown from "./DeadlineCountdown";

const STATUS_OPTIONS = ["assigned", "in_progress"];

function isLikelyLinkedInUrl(value) {
  try {
    const host = new URL(value.trim()).hostname.toLowerCase();
    return (
      host === "linkedin.com" ||
      host.endsWith(".linkedin.com") ||
      host === "lnkd.in" ||
      host.endsWith(".lnkd.in")
    );
  } catch {
    return false;
  }
}

export default function AssignmentRow({
  assignment,
  onStatusChange,
  onUnassign,
  onSubmitProof,
  readOnly = false,
  highlighted = false,
  unassigning = false,
}) {
  const [url, setUrl] = useState(assignment.linkedin_post_url || "");
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState(null); // { type: 'success'|'error', text }
  const isValidated = assignment.proof_status === "validated";
  const isPending = assignment.proof_status === "pending";

  // Keep input in sync when parent refreshes assignment after submit.
  useEffect(() => {
    setUrl(assignment.linkedin_post_url || "");
  }, [assignment.id, assignment.linkedin_post_url]);

  async function handleSubmitProof(e) {
    e.preventDefault();
    if (!onSubmitProof || !url.trim()) return;
    setFeedback(null);

    const trimmed = url.trim();
    if (!isLikelyLinkedInUrl(trimmed)) {
      setFeedback({
        type: "error",
        text: "Only LinkedIn post links are accepted (linkedin.com or lnkd.in).",
      });
      return;
    }

    setSubmitting(true);
    try {
      await onSubmitProof(assignment, trimmed);
      setFeedback({ type: "success", text: "Proof submitted successfully." });
      setTimeout(() => setFeedback((f) => (f?.type === "success" ? null : f)), 4000);
    } catch (err) {
      setFeedback({
        type: "error",
        text: formatApiError(err, "Failed to submit proof."),
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className={`py-3 px-4 hover:bg-slate-50 rounded-lg transition-colors space-y-3 ${
        highlighted ? "bg-amber-50 ring-2 ring-inset ring-amber-300" : ""
      }`}
    >
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex-1 min-w-0">
          <div className="font-medium text-slate-900 truncate">{assignment.question_title}</div>
          <div className="text-xs text-slate-400">
            Assigned {new Date(assignment.assigned_at).toLocaleDateString()}
          </div>
          {assignment.question_deadline && (
            <div className="mt-1">
              <DeadlineCountdown
                createdAt={assignment.question_created_at}
                deadline={assignment.question_deadline}
                remainingSeconds={assignment.remaining_seconds}
                deadlineExpired={assignment.deadline_expired}
                compact
              />
            </div>
          )}
        </div>
        <DifficultyBadge difficulty={assignment.difficulty} />
        {readOnly ? (
          <>
            <StatusBadge status={assignment.status} />
            <ProofStatusBadge proofStatus={assignment.proof_status} />
          </>
        ) : (
          <>
            {isValidated ? (
              <StatusBadge status="completed" />
            ) : (
              <select
                value={assignment.status === "completed" ? "in_progress" : assignment.status}
                onChange={(e) => onStatusChange(assignment, e.target.value)}
                className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500"
                disabled={isValidated}
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s.replace("_", " ")}
                  </option>
                ))}
              </select>
            )}
            <ProofStatusBadge proofStatus={assignment.proof_status} />
            {!isValidated && (
              <button
                onClick={() => onUnassign(assignment)}
                disabled={unassigning}
                className="text-slate-400 hover:text-red-600 p-1.5 rounded-lg hover:bg-red-50 transition-colors disabled:opacity-50"
                title="Unassign"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            )}
          </>
        )}
      </div>

      {isValidated && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2">
          <ValidatedBadge />
          <span className="text-sm font-semibold text-emerald-800 tracking-wide">
            YOUR SOLUTION HAS BEEN VALIDATED
          </span>
          <span className="text-sm font-semibold text-emerald-800">
            Points Earned: +{assignment.points_awarded ?? 0} ⭐
          </span>
          {assignment.linkedin_post_url && (
            <a
              href={assignment.linkedin_post_url}
              target="_blank"
              rel="noreferrer"
              className="ml-auto text-xs text-emerald-700 hover:underline inline-flex items-center gap-1 max-w-[40%] truncate"
              title={assignment.linkedin_post_url}
            >
              View LinkedIn post <ExternalLink className="h-3 w-3 shrink-0" />
            </a>
          )}
        </div>
      )}

      {!readOnly && !isValidated && (
        <form onSubmit={handleSubmitProof} className="space-y-2">
          <div className="flex flex-col sm:flex-row gap-2">
            <input
              className="input text-sm flex-1"
              type="url"
              placeholder="Paste your LinkedIn post URL as proof of work..."
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                if (feedback) setFeedback(null);
              }}
              required
            />
            <button type="submit" disabled={submitting} className="btn btn-primary !py-2 text-sm whitespace-nowrap">
              <Send className="h-3.5 w-3.5" />
              {submitting ? "Submitting..." : isPending ? "Update proof" : "Submit proof"}
            </button>
          </div>
          {feedback && (
            <div
              className={`text-sm px-3 py-2 rounded-lg ${
                feedback.type === "success"
                  ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                  : "bg-red-50 text-red-700 border border-red-200"
              }`}
              role="status"
            >
              {feedback.text}
            </div>
          )}
          {isPending && assignment.linkedin_post_url && !feedback && (
            <p className="text-xs text-slate-500 truncate" title={assignment.linkedin_post_url}>
              Submitted: {assignment.linkedin_post_url}
            </p>
          )}
          {assignment.submitted_after_deadline && (
            <p className="text-xs font-medium text-rose-600">Submitted after deadline — 0 points</p>
          )}
          {assignment.proof_status === "pending" && !assignment.submitted_after_deadline && (
            <p className="text-xs text-slate-500">
              Potential points: {assignment.potential_points ?? 0} (awarded after admin validation)
            </p>
          )}
          {assignment.proof_status === "rejected" && (
            <p className="text-xs font-medium text-rose-600">Proof rejected — 0 points. You may resubmit a new LinkedIn URL.</p>
          )}
        </form>
      )}

      {readOnly && assignment.linkedin_post_url && (
        <a
          href={assignment.linkedin_post_url}
          target="_blank"
          rel="noreferrer"
          className="text-xs text-brand-600 hover:underline inline-flex items-center gap-1 max-w-full"
          title={assignment.linkedin_post_url}
        >
          <span className="truncate">{assignment.linkedin_post_url}</span>
          <ExternalLink className="h-3 w-3 shrink-0" />
        </a>
      )}
    </div>
  );
}
