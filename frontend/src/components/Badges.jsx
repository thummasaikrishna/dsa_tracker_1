export function DifficultyBadge({ difficulty }) {
  return <span className={`badge badge-${difficulty}`}>{difficulty}</span>;
}

const STATUS_LABELS = {
  assigned: "Assigned",
  in_progress: "In Progress",
  completed: "Completed",
};

export function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{STATUS_LABELS[status] || status}</span>;
}

export function ValidatedBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 text-emerald-800 text-xs font-semibold px-2.5 py-1 border border-emerald-200">
      Validated
    </span>
  );
}

export function ProofStatusBadge({ proofStatus }) {
  if (proofStatus === "validated") return <ValidatedBadge />;
  if (proofStatus === "pending") {
    return (
      <span className="inline-flex items-center rounded-full bg-amber-50 text-amber-700 text-xs font-medium px-2.5 py-1 border border-amber-200">
        Pending review
      </span>
    );
  }
  if (proofStatus === "rejected") {
    return (
      <span className="inline-flex items-center rounded-full bg-rose-50 text-rose-700 text-xs font-medium px-2.5 py-1 border border-rose-200">
        Rejected
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full bg-slate-50 text-slate-500 text-xs font-medium px-2.5 py-1 border border-slate-200">
      No proof yet
    </span>
  );
}
